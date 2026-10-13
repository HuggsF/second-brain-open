# Provedores na nuvem com reserva local — design

Data: 2026-10-13 · Escopo: núcleo agnóstico (tarefas locais) · Status: aguardando revisão
Depende de: `.superpowers/specs/2026-10-13-09-00-protocolo-tarefas-locais-design.md` (implementado no `main`).

## 1. Intenção

As tarefas pequenas (`classify`, `extract`, `summarize`, `validate`) levam 16 s com o modelo local carregado e
44–51 s a frio nesta máquina (i5-1334U, sem GPU dedicada, Ollama em CPU). Isso inviabiliza o uso interativo
pelos agentes. Objetivo: atender as tarefas com um modelo pequeno na nuvem (latência típica de poucos segundos,
a medir) e manter o Ollama como reserva, sem perder as garantias do protocolo.

Decisões tomadas no brainstorming:
- Nuvem primeiro, local de reserva.
- Só provedores sem retenção nem treino (OpenRouter: `provider.data_collection: deny` e `provider.zdr: true`).
- Abordagem A: cliente genérico compatível com OpenAI e uma cadeia de provedores declarada no perfil.

Critério de sucesso:
- Com `OPENROUTER_API_KEY` no `.env`, o `task-eval` do perfil kiosk atende as tarefas pela nuvem, com o mesmo
  ou maior acerto que o local (92%) e latência média bem abaixo de 16 s por chamada. O valor exato é medido e
  registrado no ADR-018.
- Sem a chave, ou com a nuvem fora, tudo continua funcionando pelo Ollama.
- Nenhuma chave e nenhum conteúdo de tarefa aparecem em envelope, evento, trace ou mensagem de erro.

## 2. Fora do escopo

- Painel em tempo real.
- Roteamento por sensibilidade do conteúdo.
- Cache de prompts.
- Streaming.
- Cobrança real lida da API do provedor; o custo vem do `price` declarado no perfil.
- Escrever ou ler o `.env`: o usuário adiciona a chave.

## 3. Componentes

```
core/local_tasks/
  openai_compat_client.py   OpenAICompatClient: POST {base_url}/chat/completions; mesma interface do
                            OllamaClient: chat(model, system, user, schema) -> Completion; erros -> LocalModelError
  providers.py              ProviderSpec (dados de um item de `providers`), build_client(profile),
                            FallbackClient(entradas) que tenta em ordem
  profile.py                + campo `providers: tuple[ProviderSpec, ...]` (vazio = só Ollama, como hoje)
  router.py                 client=None -> build_client(profile); status() lista os provedores e a disponibilidade
core/protocol/schemas/envelope.schema.json   cost.tier += "cloud"; cost.provider (string) e cost.actual_usd (number ≥ 0) opcionais
mcp_servers/local_tasks_mcp.py, cli.py       load_dotenv(<raiz>/.env), como os gateways existentes
profiles/kiosk/profile.yaml                  provedor de nuvem primeiro, Ollama de reserva
```

### Item de `providers`

| Campo | Tipo | Padrão | Uso |
|---|---|---|---|
| `kind` | `openai_compatible` \| `ollama` | obrigatório | escolhe o cliente |
| `name` | string | igual a `kind` | aparece em `cost.provider` e nos eventos |
| `model` | string | obrigatório | modelo pedido ao provedor |
| `base_url` | string | `settings.ollama_url` para `ollama`; obrigatório para `openai_compatible` | endpoint |
| `api_key_env` | string | nenhum | **nome** da variável de ambiente com a chave; nunca o valor |
| `timeout_seconds` | int | `timeout_seconds` do perfil | timeout da chamada |
| `keep_alive` | string \| int | `keep_alive` do perfil | só `ollama` |
| `structured` | `json_schema` \| `json_object` \| `none` | `json_schema` | forma do `response_format` |
| `extra` | objeto | `{}` | mesclado no corpo da requisição (ex.: `provider: {data_collection: deny, zdr: true}`) |
| `price` | `{input, output}` USD/1M | `{0, 0}` | calcula `cost.actual_usd` |

Erros de configuração levantam `ValueError` em `load_profile`: `kind` desconhecido, `model` ausente,
`openai_compatible` sem `base_url`, `structured` inválido, `price` não numérico. O roteador já transforma
esse erro em `status: error`. Um perfil sem `providers` tem comportamento idêntico ao atual.

O prazo total de um `run_task` passa a usar o maior `timeout_seconds` entre os provedores:
`max(timeouts) × (1 + retries) × 2`.

### Perfil kiosk

```yaml
providers:
  - kind: openai_compatible
    name: openrouter
    base_url: https://openrouter.ai/api/v1
    model: <definido pelo task-eval, §7>
    api_key_env: OPENROUTER_API_KEY
    timeout_seconds: 20
    structured: json_schema
    extra:
      provider: {data_collection: deny, zdr: true}
    price: {input: <do modelo escolhido>, output: <do modelo escolhido>}
  - kind: ollama
    model: llama3.2:3b
    timeout_seconds: 120
    keep_alive: 30m
```

O nome `openrouter` e a URL aparecem só no perfil; o código do núcleo não cita fornecedor nenhum.

## 4. Fluxo

### `OpenAICompatClient.chat`

- Header `Authorization: Bearer <os.environ[api_key_env]>`, lido na hora da chamada; sem `api_key_env`, sem header.
- Corpo: `model`; `messages` [system, user]; `temperature: 0`; `response_format` conforme `structured`:
  - `json_schema` → `{"type": "json_schema", "json_schema": {"name": "output", "strict": true, "schema": <schema>}}`
  - `json_object` → `{"type": "json_object"}`
  - `none` → sem `response_format`
- O bloco `extra` é mesclado no topo do corpo. As chaves de `extra` não podem sobrescrever `model` nem `messages`.
- Resposta: texto em `choices[0].message.content`; tokens em `usage.prompt_tokens` e `usage.completion_tokens`
  (ausentes → 0); `ms` medido localmente com `time.perf_counter`.

### `FallbackClient`

- Recebe entradas `(spec, client)` em ordem. Uma entrada `openai_compatible` cujo `api_key_env` não está no
  ambiente é **pulada**, sem chamada.
- Em `LocalModelError` (`local_unavailable` ou `timeout`), tenta a próxima. Se todas falharem, levanta o último
  erro. Se nenhuma estiver disponível, levanta `LocalModelError("local_unavailable")`.
- Guarda em `last_provider` o `ProviderSpec` que respondeu, para o roteador preencher `cost.model`,
  `cost.provider`, `cost.tier` (`cloud` para `openai_compatible`, `local` para `ollama`) e `cost.actual_usd`.
- Resposta que chega mas não passa no schema **não** troca de provedor: o laço de nova tentativa do roteador
  chama o `FallbackClient` de novo, que recomeça pelo primeiro provedor disponível.

### Mapeamento de erros (`OpenAICompatClient`)

| Situação | `LocalModelError.reason` |
|---|---|
| `httpx.TimeoutException` | `timeout` |
| falha de conexão / outro `TransportError` | `local_unavailable` |
| HTTP 401, 403, 404, 429, 5xx e demais ≥ 400 | `local_unavailable` |
| 200 sem `choices[0].message.content` texto | `local_unavailable` |

`str(erro)` leva só o motivo e o tipo da exceção ou o status HTTP: nunca header, chave ou conteúdo.
O vocabulário de `reason` não muda; `local_unavailable` passa a significar "modelo indisponível" (texto do
protocolo, README e ADR atualizados).

## 5. Custo, eventos e status

- `cost.tier`: `cloud` | `local` | `deterministic`.
- `cost.model`: modelo que respondeu.
- `cost.provider`: `name` do provedor (ausente em `deterministic`).
- `cost.actual_usd`: tokens × `price` do provedor / 1e6.
- `paid_equivalent_usd`: mantém o significado atual (preço de referência do modelo pago grande, `paid_reference`).
- Os eventos copiam `cost` como hoje; nada de conteúdo.
- `router.status()` ganha `providers`, uma lista de `{name, kind, model, configured, available}`:
  - `configured` = a chave está no ambiente (ou não é necessária).
  - `available` = o endpoint respondeu. Para `ollama`, `/api/tags`; para `openai_compatible`, `GET {base_url}/models`
    com timeout de 5 s.
  - As chaves existentes do status ficam iguais.

## 6. Privacidade e segurança

- A chave é lida do ambiente só no momento da chamada e nunca é gravada: nem em envelope, evento, trace, erro,
  relatório ou teste (os testes usam valor sentinela).
- O conteúdo só sai para provedores `openai_compatible` do perfil. No perfil kiosk, com
  `provider.data_collection: deny` e `provider.zdr: true`. O README orienta a travar o mesmo na conta
  (openrouter.ai/settings/privacy).
- O trace MCP continua sem conteúdo (`content_args`).
- CLAUDE.md §2 ("Never") ganha: nunca registrar a chave de provedor; conteúdo de tarefa só vai a provedor
  declarado no perfil com garantia de não retenção.

## 7. Testes e avaliação

TDD; nenhum teste usa a rede.

1. `tests/test_openai_compat_client.py` (`httpx.MockTransport`):
   - corpo por `structured`, com `extra` mesclado sem sobrescrever `model` e `messages`;
   - header com a chave do ambiente;
   - cada linha da tabela de erros;
   - `usage` ausente vira 0;
   - a chave sentinela não aparece em `str(erro)`.
2. `tests/test_providers.py`:
   - parse de `providers` e erros de configuração;
   - provedor sem chave é pulado sem chamada;
   - falha leva ao próximo; todas falham, sobe o último erro;
   - `last_provider` está correto;
   - perfil sem `providers` = só Ollama (regressão).
3. `tests/test_local_tasks.py`:
   - `run_task` com `FallbackClient` falso preenche `tier`, `provider` e `actual_usd`;
   - envelope válido;
   - prazo com o maior timeout.
4. Envelope: `cloud`, `provider` e `actual_usd` passam no schema; tier desconhecido falha.
5. Privacidade: sentinelas de chave e de texto ausentes de `events.jsonl`, trace log e erros.
6. Gate de agnosticismo inclui `openai_compat_client.py` e `providers.py`.
7. `cli.py task-eval`:
   - ganha `--profile NOME`;
   - imprime a latência média e o tier que respondeu, por tarefa;
   - usa a cadeia de provedores do perfil.
   Com a chave no `.env`, comparar 2 ou 3 modelos pequenos com saída estruturada e endpoint ZDR, escolhidos da
   lista atual do provedor. Registrar acerto, latência média e custo por chamada. O vencedor define o `model` e o
   `price` do perfil kiosk.

## 8. Documentação e decisões

- **ADR-018** (`scope: second-brain`, `related: [ADR-008, ADR-014, ADR-017]`):
  - Decisão: nuvem primeiro com reserva local, garantia `zdr`/`deny` e cliente compatível com OpenAI.
  - Alternativas descartadas: local primeiro; um provedor só; roteamento por sensibilidade; cliente específico de
    fornecedor; biblioteca de terceiros (LiteLLM).
  - Consequências: latência medida, custo real e o que sai da máquina.
- **ADR-017**: só o frontmatter muda: `status: "Substituído por ADR-018"`. O texto continua igual; o ADR-018
  explica que a substituição é parcial (a decisão "o núcleo nunca chama a nuvem").
- **README**: seção de provedores, `OPENROUTER_API_KEY` no `.env`, trava de privacidade da conta e resultados
  do `task-eval`.
- **CLAUDE.md**: §2 (regra da chave e do conteúdo); §3 (novos módulos de teste no comando de prova).
- **`requirements.txt`**: nada novo (`httpx` e `python-dotenv` já declarados).

## 9. Riscos

- **Modelo sem suporte a `json_schema` estrito.** O roteador ainda valida e tenta de novo; `structured` pode ser
  rebaixado para `json_object` no perfil.
- **Nenhum endpoint ZDR para o modelo escolhido.** O OpenRouter devolve 404, e a tarefa cai no Ollama. O
  `task-eval` revela isso antes de fixar o modelo.
- **Custo inesperado.** O `actual_usd` nos eventos permite somar o gasto. Limite de gasto fica na conta do
  provedor; o núcleo não impõe teto.
- **Latência da nuvem não medida ainda.** O critério de sucesso depende da medição do §7.

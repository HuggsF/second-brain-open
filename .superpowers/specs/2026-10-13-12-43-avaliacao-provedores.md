# Avaliação de provedores de nuvem — 2026-10-13

Spec: `.superpowers/specs/2026-10-13-12-43-provedores-nuvem-com-reserva-local-design.md` (§1 critério de sucesso, §7).
Decisão: `vault/adrs/ADR-018-provedores-nuvem-com-reserva-local.md`.

## Procedimento

- Candidatos levantados em `GET https://openrouter.ai/api/v1/models` (público, sem chave), 462 modelos.
  Filtro: `structured_outputs` em `supported_parameters`, `context_length` ≥ 8192, sem sufixo `:free`,
  preço de entrada > 0. Fora também os aliases `~…` (apontam para "a versão mais nova" e mudam sem aviso)
  e as variantes `:batch` (sem resposta interativa). Ficaram os 3 de menor preço de entrada, todos modelos
  instruídos, com o ID copiado da lista.
- Um perfil temporário `profiles/eval-<n>/profile.yaml` por candidato (não comitado, apagado no fim), com o
  vocabulário do kiosk, o provedor `openai_compatible` com `extra.provider = {data_collection: deny, zdr: true}`,
  `structured: json_schema`, `timeout_seconds: 20`, e o Ollama `llama3.2:3b` de reserva.
- Execução a partir da raiz do worktree:
  `BRAIN_ENV_FILE=C:/KIOSK/second-brain/.env cli.py task-eval --profile eval-<n> --min-accuracy 0`.
  O arquivo de ambiente não foi lido nem impresso; só o caminho foi passado.
- Latência: média de `cost.ms` das 9 chamadas de modelo (3 `classify`, 3 `extract`, 3 `summarize`); os 3
  casos de `validate` do dataset não têm `source`, são determinísticos e ficam fora da média. O `ms` inclui o
  tempo das tentativas que falharam antes da resposta (correção 6 desta rodada).
- Custo por chamada: média de `cost.actual_usd` das mesmas 9 chamadas, lida de `.runtime/events.jsonl`.

## Candidatos

| # | ID (lista pública) | Contexto | Entrada US$/1M | Saída US$/1M | Endpoints ZDR na lista |
|---|---|---|---|---|---|
| 1 | `deepseek/deepseek-v4-flash-0731` | 1.048.576 | 0,016 | 0,64 | 20 |
| 2 | `openai/gpt-oss-20b` | 131.072 | 0,018 | 0,09 | 10 |
| 3 | `inclusionai/ling-3.0-flash-vl` | 262.144 | 0,021 | 0,0616 | 2 |

## Resultados

| Candidato | Acerto | classify | extract | summarize | Latência média | Tiers (9 chamadas) | Custo por chamada |
|---|---|---|---|---|---|---|---|
| `deepseek/deepseek-v4-flash-0731` | 100% | 3/3 · 6,3 s | 3/3 · 6,6 s | 3/3 · 5,6 s | 6,2 s | cloud 9 | US$ 0,000195 |
| `openai/gpt-oss-20b` | 100% | 3/3 · 6,2 s | 3/3 · 4,0 s | 3/3 · 13,2 s | 7,8 s | cloud 9 | US$ 0,000029 |
| `inclusionai/ling-3.0-flash-vl` | 92% | 2/3 · 23,5 s | 3/3 · 8,9 s | 3/3 · 5,5 s | 12,7 s | cloud 5, local 4 | US$ 0,000007 |

`validate`: 3/3 em todos, determinístico (0 ms, sem custo).

- `openai/gpt-oss-20b` rodou duas vezes; a primeira deu 10,6 s de média (máxima 25,5 s), todas as chamadas em
  `cloud` e `status: ok`; o acerto dessa rodada não foi registrado (saída cortada). A tabela traz a segunda.
- `inclusionai/ling-3.0-flash-vl`: as 3 chamadas de `classify` e 1 de `extract` caíram no Ollama. Causa,
  confirmada chamando só a nuvem para os 6 casos de `classify` e `extract`: **HTTP 429** (limite de taxa) nos dois
  endpoints ZDR desse modelo. O `classify` 2/3 é o acerto do `llama3.2:3b` local.

## Vencedor

Só os candidatos 1 e 2 tiveram todas as chamadas de modelo em `tier: cloud`. Empate no acerto (100%); desempate
pela menor latência: **`deepseek/deepseek-v4-flash-0731`** (6,2 s contra 7,8 s). O perfil kiosk recebeu esse ID e
o preço da lista: `price: {input: 0.016, output: 0.64}` (US$ por 1M tokens).

## `task-eval --profile kiosk` final

```
classify: casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=14003 cloud=3
extract: casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=34267 cloud=3
summarize: casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=4576 cloud=3
validate: casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=0 deterministic=3
Acerto geral: 100% (mínimo 0%)
```

- 9 chamadas de modelo, todas `cloud`; latência média 17,6 s, mediana 7,2 s, máxima 87,5 s.
- A chamada de 87,5 s é uma única tentativa de `extract` (152 tokens de entrada, 1.805 de saída): o modelo
  raciocinou longamente. O `timeout_seconds: 20` é o timeout de leitura do `httpx`, não um prazo total, e não
  corta uma resposta que continua chegando.
- Custo médio por chamada US$ 0,000294.

## Critério de sucesso (spec §1)

| Critério | Resultado |
|---|---|
| Acerto pela nuvem ≥ 92% (local) | Atingido: 100% |
| Latência média bem abaixo de 16 s | **Não atingido** no kiosk final (17,6 s); 6,2 s na rodada do candidato |
| Sem chave ou com a nuvem fora, tudo pelo Ollama | Atingido (testes; e na prática com o 429 do candidato 3) |
| Chave e conteúdo fora de envelope, eventos, trace e erros | Atingido (testes com chave sentinela) |

Por isso o ADR-018 fica `Proposto`. Pendência: prazo total por chamada no cliente (ou limitar o raciocínio
via `extra`) e nova medição.

## Gasto

5 rodadas de `task-eval` (45 chamadas de modelo) + 6 chamadas de diagnóstico (todas 429, sem custo):
US$ 0,0050 somando `actual_usd`.

## Histórico: primeira tentativa (conta gratuita)

Na primeira rodada da Task 6 a conta do OpenRouter estava em free-tier, sem crédito. Os modelos pagos
(`openai/gpt-oss-20b`, `mistralai/mistral-nemo`) responderam **HTTP 402** (pagamento exigido); os gratuitos
(`google/gemma-4-26b-a4b-it:free`, `google/gemma-4-31b-it:free`, `nvidia/nemotron-3-super-120b-a12b:free`)
responderam **HTTP 429** (pool compartilhado congestionado); o alias `~deepseek/deepseek-v4-flash-latest`
respondeu **HTTP 400** ("not a valid model ID"). Todas as chamadas caíram no Ollama local, com 92% de acerto
(`classify` 2/3), o que validou a reserva mas não mediu nenhum modelo na nuvem.

Naquela rodada o perfil kiosk recebeu `google/gemma-4-27b-it` com preço {0,10, 0,20}: o modelo não existe na lista
do OpenRouter e o preço não tinha fonte. Os dois foram substituídos pelo vencedor desta avaliação.

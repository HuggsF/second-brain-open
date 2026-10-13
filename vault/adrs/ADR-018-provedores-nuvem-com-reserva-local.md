---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-13
related: [ADR-008, ADR-014, ADR-017]
---
# ADR-018: Provedores de nuvem com reserva local

> Esta ADR estende o ADR-017 (tier local com perfis) com suporte a provedores de nuvem. O ADR-017 permanece válido para a parte determinística e de perfis; esta ADR adiciona a cadeia de provedores e o fallback.

## Contexto
O ADR-017 criou o tier local com `llama3.2:3b` e definiu `escalate` como única saída quando o modelo não resolve. O agente chamador tem de refazer a tarefa com seu próprio modelo pago, gastando tokens da janela de contexto e quebrando a separação entre "quem orquestra" e "quem executa tarefas simples". Além disso, o modelo local de 3B tem qualidade limitada em tarefas de classificação (67% de acerto no dataset dourado).

Adicionar um provedor de nuvem barato, com reserva local para quando a nuvem falhar, reduz o `escalate` e melhora a qualidade sem perder a garantia de funcionamento offline.

## Alternativas Consideradas
- **Chamar a nuvem direto no roteador, sem fallback:** se o provedor falhar, vira `escalate`. Descartada: perde a resiliência offline que o tier local provê.
- **Lista de provedores fixa no código:** viola o agnosticismo do núcleo e impede outra instância de usar outro fornecedor.
- **Retry com backoff no mesmo provedor:** acrescenta latência sem ganhar resiliência; o fallback para o próximo é mais previsível e já faz retry com o modelo local.
- **Usar a chave de API diretamente no código:** proibido pela política de segurança (CLAUDE.md §2). O perfil cita o nome da variável de ambiente (`api_key_env`), nunca o valor.

## Decisão
1. O perfil passa a aceitar um bloco `providers`, lista ordenada de provedores. Cada item tem `kind` (`openai_compatible` ou `ollama`), `model`, `base_url`, `api_key_env` (nome da variável), `timeout_seconds`, `structured` (`json_schema`, `json_object` ou `none`), `extra` (mesclado no corpo da requisição) e `price` (`input`, `output` em USD/1M tokens). Perfis sem `providers` continuam idênticos ao ADR-017.
2. `OpenAICompatClient` implementa a interface `chat()` do `OllamaClient`, usando `Bearer <api_key>` e `response_format` conforme o `structured` do provedor. `extra` é mesclado no corpo (exceto `model` e `messages`), permitindo `provider: {data_collection: deny, zdr: true}` do OpenRouter.
3. `FallbackClient` recebe a lista de `(ProviderSpec, Client)` e tenta em ordem. Se a chave do provedor está ausente, pula. Se a chamada falha com `LocalModelError`, tenta o próximo. `last_provider` guarda o `ProviderSpec` do provedor que respondeu, usado para preencher `cost.tier`, `cost.provider` e `cost.actual_usd` no envelope.
4. `build_client(profile)` é a fábrica: sem providers, cria `OllamaClient` como antes; com providers, cria `FallbackClient`.
5. `cost.tier` pode ser `local`, `cloud` ou `deterministic`. `cost.provider` (string) e `cost.actual_usd` (number ≥ 0) são opcionais e só aparecem quando o provedor é nomeado.
6. `deadline_timeout(profile)` usa o maior `timeout_seconds` entre os provedores. O prazo total do `run_task` é `max(timeouts) × (1 + retries) × 2`.
7. `status()` reporta a lista de provedores com nome, kind, modelo, configurado e disponível.
8. `cli.py` e `mcp_servers/local_tasks_mcp.py` chamam `load_dotenv(settings.env_file, override=False)` na importação. `settings.env_file` é `BRAIN_ENV_FILE` ou `<raiz>/.env`.
9. `task-eval` aceita `--profile NOME`, usa `build_client(profile)` e reporta latência média e contagem por tier.

## Consequências
- **Fallback validado.** Com a conta OpenRouter em free-tier (sem créditos), todas as chamadas caem no Ollama local com 92% de acerto (12 casos). O mecanismo de fallback funciona: 402 (sem crédito), 429 (rate limit) e timeout são detectados e o próximo provedor na lista é tentado.
- **Latência do fallback.** Quando a nuvem falha e cai para o local, a latência acumula o timeout da tentativa na nuvem + a chamada local. Com `timeout_seconds: 20` no provedor cloud e 120s no local, uma chamada que falha na nuvem leva ~20s + ~20s (local) = ~40s. O prazo total do `run_task` é `120 × (1+1) × 2 = 480s`.
- **Custo rastreado.** `cost.actual_usd` calcula o custo real baseado nos preços do provedor. `cost.paid_equivalent_usd` continua usando o `paid_reference` do perfil para comparação.
- **Agnosticismo mantido.** O nome do fornecedor (OpenRouter) aparece somente no perfil `kiosk`, nunca no código do núcleo. Outra instância pode usar outro fornecedor.
- **Chave protegida.** O perfil cita `OPENROUTER_API_KEY` (nome da variável), nunca o valor. `load_dotenv` carrega do `.env` que está no `.gitignore`.
- **Avaliação pendente.** Com créditos na conta, reexecutar `task-eval --profile kiosk` para medir a qualidade real do `google/gemma-4-27b-it` na nuvem. O resultado atual é inteiramente do `llama3.2:3b` local.
- `httpx` passa a ser dependência direta no `requirements.txt`.

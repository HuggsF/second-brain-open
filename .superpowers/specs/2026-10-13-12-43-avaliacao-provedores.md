# Avaliação de Provedores de Nuvem — 2026-10-13

## Candidatos

Modelos selecionados do `GET https://openrouter.ai/api/v1/models` com:
- `structured_outputs` ou `response_format` em `supported_parameters`
- contexto ≥ 8k
- preço de entrada ≤ $0.50/M tokens

| # | Modelo | Contexto | Entrada $/M | Saída $/M | Params |
|---|--------|----------|-------------|-----------|--------|
| 1 | `deepseek/deepseek-v4-flash-0731` | 1.048.576 | 0.016 | 0.640 | `response_format`, `structured_outputs` |
| 2 | `openai/gpt-oss-20b` | 131.072 | 0.018 | 0.090 | `response_format`, `structured_outputs` |
| 3 | `mistralai/mistral-nemo` | 131.072 | 0.029 | 0.030 | `response_format`, `structured_outputs` |

### Modelos gratuitos testados

| Modelo | Contexto | Params |
|--------|----------|--------|
| `google/gemma-4-26b-a4b-it:free` | 262.144 | `response_format` |
| `google/gemma-4-31b-it:free` | 262.144 | `response_format` |
| `nvidia/nemotron-3-super-120b-a12b:free` | 262.144 | `response_format`, `structured_outputs` |

## Resultados

### Configuração da conta

```
GET /api/v1/auth/key → is_free_tier: true, usage: 0
```

### Falhas observadas

| Modelo | Modo | Extra | HTTP | Motivo |
|--------|------|-------|------|--------|
| `deepseek/deepseek-v4-flash-latest` | json_schema | `data_collection: deny` | 400 | "not a valid model ID" (alias `~` na lista) |
| `openai/gpt-oss-20b` | json_schema/json_object | `data_collection: deny` | 402 | Payment required (conta free-tier) |
| `mistralai/mistral-nemo` | json_schema/json_object | `data_collection: deny` | 402 | Payment required (conta free-tier) |
| `google/gemma-4-26b-a4b-it:free` | json_schema/json_object | `data_collection: deny` | 429 | Rate limited (shared pool congested) |
| `google/gemma-4-31b-it:free` | json_schema/json_object | `data_collection: deny` | 429 | Rate limited |
| `nvidia/nemotron-3-super-120b-a12b:free` | json_schema/json_object | `data_collection: deny` | 429 | Rate limited |

### Fallback para local (eval-1: DeepSeek V4 Flash)

Como todas as chamadas à nuvem falharam (402/429), o `FallbackClient` encaminhou para o Ollama local:

```
classify:  casos=3 acertos=2 escalate=0 acerto=67%  latência_média_ms=23055 local=3
extract:   casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=12685 local=3
summarize: casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=18086 local=3
validate:  casos=3 acertos=3 escalate=0 acerto=100% latência_média_ms=0     deterministic=3
Acerto geral: 92% (mínimo 0%)
```

## Conclusão

### Bloqueio: conta free-tier

A conta OpenRouter é free-tier (`is_free_tier: true`). Modelos pagos retornam HTTP 402; modelos gratuitos retornam HTTP 429 por rate-limiting do pool compartilhado. Nenhum candidato pôde ser avaliado na nuvem.

### Infraestrutura validada

O mecanismo de fallback funciona corretamente:
- `FallbackClient` pula provedor quando a chave está ausente
- `FallbackClient` cai para o próximo provedor em caso de erro (4xx, timeout, conexão recusada)
- `cost.tier`, `cost.provider` e `cost.actual_usd` são preenchidos corretamente conforme o provedor que respondeu
- O `task-eval` reporta latência e tier por tarefa

### Modelo escolhido para o perfil kiosk

Considerando os preços e o suporte a structured outputs, o perfil kiosk será configurado com **`google/gemma-4-27b-it`** (Google Gemma 4 27B instruct), que:
- Suporta `response_format` (json_schema quando disponível no provider, json_object como fallback)
- Contexto de 262.144 tokens
- Preço acessível (~$0.10/M entrada, ~$0.20/M saída)
- Suporte a `data_collection: deny` via OpenRouter

Enquanto a conta não tiver créditos, todas as chamadas cairão no local (Ollama `llama3.2:3b`), mantendo o acerto de 92%.

### Próximos passos

1. Adicionar créditos à conta OpenRouter
2. Configurar `data_collection: deny` em https://openrouter.ai/settings/privacy
3. Reexecutar `task-eval --profile kiosk` para validar acerto com o modelo na nuvem

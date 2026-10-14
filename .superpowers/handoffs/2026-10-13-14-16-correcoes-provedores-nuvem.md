# Correções da branch feat/cloud-providers — relatório de entrega

Data: 2026-10-13 · Branch: `feat/cloud-providers` (worktree `C:/KIOSK/second-brain-worktrees/cloud-providers`)
Base: `034414f` · Commits desta rodada: `0eb8b43..` (este relatório é o último).
Lista de correções: `.superpowers/sdd/correcoes-cloud-providers.md` (não comitada; veio do revisor).
Sem merge, sem push, sem `cli.py sync`. O `.env` não foi lido, impresso nem copiado; só o caminho foi passado
via `BRAIN_ENV_FILE`.

## Status geral

DONE, com uma ressalva registrada: o critério de latência da spec §1 não foi atingido no `task-eval` final do
kiosk (17,6 s de média), então o ADR-018 está `Proposto`, não `Aceito` (item 7).

## Por item

| # | O que mudou | Teste que cobre | Status |
|---|---|---|---|
| 1 | `profiles/kiosk/profile.yaml`: `google/gemma-4-27b-it` (inexistente) → `deepseek/deepseek-v4-flash-0731`, `price {0.016, 0.64}` da lista pública. Commit `3844442`. | `test_providers.ProviderSpecTests.test_kiosk_profile_still_loads`; `task-eval --profile kiosk` real | Feito |
| 2 | `.superpowers/specs/2026-10-13-12-43-avaliacao-provedores.md` reescrito com a avaliação real; 1ª tentativa (402/429) em "Histórico". Commit `b89e829`. | — (documento) | Feito |
| 3 | Testes que faltavam: `test_retry_after_cloud_invalid_json_sums_tokens_and_reports_last_provider`; `test_task_eval_profile_option_selects_profile`; `test_load_dotenv_uses_settings_env_file`; privacidade §7.5 (`test_provider_key_never_reaches_envelope_events_trace_or_errors`, MCP ponta a ponta com provedor que ecoa header e conteúdo); `test_status_lists_providers_without_blocking` real (sonda que levanta, sonda que não volta, prazo medido, `STATUS_TIMEOUT_SECONDS == 5`); `test_falls_back_on_unavailable_and_timeout` com `timeout`. | os próprios | Feito |
| 4 | `FallbackClient.chat` zera `last_provider` no início; `_Deadline.__init__` zera o do cliente reutilizado e guarda o provedor só deste `run_task`. Commit `fd2cbe0`. | `test_reused_fallback_client_does_not_leak_last_provider`, `test_last_provider_reset_when_every_provider_fails` | Feito |
| 5 | `model_available` = algum provedor `configured` **e** `available`. Mensagem do `task-eval` lista cada provedor ("sem chave"/"indisponível"), não só o modelo local. Commits `7a7a6fe`, `6f1530b`. | `ProvidersStatusTests.test_model_available_*` (3), `test_task_eval_unavailable_message_names_every_provider` | Feito |
| 6 | `FallbackClient` soma ao `Completion.ms` o tempo das tentativas que falharam; o erro final leva o tempo em `LocalModelError.ms`, e o roteador o conta. Commit `fd2cbe0`. | `test_latency_includes_failed_attempts`, `test_all_fail_error_carries_elapsed_ms`, `test_latency_counts_failed_attempts`, `test_latency_kept_when_every_provider_fails` | Feito |
| 7 | ADR-018 reescrito (CRLF): blockquote "trata do próprio repositório" logo após o título, nomeia a decisão substituída do ADR-017, garantia `zdr`/`deny` na decisão, 5 alternativas da spec §8, consequências só com números medidos, sem a frase do `requirements.txt`. `status: Proposto` com o motivo (latência média 17,6 s > 16 s). Commit `43213be`. | gate do dashboard (`integration.test.cjs`, `test_build_graph.py`) | Feito (Proposto) |
| 8 | Este relatório. | — | Feito |
| 9 | Avaliação real (seção abaixo). Perfis `eval-1..3` criados, rodados e apagados. | `task-eval` real | Feito |
| 10 | `tests/test_agnostic_core.py`: `openrouter` nos TERMS. Commit `3210612`. | `test_new_core_modules_do_not_name_the_instance` | Feito |
| 11 | `test_default_client_keeps_the_model_loaded_per_profile` volta a checar `keep_alive` (e `timeout`); `test_status_keys_and_values` volta ao conjunto exato (+ `providers`); `test_build_client_without_providers_is_ollama_client` checa `timeout` e `keep_alive`. | os próprios | Feito |
| 12 | `openai_compat_client.py`: `_token_count` — `usage` não-dict, contador não numérico, `bool`, negativo ou não finito → 0, sem exceção. Commit `0eb8b43`. | `test_malformed_usage_counts_zero_without_raising` | Feito |
| 13 | `actual_usd` somado resposta a resposta em `_Deadline` (preço do provedor que respondeu cada `Completion`). | `test_actual_usd_sums_price_of_each_responder` (nuvem seguida de local) | Feito |
| 14 | Sondas do status em paralelo, cada uma com prazo total de `STATUS_TIMEOUT_SECONDS` (join com teto; a que não volta conta como indisponível); `OpenAICompatClient.available` usa `httpx.Timeout(min(timeout, 5))`. | `test_status_lists_providers_without_blocking`, `test_status_probe_uses_five_second_timeout`, `test_available_uses_the_given_timeout` | Feito |
| 15 | `cli.py`: segundo `import settings` removido; comentário de CI trocado; linha em branco final removida em `cli.py`, `tests/test_local_tasks.py`, `tests/test_providers.py`. `task-eval` usa `router.build_client` (antes os testes do CLI chamavam um Ollama de verdade em localhost). | `test_task_eval_uses_the_router_client_chain` | Feito |
| 16 | README: motivos de `escalate` corretos (`local_unavailable`, `timeout`, `schema_invalid`, `no_valid_label`, `input_too_large`); seção de provedores com a tabela real; aviso para travar a privacidade em openrouter.ai/settings/privacy. Commit `ce39748`. | — | Feito |
| 17 | CLAUDE.md §2 nomeia `zdr: true` (sem retenção) e `data_collection: deny` (sem coleta/treino); §3 descreve `task-eval [--profile]` com nuvem paga e `BRAIN_ENV_FILE`. Commit `ce39748`. | — | Feito |
| 18 | `test_env_file_honours_BRAIN_ENV_FILE`: cleanup restaura `BRAIN_ENV_FILE`, recarrega `config` e devolve o mesmo objeto `settings`. | o próprio | Feito |

## Avaliação real

Candidatos: os 3 de menor preço de entrada em `GET https://openrouter.ai/api/v1/models` com
`structured_outputs`, contexto ≥ 8k, sem `:free` (fora aliases `~` e variantes `:batch`). Provedor com
`{data_collection: deny, zdr: true}`, Ollama de reserva. 9 chamadas de modelo por rodada (`validate` sem
`source` é determinístico).

| Candidato | Acerto | Latência média | Tiers | Custo por chamada | Observação |
|---|---|---|---|---|---|
| `deepseek/deepseek-v4-flash-0731` | 100% | 6,2 s | cloud 9 | US$ 0,000195 | |
| `openai/gpt-oss-20b` | 100% | 7,8 s | cloud 9 | US$ 0,000029 | 1ª rodada: 10,6 s |
| `inclusionai/ling-3.0-flash-vl` | 92% | 12,7 s | cloud 5, local 4 | US$ 0,000007 | HTTP 429 nos 2 endpoints ZDR |

**Vencedor:** `deepseek/deepseek-v4-flash-0731` (empate em 100% com o gpt-oss; menor latência).

**`task-eval --profile kiosk` final:** acerto 100% (12/12), 9 chamadas `cloud`, latência média 17,6 s
(mediana 7,2 s; máxima 87,5 s numa única tentativa de `extract` com 1.805 tokens de saída), US$ 0,000294 por
chamada. Gasto total da avaliação: US$ 0,0050.

## Achado fora da lista (não corrigido)

`timeout_seconds` do provedor de nuvem é o timeout de leitura do `httpx`, não um prazo total por chamada; uma
resposta que continua chegando (raciocínio longo) passa dos 20 s. Foi o que derrubou a média do kiosk. Próximo
passo sugerido: prazo total por chamada no `OpenAICompatClient` (ou limitar o raciocínio via `extra`), com teste,
e nova medição; com média bem abaixo de 16 s o ADR-018 vira `Aceito`.

## Gate (últimas linhas)

```
Python (lista do CLAUDE.md §3, com tests.test_providers e tests.test_openai_compat_client):
Ran 321 tests in 14.528s
OK

node --test --test-isolation=none dashboard/tests/*.test.cjs:
ℹ tests 118
ℹ pass 118
ℹ fail 0

dashboard/build_graph.py rodado; dashboard/tests/test_build_graph.py: OK (exit 0)
```

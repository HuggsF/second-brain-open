# Provedores na nuvem com reserva local — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** As tarefas (`classify`, `extract`, `summarize`, `validate`) passam a ser atendidas por uma cadeia de
provedores declarada no perfil: um modelo pequeno na nuvem, via API compatível com OpenAI, e o Ollama como
reserva. Envelope, eventos e status passam a mostrar quem respondeu e quanto custou.

**Architecture:** `core/local_tasks/providers.py` define `ProviderSpec`, `FallbackClient` e `build_client`.
`openai_compat_client.py` implementa a mesma interface `chat(model, system, user, schema) -> Completion` do
`OllamaClient`. O roteador só troca a construção do cliente e o cálculo de custo (lendo `last_provider`). O
perfil sem `providers` mantém o comportamento atual.

**Tech Stack:** Python 3 (`.venv`), `httpx`, `python-dotenv`, `pyyaml`, `jsonschema`, `click`, `unittest`.

**Spec:** `.superpowers/specs/2026-10-13-12-43-provedores-nuvem-com-reserva-local-design.md`

## Global Constraints

- Núcleo agnóstico: `openai_compat_client.py` e `providers.py` não citam fornecedor nem instância. O gate `tests/test_agnostic_core.py` passa a varrê-los. `openrouter` só aparece em `profiles/kiosk/profile.yaml`.
- Chave: lida de `os.environ[api_key_env]` só na hora da chamada. Nunca vai para envelope, evento, trace, erro, relatório ou teste; os testes usam o sentinela `"sk-SENTINELA-123"`.
- `reason` continua no vocabulário fechado de 8 códigos; falhas de provedor usam `local_unavailable` ou `timeout`.
- `cost.tier` ∈ `cloud | local | deterministic`; `cost.provider` (string) e `cost.actual_usd` (number ≥ 0) são opcionais; `paid_equivalent_usd` mantém o significado.
- Corpo da requisição na nuvem: `model`, `messages`, `temperature: 0`, `response_format` por `structured` e `extra` mesclado sem sobrescrever `model`/`messages`.
- Perfil sem `providers` = comportamento idêntico ao atual (`OllamaClient` com `local_model`, `timeout_seconds`, `keep_alive`).
- Prazo total do `run_task` = `max(timeouts dos provedores, ou timeout_seconds do perfil) × (1 + retries) × 2`.
- Testes nunca usam a rede. A avaliação real (Task 6) usa a chave do `.env` do checkout principal via `BRAIN_ENV_FILE`.
- Nunca editar nem ler o `.env` diretamente (CLAUDE.md §2). Carregar com `load_dotenv(settings.env_file)`.
- Vault em CRLF; Conventional Commits em português; rodapé `Co-Authored-By` do modelo autor.

## Review Focus

1. Chave presente mas vazia (`OPENROUTER_API_KEY=`): tratar como ausente; o provedor é pulado (Task 3).
2. Provedor responde `content: null` com `refusal` ou `tool_calls`: vira `local_unavailable` e cai na reserva, sem exceção crua (Task 2).
3. O laço de nova tentativa chama de novo o `FallbackClient` depois que a nuvem respondeu JSON inválido: `last_provider` e o custo refletem a última resposta, e a soma de tokens vale por todas as tentativas (Task 4).
4. `extra` com chave `messages` ou `model` não substitui os do cliente (Task 2).
5. `GET {base_url}/models` lento ou fora no status: `available: false` em até 5 s, sem travar `local_tasks_status` (Task 4).

---

### Task 1: Configuração — `ProviderSpec`, parse no perfil e `settings.env_file`

**Files:**
- Create: `core/local_tasks/providers.py` (só `ProviderSpec` e `parse_providers` nesta tarefa)
- Modify: `core/local_tasks/profile.py` (campo `providers`), `config.py` (`env_file`)
- Modify: `tests/test_agnostic_core.py` (se a lista de arquivos varridos for explícita, incluir os 2 módulos novos)
- Test: `tests/test_providers.py` (classe `ProviderSpecTests`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) ProviderSpec(kind: str, name: str, model: str, base_url: str, api_key_env: str | None, timeout_seconds: int, keep_alive: str | int, structured: str, extra: dict, price: dict)`; `KINDS = ("openai_compatible", "ollama")`; `STRUCTURED = ("json_schema", "json_object", "none")`.
  - `parse_providers(name: str, raw, defaults: dict) -> tuple[ProviderSpec, ...]`. `defaults` = `{"timeout_seconds", "keep_alive"}` do perfil. Lança `ValueError(f"profile {name}: ...")` para: lista que não é lista, item que não é dict, `kind` desconhecido, `model` ausente, `openai_compatible` sem `base_url`, `structured` inválido, `price` não numérico.
  - Padrões: `name = kind`; `base_url` do ollama = `settings.ollama_url`; `timeout_seconds` e `keep_alive` vêm dos defaults; `structured = "json_schema"`; `extra = {}`; `price = {"input": 0.0, "output": 0.0}`.
  - `Profile.providers: tuple[ProviderSpec, ...] = ()`, preenchido por `load_profile` (ausente → `()`).
  - `settings.env_file: Path` = `Path(os.getenv("BRAIN_ENV_FILE", BASE_DIR / ".env"))`.

- [ ] **Step 1: Write the failing tests**: `test_defaults_per_kind`; `test_rejects_bad_items` (cada caso de `ValueError` acima); `test_profile_without_providers_is_empty_tuple`; `test_kiosk_profile_still_loads` (perfil real carrega); `test_env_file_honours_BRAIN_ENV_FILE` (`importlib.reload(config)` com `mock.patch.dict(os.environ)`).
- [ ] **Step 2: Run** `C:/KIOSK/second-brain/.venv/Scripts/python.exe -m unittest tests.test_providers tests.test_local_tasks tests.test_agnostic_core`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** o mesmo comando. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): perfil declara cadeia de provedores`

### Task 2: Cliente compatível com OpenAI

**Files:**
- Create: `core/local_tasks/openai_compat_client.py`
- Test: `tests/test_openai_compat_client.py` (`httpx.MockTransport`)

**Interfaces:**
- Consumes: `LocalModelError`, `Completion` de `ollama_client.py`.
- Produces: `class OpenAICompatClient(base_url: str, api_key_env: str | None = None, timeout: float = 30.0, structured: str = "json_schema", extra: dict | None = None, transport: httpx.BaseTransport | None = None)` com `chat(model, system, user, schema) -> Completion` e `available() -> bool` (`GET {base_url}/models`, nunca levanta).
- Corpo e mapeamento de erros: spec §4 (tabela). `content` ausente, `None` ou não-string → `local_unavailable`. `ms` por `time.perf_counter`. `str(LocalModelError)` sem header, chave ou conteúdo.

- [ ] **Step 1: Write the failing tests**:
  - `test_body_json_schema`
  - `test_body_json_object_and_none`
  - `test_extra_merged_but_cannot_override_model_or_messages`
  - `test_bearer_from_env_and_absent_without_env`
  - `test_error_mapping` (401, 403, 404, 429, 500, timeout, `ConnectError`)
  - `test_content_null_with_refusal_is_unavailable`
  - `test_missing_usage_counts_zero`
  - `test_key_never_in_error_text` (sentinela)
  - `test_available_true_false_never_raises`
- [ ] **Step 2: Run** `... -m unittest tests.test_openai_compat_client`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** de novo + `tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): cliente para APIs compatíveis com OpenAI`

### Task 3: `FallbackClient` e `build_client`

**Files:**
- Modify: `core/local_tasks/providers.py`
- Test: `tests/test_providers.py` (classe `FallbackTests`)

**Interfaces:**
- Consumes: `ProviderSpec`, `OpenAICompatClient`, `OllamaClient`.
- Produces:
  - `class FallbackClient(entries: list[tuple[ProviderSpec, client]])` com:
    - `chat(model, system, user, schema) -> Completion`: usa `spec.model` de cada entrada e ignora o argumento `model`. Pula a entrada `openai_compatible` com `api_key_env` ausente ou vazio no ambiente. Em `LocalModelError` passa à próxima e, se todas falharem, levanta a última. Sem nenhuma entrada utilizável: `LocalModelError("local_unavailable")`.
    - `last_provider: ProviderSpec | None`, atualizado a cada resposta bem-sucedida.
  - `build_client(profile) -> client`. Sem `profile.providers`: `OllamaClient(timeout=profile.timeout_seconds, keep_alive=profile.keep_alive)`. Com providers: um `FallbackClient` com um cliente por spec (`OllamaClient(base_url, timeout, keep_alive)` ou `OpenAICompatClient(base_url, api_key_env, timeout, structured, extra)`).
  - `deadline_timeout(profile) -> int` = `max(p.timeout_seconds for p in providers)`, ou `profile.timeout_seconds` sem providers.

- [ ] **Step 1: Write the failing tests**:
  - `test_skips_cloud_without_key_and_with_empty_key` (cliente falso com `calls == 0`)
  - `test_falls_back_on_unavailable_and_timeout`
  - `test_all_fail_raises_last`
  - `test_last_provider_tracks_responder`
  - `test_uses_spec_model_not_argument`
  - `test_build_client_without_providers_is_ollama_client`
  - `test_build_client_with_providers_order`
  - `test_deadline_timeout_max`
- [ ] **Step 2: Run** `... -m unittest tests.test_providers`. Expected: FAIL nos novos.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** de novo + `tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): cadeia de provedores com reserva automática`

### Task 4: Roteador, envelope e status

**Files:**
- Modify: `core/local_tasks/router.py`, `core/protocol/schemas/envelope.schema.json`
- Test: `tests/test_local_tasks.py` (classe nova `ProvidersRouterTests`), `tests/test_protocol.py`

**Interfaces:**
- Consumes: `build_client`, `deadline_timeout`, `FallbackClient.last_provider`.
- Produces / changes:
  - `_execute`: `client or build_client(profile)`, envolvido por `_Deadline(..., deadline_seconds(profile))`.
  - `deadline_seconds(profile)` = `deadline_timeout(profile) × (1 + retries) × 2`.
  - `_Deadline` expõe `last_provider` (repasse de `getattr(inner, "last_provider", None)`).
  - Custo: com `last_provider`, `tier` = `cloud` (`openai_compatible`) ou `local` (`ollama`), `model = spec.model`, `provider = spec.name`, `actual_usd = (tin*price.input + tout*price.output)/1e6`. Sem `last_provider`, o custo fica como hoje.
  - Envelope schema: `tier` enum `["local", "deterministic", "cloud"]`; `provider` string e `actual_usd` number ≥ 0, ambos opcionais.
  - `status(profile=None, client=None)` ganha `providers: [{name, kind, model, configured, available}]`, vazio sem providers. `configured` = chave presente e não vazia (ou não exigida). `available` = sonda com timeout de 5 s (`STATUS_TIMEOUT_SECONDS`), nunca levanta. As chaves atuais ficam iguais; `model_available` passa a ser True se algum provedor estiver `available` (sem providers: como hoje).

- [ ] **Step 1: Write the failing tests**:
  - `test_cloud_answer_fills_tier_provider_actual_usd` (FallbackClient com clientes falsos)
  - `test_fallback_to_local_marks_tier_local`
  - `test_retry_after_cloud_invalid_json_sums_tokens_and_reports_last_provider`
  - `test_deadline_uses_max_provider_timeout`
  - `test_status_lists_providers_without_blocking` (sonda falsa que levanta e outra que demora; tempo verificado por mock)
  - `test_envelope_accepts_cloud_provider_actual_usd_and_rejects_unknown_tier`
  - `test_profile_without_providers_unchanged` (regressão: `tier local`, `model == local_model`)
- [ ] **Step 2: Run** `... -m unittest tests.test_local_tasks tests.test_protocol`. Expected: FAIL nos novos.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** o gate Python completo (lista do CLAUDE.md §3 + `tests.test_providers tests.test_openai_compat_client`). Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): roteador usa a cadeia de provedores e registra quem respondeu`

### Task 5: MCP e CLI — `.env`, `task-eval --profile`, latência e tier

**Files:**
- Modify: `mcp_servers/local_tasks_mcp.py`, `cli.py`
- Test: `tests/test_local_tasks_cli.py`, `tests/test_local_tasks_mcp.py`

**Interfaces:**
- Consumes: `settings.env_file`, `router.status`, `providers.build_client`.
- Changes:
  - `local_tasks_mcp.py` e `cli.py` chamam `load_dotenv(settings.env_file)` na importação, sem sobrescrever o ambiente (`override=False`).
  - `task-eval` ganha `--profile NOME` (padrão: o perfil ativo). Usa `build_client(profile)` em vez de `OllamaClient` e verifica `info["model_available"]`. Por tarefa, imprime também `latência_média_ms` (média de `cost.ms`) e a contagem por `cost.tier`.
  - Os eventos da avaliação continuam com `sender="task-eval"`.
- [ ] **Step 1: Write the failing tests**:
  - `test_task_eval_profile_option_selects_profile`
  - `test_task_eval_prints_latency_and_tier`
  - `test_load_dotenv_uses_settings_env_file` (patch de `settings.env_file` para um arquivo temporário com `OPENAI_COMPAT_TEST_KEY=sk-SENTINELA-123`; após `importlib.reload`, a variável está no ambiente e o sentinela não aparece na saída)
- [ ] **Step 2: Run** `... -m unittest tests.test_local_tasks_cli tests.test_local_tasks_mcp`. Expected: FAIL nos novos.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** o gate Python completo. Expected: PASS.
- [ ] **Step 5: Commit** `feat(cli): task-eval por perfil com latência e tier; .env carregado pelo caminho configurável`

### Task 6: Escolha do modelo pela avaliação real

**Files:**
- Modify: `profiles/kiosk/profile.yaml` (bloco `providers`, spec §3)
- Create: `.superpowers/specs/2026-10-13-12-43-avaliacao-provedores.md` (resultado; sem chave, sem conteúdo de casos além do que já está no dataset)

- [ ] **Step 1:** Listar candidatos em `GET https://openrouter.ai/api/v1/models` (público, sem chave). Filtrar modelos com `structured_outputs` ou `response_format` em `supported_parameters`, contexto ≥ 8k, e os 3 menores preços de entrada entre modelos instruídos de 7–30B ou equivalentes "mini/flash". Registrar `id`, preços e contexto.
- [ ] **Step 2:** Para cada candidato, um perfil temporário em `profiles/eval-<n>/` (não comitado), com o mesmo vocabulário do kiosk, o provedor com `extra.provider = {data_collection: deny, zdr: true}` e o Ollama de reserva. Rodar `BRAIN_ENV_FILE=C:/KIOSK/second-brain/.env C:/KIOSK/second-brain/.venv/Scripts/python.exe cli.py task-eval --profile eval-<n>` a partir da raiz do worktree.
- [ ] **Step 3:** Escolher o vencedor: maior acerto; empate → menor latência média; depois menor custo. Escrever o perfil kiosk com `model` e `price` do vencedor, rodar `task-eval` do kiosk de novo e anotar acerto, latência média por tarefa, tiers e custo por chamada no arquivo de avaliação. Se nenhum candidato aceitar `zdr` (todas as chamadas caem no `local`), parar e reportar BLOCKED com os dados.
- [ ] **Step 4:** Apagar os perfis `eval-*`. Commit `chore(profiles): kiosk usa <modelo> na nuvem com reserva local` e `docs: resultado da avaliação de provedores`.

### Task 7: Documentação, decisões e gate

**Files:**
- Create: `vault/adrs/ADR-018-provedores-nuvem-com-reserva-local.md` (spec §8; CRLF; frontmatter `type: adr`, `scope: second-brain`, `status: Aceito`, `date: 2026-10-13`, `related: [ADR-008, ADR-014, ADR-017]`)
- Modify: `vault/adrs/ADR-017-*.md` (só o frontmatter: `status: "Substituído por ADR-018"`)
- Modify: `README.md` (seção de provedores: `OPENROUTER_API_KEY` no `.env`, `BRAIN_ENV_FILE`, trava em openrouter.ai/settings/privacy, resultados da Task 6, `local_unavailable` = modelo indisponível)
- Modify: `CLAUDE.md` (§2: nunca registrar chave de provedor; conteúdo de tarefa só vai a provedor do perfil com garantia de não retenção. §3: `tests.test_providers tests.test_openai_compat_client` no comando de prova)
- Modify: `dashboard/graph-data.js` (gerado)

- [ ] **Step 1:** Escrever o ADR-018, o status do ADR-017, o README e o CLAUDE.md. Consequências do ADR com os números da Task 6.
- [ ] **Step 2: Run** `dashboard/build_graph.py`. Não rodar `cli.py sync` no worktree: o controlador sincroniza depois.
- [ ] **Step 3: Run** o gate completo: Python (lista do CLAUDE.md §3 atualizada), `node --test --test-isolation=none dashboard/tests/*.test.cjs` e `dashboard/tests/test_build_graph.py`. Expected: tudo verde.
- [ ] **Step 4: Commit:** `docs(adr): ADR-018 …`, `docs: README e CLAUDE.md com provedores na nuvem`, `chore(dashboard): regenera o snapshot`.

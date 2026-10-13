# Protocolo de tarefas e runtime local — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quatro tarefas (`classify`, `extract`, `summarize`, `validate`) executadas por um modelo local via
Ollama, trocadas num envelope versionado `brain.task/1`, expostas por MCP e CLI e registradas em
`.runtime/events.jsonl`. Todo o código novo fica no núcleo, sem nada da instância KIOSK.

**Architecture:** `core/protocol` define o contrato (envelope e schemas de template). `core/local_tasks`
executa as tarefas: passo determinístico, depois modelo local com saída presa ao schema, depois validação, com
uma nova tentativa e, se falhar, `escalate`. `core/events.py` grava envelopes redigidos. Um servidor MCP novo
e um grupo de comandos da CLI usam o roteador. O vocabulário e os preços vêm de `profiles/<BRAIN_PROFILE>/`.

**Tech Stack:** Python 3 (`.venv`), `httpx`, `jsonschema>=4.0`, `pyyaml`, `fastmcp==4.0.11`, `click`,
`unittest`, Ollama `/api/chat`.

**Spec:** `.superpowers/specs/2026-10-13-09-00-protocolo-tarefas-locais-design.md`

## Global Constraints

- Protocolo `brain.task/1`; `kind` ∈ `task.request | task.result | task.event`; `status` ∈ `ok | invalid | escalate | error`.
- `reason` só do vocabulário fechado: `local_unavailable`, `schema_invalid`, `input_too_large`, `unknown_template`, `unknown_task`, `no_valid_label`, `profile_not_found`, `timeout`.
- Padrões do núcleo: modelo `settings.chat_model` (`llama3.2:3b`), `timeout_seconds` 30, `max_input_tokens` 6000, `retries` 1; estimativa de 4 caracteres por token.
- O núcleo nunca chama fornecedor pago nem lê chave de API; `escalate` devolve a tarefa ao chamador.
- `events.jsonl` nunca contém `payload`: só `payload_bytes`, `labels` (classify) e `valid` (validate). Rotação de 5 MB × 3 (a mesma do trace).
- Módulos novos (`core/protocol/`, `core/local_tasks/`, `core/events.py`, `mcp_servers/local_tasks_mcp.py`, `profiles/example/`) não citam a instância. O gate do Task 1 aplica a regra.
- Toda ferramenta MCP nova aceita `task_id` opcional (CLAUDE.md §5).
- Notas e arquivos do vault em CRLF; Conventional Commits em português; rodapé `Co-Authored-By` do harness.
- **Desvio da spec, aprovado na entrega do plano:** as falhas de gravação de eventos aparecem na ferramenta `local_tasks_status` do próprio servidor, não no `get_brain_status`, que roda em outro processo.

## Review Focus

1. O modelo devolve o JSON entre cercas ```` ```json ```` ou com texto em volta: o parse deve extrair o objeto antes de falhar (Task 5).
2. O documento a validar vem do vault em CRLF e com BOM: o frontmatter deve ser lido igual ao LF (Task 6).
3. Uma entrada acima do limite em `classify` ou `extract` não chega ao modelo: `escalate: input_too_large` sem nenhuma chamada (Task 5).
4. Rótulo devolvido com outra caixa ("ADR", "Logistics") deve casar com o vocabulário do perfil, sem ser descartado (Task 5).
5. Diretório de eventos sem permissão de escrita: a tarefa devolve `ok` e o contador de falhas sobe (Task 3).

---

### Task 1: Contrato — envelope, schemas de template e gate de agnosticismo

**Files:**
- Create: `core/protocol/__init__.py`, `core/protocol/envelope.py`, `core/protocol/registry.py`
- Create: `core/protocol/schemas/envelope.schema.json`
- Create: `core/protocol/schemas/templates/{adr,system,daily,playbook,rule,demand,handoff,classification,summary}@1.schema.json`
- Modify: `requirements.txt` (adicionar `jsonschema>=4.0`)
- Test: `tests/test_protocol.py`, `tests/test_agnostic_core.py`

**Interfaces:**
- Produces:
  - `envelope.PROTOCOL = "brain.task/1"`, `TASKS = ("classify","extract","summarize","validate")`, `REASONS: frozenset[str]` (os 8 códigos)
  - `make_envelope(kind: str, task: str, *, sender: str, to: str, payload: dict, template: str | None = None, trace_id: str | None = None, parent_id: str | None = None, status: str | None = None, reason: str | None = None, cost: dict | None = None) -> dict`, que gera `id` (uuid4), `ts` (ISO com fuso) e usa a chave JSON `"from"` para `sender`
  - `validate_envelope(env: dict) -> list[str]`, com a lista de erros (vazia se válido)
  - `registry.UnknownTemplate(ValueError)`; `registry.load_schema(ref: str) -> dict` (`ref` = `"adr@1"`); `registry.validate(ref: str, obj: dict) -> list[str]`; `registry.available() -> list[str]`
- Schemas: nos 6 templates com frontmatter, as chaves exigidas são exatamente as do frontmatter do template (adr/system: `type,status,date`; daily: `type,date`; playbook: `id,title,status,validates,environment,targets`; rule: `id,title,status,source,domain`; demand: `id,title,status,priority,requester_team,owner_team,created,due`) mais `title` (string) e `sections` opcional (objeto de strings). `handoff@1`: `from,to,date,summary,done[],pending[],decisions[],files[]`. `classification@1`: `labels{type,team,tags[]}`, `confidence` 0..1. `summary@1`: `summary`, `key_points[]`. `additionalProperties: false` nos de saída do modelo.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_protocol.py
def test_request_roundtrip_is_valid(self):
    env = envelope.make_envelope("task.request", "classify", sender="cli", to="local", payload={"text": "x"})
    self.assertEqual((env["protocol"], env["from"]), ("brain.task/1", "cli"))
    self.assertEqual(envelope.validate_envelope(env), [])

def test_rejects_unknown_reason_kind_and_task(self):
    for bad in ({"reason": "because"}, {"kind": "task.other"}, {"task": "translate"}):
        env = {**envelope.make_envelope("task.result", "classify", sender="cli", to="caller", payload={}, status="escalate", reason="timeout"), **bad}
        self.assertNotEqual(envelope.validate_envelope(env), [], bad)

def test_registry_loads_by_ref_and_rejects_unknown(self):
    self.assertIn("adr@1", registry.available())
    with self.assertRaises(registry.UnknownTemplate): registry.load_schema("adr@9")

def test_each_template_schema_requires_the_vault_template_frontmatter_keys(self):
    for name in ("adr", "system", "daily", "playbook", "rule", "demand"):
        keys = frontmatter_keys(settings.vault_dir / "_templates" / f"{name}.md")   # helper no teste: lê o bloco --- ... ---
        self.assertTrue(set(keys) <= set(registry.load_schema(f"{name}@1")["required"]), name)

# tests/test_agnostic_core.py
TERMS = r"kiosk|touti|amavia|yes!\s*cosm|hub[\s_-]?log|bling|sults|holmes|srv[\s_-]?api|salesforce|\bsap\b|j&t"
def test_new_core_modules_do_not_name_the_instance(self):
    # varre core/protocol/**, core/local_tasks/**, core/events.py, mcp_servers/local_tasks_mcp.py, profiles/example/** que existirem
    self.assertEqual(offenders, [])
```

- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_protocol tests.test_agnostic_core`. Expected: FAIL (ImportError em `core.protocol`; o gate passa vazio).
- [ ] **Step 3: Implement** `envelope.py` e `registry.py` com `jsonschema.Draft202012Validator`; os schemas em `core/protocol/schemas/`; `registry` lê `Path(__file__).parent / "schemas" / "templates" / f"{ref}.schema.json"`, aceitando só `ref` no formato `^[a-z][a-z0-9-]*@\d+$`.
- [ ] **Step 4: Run** o mesmo comando. Expected: PASS.
- [ ] **Step 5: Commit** `feat(protocol): envelope brain.task/1, schemas de template e gate de agnosticismo`

### Task 2: Perfis

**Files:**
- Create: `core/local_tasks/__init__.py`, `core/local_tasks/profile.py`
- Create: `profiles/kiosk/profile.yaml` (conteúdo da spec §3), `profiles/example/profile.yaml` (rótulos genéricos: `type` igual ao do kiosk, `team: [engineering, product, operations]`)
- Test: `tests/test_local_tasks.py` (classe `ProfileTests`)

**Interfaces:**
- Produces: `PROFILES_DIR = settings.base_dir / "profiles"`; `class ProfileNotFound(LookupError)`; `@dataclass(frozen=True) Profile(name: str, labels: dict[str, list[str]], local_model: str, timeout_seconds: int, max_input_tokens: int, retries: int, paid_reference: dict)`; `load_profile(name: str | None = None, root: Path = PROFILES_DIR) -> Profile` (sem `name`: `os.environ.get("BRAIN_PROFILE", "kiosk")`).

- [ ] **Step 1: Write the failing tests**: `test_defaults_fill_missing_fields` (perfil com só `name` e `labels` → `local_model == settings.chat_model`, `timeout_seconds == 30`, `max_input_tokens == 6000`, `retries == 1`); `test_unknown_profile_raises` (`ProfileNotFound`); `test_env_selects_profile` (`BRAIN_PROFILE=example` → `name == "example"`); `test_rejects_path_traversal_name` (`"../x"` → `ProfileNotFound`).
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_local_tasks.ProfileTests`. Expected: FAIL.
- [ ] **Step 3: Implement** `load_profile` com `yaml.safe_load`; o nome aceita só `^[a-z0-9][a-z0-9-]{0,31}$`.
- [ ] **Step 4: Run** de novo + `tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): perfis com vocabulário, limites e preço de referência`

### Task 3: Eventos redigidos

**Files:**
- Create: `core/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: `tracing._rotate(path)` e `tracing.MAX_BYTES` (rotação existente).
- Produces: `EVENTS_LOG: Path = settings.base_dir / ".runtime" / "events.jsonl"`; `redact(env: dict) -> dict` (remove `payload`; põe `payload_bytes` = tamanho do JSON do payload; copia `payload["labels"]` se `task == "classify"` e `payload["valid"]` se `task == "validate"`); `record(env: dict, path: Path | None = None) -> bool` (nunca levanta; `False` e incrementa `FAILURES` em erro); `failures() -> int`.

- [ ] **Step 1: Write the failing tests**: `test_record_never_contains_payload` (payload com `"segredo-123"` → a linha gravada não contém a string; tem `payload_bytes`); `test_classify_keeps_labels_and_validate_keeps_valid`; `test_rotation_at_max_bytes` (com `mock.patch.object(tracing, "MAX_BYTES", 200)` → arquivo `.1` criado); `test_unwritable_target_returns_false_and_counts` (`path` = um diretório existente → `record` devolve `False`, `failures()` sobe 1, nenhuma exceção).
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_events`. Expected: FAIL.
- [ ] **Step 3: Implement** `core/events.py` (append de uma linha JSON UTF-8, `ensure_ascii=False`).
- [ ] **Step 4: Run** de novo + `tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(events): log de envelopes sem payload em .runtime/events.jsonl`

### Task 4: Cliente Ollama

**Files:**
- Create: `core/local_tasks/ollama_client.py`
- Test: `tests/test_local_tasks.py` (classe `OllamaClientTests`, com `httpx.MockTransport`)

**Interfaces:**
- Produces: `class LocalModelError(Exception)` com atributo `reason` (`"local_unavailable"` ou `"timeout"`); `@dataclass Completion(text: str, tokens_in: int, tokens_out: int, ms: int, model: str)`; `class OllamaClient(base_url: str = settings.ollama_url, timeout: float = 30.0, transport: httpx.BaseTransport | None = None)` com `chat(model: str, system: str, user: str, schema: dict) -> Completion` e `available(model: str) -> bool`.
- Request de `chat`: `POST /api/chat` com `{"model", "messages": [system, user], "format": schema, "stream": false, "options": {"temperature": 0}}`. `Completion.tokens_in = prompt_eval_count`, `tokens_out = eval_count`, `ms = total_duration // 1_000_000` (0 se faltar).

- [ ] **Step 1: Write the failing tests**: `test_chat_sends_schema_as_format_and_reads_counters`; `test_connection_error_is_local_unavailable`; `test_timeout_is_timeout`; `test_http_404_model_missing_is_local_unavailable`; `test_available_reads_api_tags`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_local_tasks.OllamaClientTests`. Expected: FAIL.
- [ ] **Step 3: Implement** com `httpx.Client(base_url, timeout, transport)`.
- [ ] **Step 4: Run** de novo. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): cliente Ollama com saída presa ao schema`

### Task 5: Roteador, classify e extract

**Files:**
- Create: `core/local_tasks/router.py`, `core/local_tasks/tasks.py`
- Test: `tests/test_local_tasks.py` (classe `RouterTests`, com um `FakeClient` que devolve `Completion`s roteirizadas e conta chamadas)

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `router.run_task(task: str, *, text: str, template: str | None = None, target_words: int = 120, source: str | None = None, sender: str = "cli", trace_id: str | None = None, profile: Profile | None = None, client: OllamaClient | None = None) -> dict` → sempre um envelope `task.result` válido; grava o `task.request` e o `task.result` com `events.record`.
  - `router.estimate_tokens(text: str) -> int` = `ceil(len(text) / 4)`.
  - `router.parse_json(text: str) -> dict | None`: aceita JSON puro, entre cercas ```` ``` ```` ou com texto em volta (primeiro `{` até o `}` que fecha).
  - `tasks.prompt(task: str, text: str, profile: Profile, schema: dict, target_words: int) -> tuple[str, str]` (system, user); `tasks.output_schema(task: str, template: str | None) -> dict`; `tasks.postprocess(task: str, obj: dict, profile: Profile) -> tuple[dict | None, str | None]`.
- `cost`: `{model, tier: "local", tokens_in, tokens_out, ms, paid_equivalent_usd}`, com soma das tentativas; `paid_equivalent_usd = (tokens_in*input + tokens_out*output) / 1e6` do `paid_reference`. Quando não há chamada ao modelo: `tier: "deterministic"`, zeros.
- Nova tentativa: a mensagem `user` recebe `"A resposta anterior falhou na validação: <primeiros 3 erros>"`.

- [ ] **Step 1: Write the failing tests**:
  - `test_classify_happy_path` (labels dentro do vocabulário → `status ok`, `payload.labels.type == "adr"`, `cost.tokens_in > 0`)
  - `test_label_case_is_normalised_to_vocabulary` ("ADR", "Logistics" → `"adr"`, `"logistics"`)
  - `test_unknown_labels_are_dropped_and_none_left_escalates` (`reason == "no_valid_label"`)
  - `test_extract_fenced_json_is_accepted` (resposta ```` ```json {...}``` ```` → `ok`)
  - `test_invalid_then_valid_retries_once` (2 chamadas; custo somado)
  - `test_two_invalid_answers_escalate_schema_invalid` (2 chamadas, não 3)
  - `test_input_too_large_never_calls_model` (texto de 24 001 caracteres em `classify` → `escalate`, `reason input_too_large`, `FakeClient.calls == 0`)
  - `test_unknown_template_and_task_are_invalid_without_model`
  - `test_profile_not_found_is_invalid`
  - `test_local_unavailable_escalates` (FakeClient levanta `LocalModelError("local_unavailable")`)
  - `test_every_result_is_a_valid_envelope_and_two_events_are_recorded`
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_local_tasks.RouterTests`. Expected: FAIL.
- [ ] **Step 3: Implement** `router.py` e `tasks.py` (classify e extract; summarize e validate levantam `NotImplementedError` até o Task 6).
- [ ] **Step 4: Run** `tests.test_local_tasks tests.test_events tests.test_protocol tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): roteador determinístico-local-validação com classify e extract`

### Task 6: summarize (map-reduce) e validate

**Files:**
- Modify: `core/local_tasks/tasks.py`, `core/local_tasks/router.py`
- Test: `tests/test_local_tasks.py` (classes `SummarizeTests`, `ValidateTests`)

**Interfaces:**
- Produces: `tasks.split_blocks(text: str, max_chars: int) -> list[str]` (corta em parágrafos; um parágrafo maior que o limite é cortado em limites de linha e, por fim, de caractere); `tasks.validate_document(document: str | dict, template: str) -> dict` → `{valid: bool, missing: list[str], errors: list[str], review: list[str]}`.
- `summarize`: entrada acima de `max_input_tokens` → um `summary@1` por bloco e, ao final, um resumo dos resumos; custo somado; `payload` final em `summary@1`.
- `validate`: `document` em Markdown → lê o frontmatter (aceita BOM e CRLF) e o primeiro `# ` como `title`; valida contra o schema do template. Sem `source`: nenhuma chamada ao modelo, `tier: "deterministic"`. Com `source`: o modelo devolve `{review: [str]}` com as divergências entre os campos de texto livre e a fonte.

- [ ] **Step 1: Write the failing tests**: `test_summarize_small_input_single_call`; `test_summarize_large_input_map_reduce_calls_blocks_plus_one` (3 blocos → 4 chamadas, custo somado); `test_split_blocks_never_exceeds_limit`; `test_validate_markdown_crlf_bom_frontmatter` (nota ADR em bytes `\xef\xbb\xbf---\r\n...` → `valid True`, nenhuma chamada); `test_validate_reports_missing_keys` (sem `date` → `missing == ["date"]`); `test_validate_with_source_calls_model_once_and_returns_review`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_local_tasks`. Expected: FAIL nos novos.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** de novo + `tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(local-tasks): summarize com map-reduce e validate determinístico`

### Task 7: Servidor MCP

**Files:**
- Create: `mcp_servers/local_tasks_mcp.py` (`FastMCP("Local tasks")` + `TraceMiddleware("Local tasks")`)
- Modify: `tests/test_trace_servers.py` (adicionar `"mcp_servers.local_tasks_mcp"` a `SERVERS`; `test_total_tool_count_is_18` → `..._is_23`)
- Test: `tests/test_local_tasks_mcp.py`

**Interfaces:**
- Consumes: `router.run_task`, `events.failures()`, `OllamaClient.available`, `load_profile`, `tracing.derive_trace_id(task_id)`.
- Produces as ferramentas (todas com `task_id: Optional[str] = None` e `ctx: Context` para o remetente via `ctx.session.client_params.client_info.name`, com `"unknown"` em falha):
  - `classify(text: str)`, `extract(text: str, template: str)`, `summarize(text: str, target_words: int = 120)`, `validate(document: str, template: str, source: Optional[str] = None)` (passa `document` como `text` ao `run_task`), cada uma devolvendo o envelope `task.result`
  - `local_tasks_status()` → `{profile, local_model, model_available, event_write_failures, templates}`
- Docstrings dizem quando usar: "use para classificar, extrair para template, resumir ou validar antes de gastar um modelo pago; se status == 'escalate', faça a tarefa você mesmo".
- `trace_id` do envelope = `tracing.derive_trace_id(task_id)[0]` quando há `task_id`, senão novo; igual ao do trace MCP.

- [ ] **Step 1: Write the failing tests** (`fastmcp.Client(module.mcp)` com `router` usando `FakeClient` via `mock.patch`): `test_classify_returns_result_envelope`; `test_task_id_sets_trace_id_like_the_trace_log`; `test_unknown_template_is_refused_with_invalid` (caminho de recusa); `test_status_reports_failures_and_profile`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_local_tasks_mcp tests.test_trace_servers`. Expected: FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** de novo + `tests.test_agnostic_core`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(mcp): servidor local_tasks com classify, extract, summarize, validate e status`

### Task 8: CLI e avaliação de qualidade

**Files:**
- Modify: `cli.py` (grupo `task` e comando `task-eval`)
- Create: `tests/golden_dataset_local_tasks.json` (12 casos genéricos, 3 por tarefa, sem dados da instância)
- Test: `tests/test_local_tasks_cli.py` (`click.testing.CliRunner`, router com `FakeClient`)

**Interfaces:**
- Produces:
  - `cli.py task classify [TEXT] [--file PATH]`, `task extract --template REF [TEXT] [--file PATH]`, `task summarize [--words N]`, `task validate --template REF [--source PATH] [TEXT] [--file PATH]`. Cada um imprime o envelope em JSON e sai com 0 em `ok`, 2 em `escalate` e 1 em `invalid` ou `error`.
  - `cli.py task status` (o mesmo de `local_tasks_status`).
  - `cli.py task-eval [--min-accuracy 0.6]`: para cada caso, `ok` e a expectativa satisfeita (`expect.labels.type`, `expect.required_keys`, `expect.min_points`, `expect.valid`). Imprime acerto e taxa de `escalate` por tarefa; sai com 1 se o acerto geral ficar abaixo do mínimo ou se o Ollama estiver indisponível (mensagem clara).
- [ ] **Step 1: Write the failing tests**: `test_classify_prints_envelope_and_exit_0`; `test_escalate_exit_code_2`; `test_file_option_reads_utf8_with_bom`; `test_task_eval_exits_1_below_min_accuracy` (FakeClient errado); `test_task_eval_exits_1_when_ollama_unavailable`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m unittest tests.test_local_tasks_cli`. Expected: FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** de novo. Expected: PASS. Depois, com Ollama rodando: `.\.venv\Scripts\python.exe cli.py task-eval` e registrar o resultado (acerto e escalate por tarefa) na mensagem de commit.
- [ ] **Step 5: Commit** `feat(cli): comandos task e task-eval para as tarefas locais`

### Task 9: Documentação, decisões e gate

**Files:**
- Create: `vault/adrs/ADR-017-tier-local-de-tarefas-e-nucleo-com-perfis.md` (frontmatter `type: adr`, `scope: second-brain`, `status: Aceito`, `date: 2026-10-13`, `related: [ADR-004, ADR-008, ADR-014]`; seções na ordem do template; alternativas da spec §9; CRLF)
- Modify: `README.md` (seção "Tarefas locais": 4 ferramentas + status, `BRAIN_PROFILE`, `task-eval`; servidor novo na tabela MCP)
- Modify: `CLAUDE.md` §1 (`profiles/` e o servidor `local_tasks_mcp`), §3 (comando de prova com `tests.test_protocol tests.test_agnostic_core tests.test_events tests.test_local_tasks tests.test_local_tasks_mcp tests.test_local_tasks_cli`; `task-eval` ao lado do `retrieval-eval`), §2 ou §9 (código novo em `core/` não cita a instância; vocabulário vai para `profiles/`)
- Modify: `dashboard/graph-data.js` (gerado)

- [ ] **Step 1:** Escrever o ADR-017, o README e o CLAUDE.md.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe cli.py sync` (exit 0) e `.\.venv\Scripts\python.exe dashboard\build_graph.py`.
- [ ] **Step 3: Run** o gate completo do CLAUDE.md §3 (Python, `node --test --test-isolation=none dashboard/tests/*.test.cjs`, `dashboard\tests\test_build_graph.py`). Expected: tudo verde.
- [ ] **Step 4: Commit** em três commits: `docs(adr): ADR-017 …`, `docs: README e CLAUDE.md com as tarefas locais`, `chore(dashboard): regenera o snapshot`.

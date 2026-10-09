# Evidence tree (step 1 of the observability plan)

Status: draft for review · Date: 2026-10-09 · Repository: `second-brain`

## 1. Purpose

Link each business rule to the playbooks (test scenarios) that validate it and to the history of
their executions, so "is rule X being respected?" has an answer with proof. Today rules live in
prose inside vault notes, and test results are narrated in text with no formal link to a rule
(360 analysis, dimensions D01 and D07).

Each execution carries the `trace_id` of the MCP call that recorded it (step 0), joining this tree
to the call trace.

Success: `cli.py evidence RULE-001` and the MCP tool `get_rule_evidence("RULE-001")` return the rule,
the playbooks that cover it and their latest executions, each with result, date, source and
`trace_id`; `cli.py evidence --lint` fails on a playbook without a rule, a rule without a playbook,
or a broken reference.

## 2. Agreed requirements

Said by the owner: option A, the Second Brain only records and links results that a person or an
agent already obtained elsewhere; it never runs tests. No Neo4j for now. Two real rules of the Hub
as the seed. Real results already documented in the vault are imported as executions marked
`imported`. Approved design: definitions as Markdown notes in the vault, executions in a local
SQLite file under `.runtime/`.

## 3. Non-goals

- Running playbooks, calling the homologation environment or any ERP, carrier or WMS.
- The dashboard, the BFF, the topology map and the agent view. They read this tree in steps 2 and 3.
- Storing request or response payloads of real orders (decision D3).
- Tamper-evidence of executions (O2) and a retention policy (O3).

## 4. Decisions

- D1. Rules and playbooks are Markdown notes with YAML front matter under `vault/rules/` and
  `vault/playbooks/`. The chunker takes the category from the parent folder, so `rules` and
  `playbooks` become retrieval categories with no chunker change; `sync` indexes them like any note.
- D2. Executions live in `.runtime/evidence.db` (SQLite, WAL, 5 s timeout), not in the vault and not
  in the catalog: they grow with every test and must not rewrite tracked files.
- D3. An execution stores a reference and a short summary, never a payload. `evidence_ref` is a
  `path:line`, an `http(s)` URL or a ticket id; `summary` is at most 500 characters.
- D4. `trace_id` is taken from the MCP call in progress (`core.tracing.current_call`); it is
  `NULL` when recorded outside a call (CLI import).
- D5. Every execution has a `source`: `reported` (an agent or person informed it through the MCP
  tool) or `imported` (taken from an existing vault note by the seed import).
- D6. `PyYAML` is declared in `requirements.txt` (it is installed today only as a transitive
  dependency). Front matter is read with `yaml.safe_load`.
- D7. New write tool `record_test_execution` in `brain_mcp`. It only appends to the local evidence
  database; it never writes to the vault.
- D8. Identifiers: `RULE-NNN` and `PB-NNN` (three digits), unique across the vault.

## 5. Design

### 5.1 Definition notes

`vault/rules/RULE-001-<slug>.md` and `vault/playbooks/PB-001-<slug>.md`, with a first-level
heading (the dashboard takes the title from it), front matter, then prose.

Rule front matter: `id`, `title`, `status` (`draft` | `active` | `retired`), `source`
(`path:line` of the note that states the rule), `domain` (free text). Body: the statement.

Playbook front matter: `id`, `title`, `status`, `validates` (list of rule ids, at least one),
`environment` (`hml` | `production` | `local`), `targets` (list of free-text component names).
Body: scenario in given / when / then form and the expected result.

### 5.2 Loader and lint: `core/evidence.py`

- `load_definitions(vault_dir: Path) -> Definitions` where `Definitions` has `rules: dict[str, Rule]`,
  `playbooks: dict[str, Playbook]` and `errors: list[str]`. A malformed note adds an error and is
  skipped; it never raises.
- `lint(defs: Definitions, store: Optional[EvidenceStore] = None) -> list[str]` returns one message
  per problem: invalid or duplicate id, missing field, status or environment out of the allowed
  set, playbook that validates an unknown rule, `active` rule without an `active` playbook,
  `active` playbook without a rule, execution that references an unknown playbook.

### 5.3 Execution store: `core/evidence_store.py`

Table `executions`: `id INTEGER PRIMARY KEY`, `playbook_id TEXT NOT NULL`, `ts TEXT NOT NULL`
(ISO-8601 with offset), `result TEXT NOT NULL` (`pass` | `fail` | `error` | `skipped`),
`environment TEXT NOT NULL`, `evidence_ref TEXT NOT NULL`, `summary TEXT NOT NULL`, `trace_id TEXT`,
`task_label TEXT`, `source TEXT NOT NULL` (`reported` | `imported`), `recorded_by TEXT NOT NULL`
(the MCP `caller`, else `cli`), `import_key TEXT UNIQUE` (set only for imported rows, makes the seed
import idempotent). Index on `(playbook_id, ts)`.

`EvidenceStore(path: Optional[Path] = None)` resolves `path or EVIDENCE_DB` at call time, like
`core/tracing.py`. Methods: `record(...) -> int`, `latest(playbook_id: str, limit: int) -> list[dict]`,
`latest_for_rule(defs, rule_id: str, limit: int) -> dict[str, list[dict]]` (by playbook),
`all_playbook_ids() -> set[str]`.

### 5.4 MCP tools (in `mcp_servers/brain_mcp.py`, all with optional `task_id`)

- `list_rules() -> list[dict]`: id, title, status, playbook ids, and for each the date and result of
  its latest execution (or `null`).
- `get_rule_evidence(rule_id: str, limit: int = 5) -> dict`: the rule, its playbooks and their
  latest executions (`limit` between 1 and 20). Unknown id returns `{"error": ...}` listing the
  known ids.
- `record_test_execution(playbook_id, result, summary, evidence_ref, environment) -> dict`:
  validates every field (section 5.5), records with `source="reported"`, `trace_id` from the
  current call and `recorded_by` from the call's `caller`; returns `{"recorded": id, "trace_id": ...}`
  or `{"error": ...}`. It never raises on invalid input.

### 5.5 Validation of a recorded execution

- `playbook_id` must exist in the loaded definitions and its `status` must not be `retired`.
- `result` in the allowed set; `environment` in the allowed set and equal to the playbook's one,
  or `local`.
- `summary`: text, control characters removed, 1 to 500 characters.
- `evidence_ref`: 1 to 300 characters and one of `path:line[-line]`, `http(s)://...` or `ABC-123`.
- Sensitive-data guard: summary and reference are refused if they contain a token-shaped string
  (`ghp_`, `github_pat_`, `-----BEGIN`), an 11-digit or CPF-shaped number, or a 44-digit number.
  The error says which rule fired, never echoes the value.

### 5.6 CLI

- `cli.py evidence [RULE_ID]`: no argument lists rules; with an id prints the rule, its playbooks
  and their latest executions (metadata only, no summary text longer than 120 characters).
- `cli.py evidence --lint`: prints problems, exit 1 when there is any, 0 otherwise.
- `cli.py evidence --import-seed`: loads `evidence/seed-executions.json` (tracked) into the store;
  rows already imported are skipped by `import_key`.

### 5.7 Seed content (real, from the vault)

Source note: `vault/systems/protecoes-processamento-emissao-hub.md`.

- `RULE-001` Every new label issuance requires a real invoice (NF): positive number, series,
  44-digit non-zero key and valid issue date. Source: that note, lines 45 and 61.
- `RULE-002` In homologation no job calls ERP, carrier or WMS, and direct label generation is
  rejected. Source: that note, line 34.
- `PB-001` Hub automated suite (`npm test`), validates RULE-001 and RULE-002, environment `local`.
- `PB-002` Issuance is blocked when the invoice is missing, incomplete or its lookup fails,
  validates RULE-001, environment `hml`. No executions yet.
- `PB-003` In homologation jobs stay pending and no external call is made, validates RULE-002,
  environment `hml`. No executions yet.
- One imported execution: `PB-001`, `pass`, summary "npm test: 26 scenarios approved, CI Node 18/20",
  `evidence_ref` `vault/systems/protecoes-processamento-emissao-hub.md:47`, `source=imported`,
  `recorded_by=cli`. Nothing else is imported: no result is invented for PB-002 or PB-003.

### 5.8 Data flow

Agent or person runs a test elsewhere → calls `record_test_execution` → validated → row in
`evidence.db` with the call's `trace_id` → `get_rule_evidence` / `cli.py evidence` join the notes
(definitions) with the rows (executions) at read time.

## 6. Error handling

- A missing or corrupt `evidence.db` is created or reported as an error in the tool result; a
  query never crashes the MCP server.
- A malformed definition note is reported by lint and skipped by the loader.
- Concurrent writers (several MCP processes): SQLite WAL with a 5 s busy timeout; a failed write
  returns `{"error": ...}`.

## 7. Testing (written before the code)

1. `tests/test_evidence.py`: loader (valid notes, missing field, bad id, duplicate id, unknown
   rule); lint for each problem class; seed notes in the real vault lint clean.
2. `tests/test_evidence_store.py`: record and read back; ordering and `limit`; `import_key`
   idempotency; WAL and busy timeout set; path resolved at call time.
3. `tests/test_evidence_tools.py` (in-process FastMCP client): `record_test_execution` happy path
   with `trace_id` equal to the call's trace; each validation rule; the sensitive-data guard never
   echoes the value; `get_rule_evidence` and `list_rules` shapes; every new tool has the optional
   `task_id` (the step-0 guard test covers it).
4. `tests/test_evidence_cli.py`: `evidence`, `evidence RULE-001`, `--lint` exit codes, `--import-seed`
   twice gives one row.
5. Review focus: a result or reference containing a control character or a very long string;
   a playbook that validates a retired rule; two processes recording at once; a rule with no
   executions (must print "no evidence yet", never a pass).
6. Regression: all existing Python tests and the 30 dashboard tests.

## 8. Documentation and housekeeping

- ADR-005 in `vault/adrs/`: evidence tree, two layers, self-reported evidence, alternatives
  discarded (everything in the visual catalog; Neo4j now).
- `CLAUDE.md`: proof command lists the new test modules; section 8 lists `vault/rules/` and
  `vault/playbooks/` as catalogues; section 5 states that a new rule needs a playbook and passes
  `cli.py evidence --lint`.
- `requirements.txt`: `pyyaml>=6.0`.
- New vault notes are written with CRLF line endings (as the existing notes; `.gitattributes`
  keeps them so) and `dashboard/build_graph.py` is rerun, because it reads every vault note.
- `.gitignore` already covers `.runtime/`; `evidence/seed-executions.json` is tracked.

## 9. Risks and open points

- O1. The imported execution is the owner's reading of one sentence in a note, mapped to the
  suite playbook. The owner confirms or removes it; removing it leaves a tree with no execution.
- O2. Executions are self-reported and the database is not tamper-evident. `source` and
  `recorded_by` are visible, and the ADR says so. Real separation of users and agents is governance work.
- O3. No retention policy for executions.
- O4. Rules and playbooks beyond the seed are written by hand; there is no authoring tool.

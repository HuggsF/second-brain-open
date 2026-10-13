# CLAUDE.md

Repository rules for `second-brain`. The `superpowers` workflow (and the user's global
`~/.claude/CLAUDE.md`, when present) applies in full; the exceptions are in the last section.
Follow every numbered item; do not paraphrase a subset.

## 1. What this repository is / is not

- Is: KIOSK Brands' local, offline engineering knowledge base. Python 3 (`.venv`), Qdrant +
  Ollama for retrieval, four FastMCP servers in `mcp_servers/`, a loopback BFF in `backend/`,
  a static dashboard in `dashboard/`, and the Markdown `vault/` that is the system of record.
- Is not: the Hub Logístico or the SRV-API server. Those are other repositories and machines
  (`C:/KIOSK/hub-logistico`, production host); read-only from here. Is not the place for 360
  analysis results: they live in `C:/KIOSK/analise-360`.
- The vault is the source; Qdrant and `dashboard/graph-data.js` are derived and rebuildable.

## 2. Never

- Never write a credential value anywhere (files, commits, logs, replies, test fixtures). Cite
  `path:line` instead. Sources: `.env`, the SRV-API key file, the GitHub token, `.runtime/`.
- Never commit `.env`, `.runtime/`, `.brain_hashes.json` or backups of them (`.gitignore` covers
  them; do not weaken it).
- Never set `SRV_API_ALLOW_ARBITRARY=1` or edit `.env` yourself. Commands outside read-only
  inspection on the production host need the human's explicit authorisation in that turn.
- Never run a mutating command on the production or staging host (deploy, restart, `sudo`,
  anything that writes) through `srv_api_run_safe_command`, `github_gateway_mcp` or any other
  MCP tool without that same authorisation.
- Never start Qdrant, Ollama, Docker or the BFF unless the task asks for it.
- Never edit `.memory-backups/` or `.frontend-backups/`: they hold preserved originals.
- Never delete or overwrite a vault note without a backup; `sync` removes its index entries.
- Never record a decision about this repository inside an existing ADR; open a new one (section 6).

## 3. Proof commands and local gates

- Python (targeted): `.\.venv\Scripts\python.exe -m unittest tests.test_components tests.test_bff_wave1 tests.test_hardening tests.test_tracing tests.test_trace_middleware tests.test_trace_servers tests.test_trace_cli tests.test_evidence tests.test_evidence_store tests.test_evidence_tools tests.test_evidence_cli tests.test_evidence_seed tests.test_gates tests.test_memory`
- Dashboard JS: `node --test --test-isolation=none dashboard/tests/*.test.cjs` (Node 24)
  and `.\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py`.
- `integration.test.cjs` compares citation hashes with the current vault bytes: after any vault
  edit, run `.\.venv\Scripts\python.exe dashboard\build_graph.py` first or that test fails.
- Typecheck / lint / format: none configured. Coverage or quality gates: none.
- CI: none. The suite above is the only gate and is run by hand.

## 4. Branches, commits, merges

- Local git only, branch `main`, no remote. Creating a remote or pushing needs the human's order.
- Feature work happens on a branch named for the change; `merge locally` merges it back into
  `main` only after the proof commands pass.
- Commit convention: Conventional Commits (`fix:`, `feat:`, `docs:`, `chore:`), one concern per
  commit, subject in Portuguese or English, never mixing both.

## 5. Definition of done

- Vault note changed → `.\.venv\Scripts\python.exe cli.py sync` finishes with exit code 0
  (it exits 1 and reports `Falhas` when any file failed) and `dashboard\build_graph.py` is rerun.
- New or changed system, rule or demand → the node and its relations in
  `dashboard/graph-catalog.json` match the note.
- Behaviour change in an MCP server → a test in `tests/` covers it, including the refusal path.
- A new MCP tool → accepts an optional `task_id`; `tests/test_trace_servers.py` fails if it does not.
- A new business rule → an `active` playbook validates it and `cli.py evidence --lint` passes.
- A change to how agents may act on a host → the "Never" section here is updated in the same commit.

## 6. Durable files

- Specs: `.superpowers/specs/` · Plans: `.superpowers/plans/` · Ledger:
  `.superpowers/ledger/ledger.md` · Handoffs: `.superpowers/handoffs/`.
- Spec, plan and handoff files are named `yyyy-MM-dd-HH-mm-{name}`.
- ADRs: `vault/adrs/ADR-NNN-*.md`. The three existing ones cover the SULTS/Holmes → Salesforce
  migration, Hub backup/versioning and Git branch policy. A decision about this repository
  itself takes the next number and says so in its first line.
- MCP call trace: `.runtime/trace-log.jsonl` (local, never committed); read it with `cli.py trace <trace_id>`.

## 7. Skills

- pending: no repository skill exists yet. Re-run the bootstrap skill when the MCP contract or
  the host policy has stabilised enough to move out of `vault/systems/`.

## 8. Catalogues

- `vault/systems/<name>.md` — one note per system or integration; read by
  `get_system_architecture`. The question that sends an agent here: "how does X work?".
  Written by hand; indexed by `sync`.
- `vault/domain/` — brand and business rules. `vault/daily/` — dated session notes.
- `vault/rules/` and `vault/playbooks/` — one note per business rule or test scenario; read by
  `get_rule_evidence` and `cli.py evidence`. Executions live in `.runtime/evidence.db`, never in the vault.
- 360 analysis of this repository: `C:/KIOSK/analise-360/second-brain-2026-10-09/relatorio.md`.

## 9. Where a new fact goes

- Durable fact about a system or integration → `vault/systems/<name>.md`.
- New prohibition, proof command, path or host policy → this file.
- Dated decision with a discarded alternative → an ADR in `vault/adrs/`.
- Business rule → `vault/domain/`; session narrative → `vault/daily/`.

## 10. Configuration this file relies on

- `.gitignore` — keeps secrets and runtime state out of git (sections 2 and 4).
- `.env` — host, user and key path for the gateway; `SRV_API_ALLOW_ARBITRARY` stays unset.
- Proposed, not installed: a pre-commit check that rejects `.env`, key files and token-shaped
  strings (prerequisite: a hook runner; side effect: blocks a commit that carries one).

## 11. Exceptions to the global

- None declared. The `superpowers` TDD item applies to `mcp_servers/`, `core/`, `ingestion/`
  and `backend/`; it does not apply to Markdown under `vault/`, whose proof is section 5.

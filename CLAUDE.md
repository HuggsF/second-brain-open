# CLAUDE.md

Repository rules for `second-brain`. The `superpowers` workflow (and the user's global
`~/.claude/CLAUDE.md`, when present) applies in full; the exceptions are in the last section.
Follow every numbered item; do not paraphrase a subset.

## 1. What this repository is / is not

- Is: KIOSK Brands' local, offline engineering knowledge base. Python 3 (`.venv`), Qdrant +
  Ollama for retrieval, five FastMCP servers in `mcp_servers/` (the fifth, `local_tasks_mcp.py`, runs
  small tasks on the local model), a loopback BFF in `backend/`, a static dashboard in `dashboard/`
  (dev server `dashboard/serve.py`), the agnostic core (`core/protocol/`, `core/local_tasks/`,
  `core/events.py`) with the instance profiles in `profiles/`, and the Markdown `vault/` that is the
  system of record.
- Is not: the Hub Logístico or the SRV-API server. Those are other repositories and machines
  (`C:/KIOSK/hub-logistico`, production host); read-only from here. Is not the place for 360
  analysis results: they live in `C:/KIOSK/analise-360`.
- Scope (ADR-021): knowledge, evidence and trace, observability (dashboard and reports about observed
  systems) and the multi-agent platform. Hub product features (connectors, sales analytics, UI
  wireframes, product documentation) are out of scope; knowledge about the Hub (system notes, rules,
  playbooks, evidence) stays. `crm_hggs` is a reference for patterns only; never copy its content here.
- The vault is the source; Qdrant and `dashboard/graph-data.js` are derived and rebuildable.

## 2. Never

- Never write a credential value anywhere (files, commits, logs, replies, test fixtures). Cite
  `path:line` instead. Sources: `.env`, the SRV-API key file, the GitHub token, `.runtime/`.
  Provider API keys (`OPENROUTER_API_KEY` and any `api_key_env` in profiles) follow the same rule:
  never log, print, copy or embed the value; only the environment variable name appears in code
  and profiles.
- Task content goes only to cloud providers declared in the profile chain, and every one of them
  carries both guarantees in `extra.provider`: `zdr: true` (zero data retention: only endpoints
  that keep nothing) and `data_collection: deny` (no endpoint that collects or trains on the
  content). Never add a cloud provider without both, and never call one outside the chain.
- Never commit `.env`, `.runtime/`, `.brain_hashes.json` or backups of them (`.gitignore` covers
  them; do not weaken it).
- Never commit the raw text of courses or books (`extracted_drive/`, `extracted_pm3/`, `downloads_*`):
  reference notes keep metadata and the source SHA-256 only (ADR-015).
- Never set `SRV_API_ALLOW_ARBITRARY=1` or edit `.env` yourself. Commands outside read-only
  inspection on the production host need the human's explicit authorisation in that turn.
- Never run a mutating command on the production or staging host (deploy, restart, `sudo`,
  anything that writes) through `srv_api_run_safe_command`, `github_gateway_mcp` or any other
  MCP tool without that same authorisation.
- Never start Qdrant, Ollama, Docker or the BFF unless the task asks for it.
- Never edit `.memory-backups/` or `.frontend-backups/`: they hold preserved originals.
- Never delete or overwrite a vault note without a backup; `sync` removes its index entries.
- Never record a decision about this repository inside an existing ADR; open a new one (section 6).
- Command allowlists live only in `core/policy/` (ADR-022); every tool call by the platform's
  orchestrator agents goes through `core/broker.py` (IDE agents call the MCP servers directly, which share
  `core.policy.commands`). Never add a local allowlist or call a tool implementation around the broker.

## 3. Proof commands and local gates

- Python (targeted): `.\.venv\Scripts\python.exe -m unittest tests.test_components tests.test_bff_wave1 tests.test_hardening tests.test_tracing tests.test_trace_middleware tests.test_trace_servers tests.test_trace_cli tests.test_evidence tests.test_evidence_store tests.test_evidence_tools tests.test_evidence_cli tests.test_evidence_seed tests.test_gates tests.test_memory tests.test_workflow_api tests.test_drive_sync tests.test_protocol tests.test_agnostic_core tests.test_events tests.test_local_tasks tests.test_local_tasks_mcp tests.test_local_tasks_cli tests.test_providers tests.test_openai_compat_client`
  Also run the whole suite with `.\.venv\Scripts\python.exe -m pytest` (three of the new suites are pytest-style); new modules: `tests.test_policy tests.test_policy_registry tests.test_broker tests.test_tools tests.test_mission_guard tests.test_no_local_allowlist tests.test_ws_server`.
  New modules (Phase 6): `tests.test_evidence_lights tests.test_domain_observation tests.test_bff_phase6`.
  New modules (onda A, ingestion/paths): `tests.test_vault_docs tests.test_sync_lock tests.test_sync_consistency`.
  New modules (onda B, citations/scope): `tests.test_citations tests.test_retrieval_contract tests.test_bff_retrievals`.
  New modules (onda C, cost/budget): `tests.test_cost tests.test_budget tests.test_budget_wiring`.
  New modules (segundo sinal, ADR-037): `tests.test_vault_vocab tests.test_golden_dataset tests.test_embeddings`.
  New modules (resposta pela cadeia, ADR-038): `tests.test_answer_generation`.
- Assistant answer (ADR-038): `BrainRetriever.answer()` (and `cli.py ask`) generates through the active
  profile's provider chain with the profile budget; retrieval stays local. The `kiosk` chain is
  cloud only (ADR-040): Ollama serves embeddings, never generation, so without the key, credit or
  budget the answer fails at once (`model_error`). Each answer is a real, paid call (cost in `cost_usd`).
- Full gate: `.\.venv\Scripts\python.exe -m pytest -q`; `node --test dashboard/tests/*.test.cjs`; `cd jev-app && npm test`.
- JEV front-end (React 19 + Tailwind 4) lives in `jev-app/`; its build is committed to `dashboard/jev/` (no CI), so after any change in `jev-app/src` run `cd jev-app && npm test && npm run build` and commit the output.
- Budget guard (ADR-035): when `BudgetTracker.status().state == "exceeded"`, `run_task` executes exclusively via local providers (zero cloud calls). If no local provider exists and the task needs a model, it returns `status="budget_exceeded"`. Deterministic tasks (unknown_task, validate-without-source) always pass. CLI exit code for `budget_exceeded` is 3.
- Budget limits and alerts (ADR-036): a limit of 0 (`daily_usd` or `monthly_usd`) blocks paid spend; when the budget state worsens after a call, an alert goes to stderr and to the in-process `budget.alert` event; that SSE fan-out reaches only subscribers in the same process (the BFF, which does not call `run_task`), so for the CLI and MCP the alert is stderr only.
- Lights (ADR-023): the test light (evidence) and the health light (observation) are separate signals; a rule's light comes from `evidence.list_rules`, health, for the JEV, from `core/domain/observation` (the Observability page still computes health in JS with `dashboard/hub-topology.js`).
- `dashboard/hub-topology.js` `project()` is the source of truth for the Python port: when you change it, regenerate the golden with `node scripts/generate_observation_golden.js` and make `core/domain/observation/projection.py` match (`--check` runs in the Node suite).
- Dashboard JS: `node --test dashboard/tests/*.test.cjs` (Node 24)
  and `.\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py`.
- `integration.test.cjs` compares citation hashes with the current vault bytes: after any vault
  edit, run `.\.venv\Scripts\python.exe dashboard\build_graph.py` first or that test fails.
- Task quality (not part of the gate above): `.\.venv\Scripts\python.exe cli.py task-eval
  [--profile NAME]` runs `tests/golden_dataset_local_tasks.json` through the profile's provider
  chain (cloud only in `kiosk`, ADR-040) and exits 1 when overall accuracy is below
  `--min-accuracy` (default 0.6); it prints accuracy, average latency and the tier that answered,
  per task. It makes real, paid cloud calls (about US$ 0.0003 per call with the kiosk model) and
  needs the key set. From a worktree, pass the
  key file by path only: `BRAIN_ENV_FILE=C:/KIOSK/second-brain/.env`.
- Retrieval quality (not part of the gate above): `.\.venv\Scripts\python.exe cli.py retrieval-eval
  [--min-recall 0.8] [--dataset PATH] [--k 5]` runs the golden dataset (30 positives, 30 negatives,
  3 known limits) through the real retriever, prints a grid of `min_score` x `max_drop` without and
  with the unknown-term gate (ADR-037), suggests the pair from the gated grid and writes a report to
  `evals/reports/` (git-ignored); it exits 1 when no gated pair clears every negative, when the
  suggested pair's recall is below `--min-recall`, when the index holds points of an older embedding
  scheme, or on a Qdrant/Ollama error. It makes real calls to the local Qdrant and Ollama (nothing is
  paid) and needs the index rebuilt first with `cli.py sync --rebuild --yes` from the canonical
  checkout (ADR-034). The floor in `config.py` (`0.70` / `0.10`, one chunk per note, applied in the
  Qdrant search) was measured on 2026-10-29 (ADR-039); change it only with a new eval report.
- Embedding scheme (ADR-037): after changing the embedding model or the query/document prefixes
  (`OLLAMA_EMBED_*`), run `cli.py sync --rebuild --yes` from the canonical checkout before restarting
  the `second-brain` MCP and the BFF, and open no new Claude Code session in between (each one starts
  the MCP with the new code); until the rebuild, sync, reconcile and `retrieval-eval` refuse.
  A golden-dataset negative's `absent_entities` must never appear in any vault note
  (`tests/test_golden_dataset.py`).
- Typecheck / lint / format: none configured. Coverage or quality gates: none.
- CI: none. The suite above is the only gate and is run by hand.

## 4. Branches, commits, merges

- Default branch `main`; remote `origin` is `github.com/HuggsF/second-brain`. Pushing, opening PRs or
  rewriting history needs the human's order.
- Feature work happens on a branch named for the change; `merge locally` merges it back into
  `main` only after the proof commands pass.
- Commit convention: Conventional Commits (`fix:`, `feat:`, `docs:`, `chore:`), one concern per
  commit, subject in Portuguese or English, never mixing both.

## 5. Definition of done

- Vault note changed → `.\.venv\Scripts\python.exe cli.py sync` finishes with exit code 0
  (it exits 1 and reports `Falhas` when any file failed) and `dashboard\build_graph.py` is rerun.
  Incremental `sync` (and `--reconcile`) refuses with exit 1 while the index holds points without
  `space_id` (pre-onda B); run `cli.py sync --rebuild --yes` from the canonical checkout first (ADR-034).
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
- ADRs: `vault/adrs/ADR-NNN-*.md`, numbered in sequence (ADR-001 to ADR-023 at 2026-10-14). A decision
  about this repository itself takes the next number and declares `scope: second-brain` in its
  frontmatter (ADR-004, 005, 010, 014, 015, 016 do).
- MCP call trace: `.runtime/trace-log.jsonl` (local, never committed); read it with `cli.py trace <trace_id>`.

## 7. Skills

- pending: no repository skill exists yet. Re-run the bootstrap skill when the MCP contract or
  the host policy has stabilised enough to move out of `vault/systems/`.

## 8. Catalogues

- `vault/systems/<name>.md` — one note per system or integration; read by
  `get_system_architecture`. The question that sends an agent here: "how does X work?".
  Written by hand; indexed by `sync`.
- `vault/domain/` — brand and business rules. `vault/daily/` — dated session notes.
- Every vault note starts with YAML frontmatter (`type`, `status`, `date`; ADR-014); templates in
  `vault/_templates/`. Adding frontmatter shifts lines: update `path:line` citations in rules and
  `evidence/seed-executions.json` in the same change.
- `vault/rules/` and `vault/playbooks/` — one note per business rule or test scenario; read by
  `get_rule_evidence` and `cli.py evidence`. Executions live in `.runtime/evidence.db`, never in the vault.
- 360 analysis of this repository: `C:/KIOSK/analise-360/second-brain-2026-10-09/relatorio.md`.

## 9. Where a new fact goes

- Durable fact about a system or integration → `vault/systems/<name>.md`.
- New prohibition, proof command, path or host policy → this file.
- Dated decision with a discarded alternative → an ADR in `vault/adrs/`.
- Business rule → `vault/domain/`; session narrative → `vault/daily/`.
- New code in `core/` does not cite the instance (brands, Hub, SULTS, Holmes, SRV-API, Salesforce, SAP):
  that vocabulary goes to `profiles/<name>/`; `tests/test_agnostic_core.py` enforces it.

## 10. Configuration this file relies on

- `.gitignore` — keeps secrets and runtime state out of git (sections 2 and 4).
- `.env` — host, user and key path for the gateway; `SRV_API_ALLOW_ARBITRARY` stays unset.
- Proposed, not installed: a pre-commit check that rejects `.env`, key files and token-shaped
  strings (prerequisite: a hook runner; side effect: blocks a commit that carries one).

## 11. Exceptions to the global

- None declared. The `superpowers` TDD item applies to `mcp_servers/`, `core/`, `ingestion/`
  and `backend/`; it does not apply to Markdown under `vault/`, whose proof is section 5.

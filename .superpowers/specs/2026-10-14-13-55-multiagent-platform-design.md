# Multi-agent platform and observability

Status: draft for review · Date: 2026-10-14 · Repository: `second-brain` · Decision record: ADR-021

## 1. Purpose

Turn the multi-agent pieces that already exist (Nexus UI, `backend/orchestrator.py`,
`backend/ws_server.py`, the domain layer in `core/domain/`, the quality gates in `core/gates/`) into one
coherent platform whose every action is authorised, traced and visible, and whose observability (panel
and reports) shows two things that must not be confused: the health of the observed systems and the
results of the tests that protect them.

Success:
- Every tool call made by an agent, from the IDE or from the Nexus orchestrator, goes through one
  policy and one broker, and leaves a record with the agent's identity and a `trace_id`.
- A mission plan is checked by the quality gates before it starts, and a RED gate blocks it.
- For each business rule, the panel shows a test light (green, yellow, red, grey) computed from recorded
  test executions, next to, and never mixed with, the health light of the system it concerns.
- Reports (Hub health, rule evidence, agent activity) are generated on demand from data the platform
  already records.

## 2. Agreed requirements

Said by the owner (2026-10-14): the Second Brain covers knowledge, observability (reports and panel) and
the multi-agent platform; Hub product features are out (ADR-021); sending data to cloud providers is
allowed; the design with three layers (agents, one tool broker, three capabilities) is approved; the
test runner lives outside this repository and only registers results; `crm_hggs` is a reference for
patterns, never a source of copied content.

## 3. Non-goals

- Running tests, deploying, or any write to production or homologation from this repository.
- Hub product code (connectors, sales analytics, UI kits). It lives in the Hub repository.
- A new UI framework or a rewrite of the Nexus scene; the two failing UX gates of the dashboard are a
  separate interface task (section 9, O1).
- Real user identities and authentication of people (governance work); agents get a role identity here.
- Neo4j, a message queue, or any new runtime service.

## 4. Current state (verified on `main` b89470d)

| Area | Fact |
|---|---|
| MCP | 5 servers, 25 tools: brain 7, github 5, srv_api 5, hub observation 3 (`observe_hub`, `pm2_status`, `pm2_logs`), local tasks 5 |
| Domain | `core/domain/nexus/entities.py` (roles, rooms, `TOOL_REGISTRY`, `AUTO_TOOLS`) and `core/domain/workflow/entities.py` (`Mission`, `Step`, `AgentEvent`, `validate_mission_envelope`); 919 lines, stdlib only; 72 tests |
| Gates | `core/gates/` has `DagGate`, `RuleComplianceGate`, `GroundingGate`, `IdempotencyGate` and `CompoundGatePipeline.run_all(payload)` returning GREEN, YELLOW or RED. **No runtime code imports them** (`backend/`, `mcp_servers/`): they are enforced nowhere |
| Tool mismatch | The domain authorises `get_rule_evidence`, `run_tests`, `validate_plan`, `write_doc`, which `backend/tool_executor.py` does not implement (a plan passes the gate and then fails with "not found"). The executor implements `run_safe_command` (SSH to production), which the domain does not authorise |
| Duplicated policy | `backend/tool_executor.py` carries its own copy of the read-only command list, including `sqlite3` (which writes to a database), connects with `AutoAddPolicy` without pinning the host key, and writes no trace. The hardened gateway is `mcp_servers/srv_api_gateway_mcp.py` |
| ws_server | Does not use `validate_mission_envelope` (ADR-020, pending item) |
| Observation | ADR-019 phase 2 planned `core/domain/observation/`; it does not exist. Contradiction detection ("test passed but observation is bad") is implemented in the browser (`dashboard/jev-ui.js`) |
| Evidence | `core/evidence.py`, `core/evidence_store.py`, `record_test_execution`; 13 playbooks of which only PB-001 to PB-003 are verifiable scenarios; `list_rules` state is therefore stuck at "parcial" |
| JEV | "Joint Evidence View". It runs nothing: it records executions by hand and copies commands. Its observation route (`/v1/observation/*`) does not exist in the BFF (`/v1/observability`), and the API it needs and the BFF live on different servers |
| Models | Deterministic, then local (Ollama), then cloud with a local fallback (ADR-017, ADR-018 "Proposto": accuracy met, latency target missed) |

## 5. Decisions

- D1. One tool policy, `core/policy/`, pure functions with no I/O, used by every caller that can reach a
  tool. No component keeps its own copy of an allowlist.
- D2. One broker, `core/broker.py`: `call(identity, tool, args, task_id)`. It asks the policy, runs the
  gates when the call belongs to a mission, executes through the existing tool implementations, and
  records the call (trace) with the agent identity. `backend/tool_executor.py` becomes a thin adapter
  over the broker.
- D3. Verdicts follow the pattern of the reference architecture the owner studied: `APPROVE`, `DENY`,
  `ESCALATE`, with fail-closed behaviour (any error, timeout or parse failure becomes `ESCALATE` or
  `DENY`, never `APPROVE`).
- D4. Four tool classes: `READ` (auto), `WRITE_LOCAL` (auto and always traced, e.g.
  `record_test_execution`), `PROD_READ` (read-only inspection of a production host: `ESCALATE` unless the
  tool is a named, fixed command), `PROD_MUTATING` (never auto; `DENY` unless a human approved that exact
  call, homologation first). No tool of the last class is exposed today.
- D5. Generic shell on a host is not a tool for agents. `sqlite3` leaves the generic allowlist; a named
  read-only tool with fixed queries and `mode=ro` replaces it when needed.
- D6. An agent is a role crossed with a specialty. Roles are the five of the Nexus domain (manager,
  researcher, coder, writer, reviewer); specialties are the four of ADR-012 (DEV, DEVOPS, QA, PRODUTO).
  Identity string: `agent:<role>/<specialty>` (specialty optional). It becomes `caller` in the trace.
- D7. A mission's calls share one trace through the existing `task_id` mechanism: `task_id = "M<missionId>"`.
  The mapping of ids is the table of ADR-020 plus this one rule.
- D8. Test lights are computed per rule from executions of playbooks marked `kind: test`; playbooks
  marked `kind: runbook` never count. The health light of the Hub and the test light are two axes of the
  same map.
- D9. Observation logic leaves the browser: `core/domain/observation/` holds `ServiceHealth`,
  `ObservationSnapshot`, `Contradiction` and `detect_contradictions()`; the UI only renders.
- D10. Cloud: allowed (ADR-021). Providers keep zero data retention (ADR-018). The sensitive-value guard
  (tokens, private keys, CPF, invoice key) stays: it protects the log and the evidence store, not privacy.

## 6. Design

### 6.1 Layers

Agents (orchestrator, mission roles, specialists) call the broker. The broker is the only path to tools.
Behind it: knowledge (vault, vectors, ADRs), evidence (rules, playbooks, executions), observability
(read-only collectors, lights, reports). Outside the repository: the test runner (CI of the Hub) writes
only through `record_test_execution`; observed systems are read only.

### 6.2 Policy and broker

`core/policy/` exposes:
- `ToolClass` (`READ`, `WRITE_LOCAL`, `PROD_READ`, `PROD_MUTATING`) and a registry mapping every tool name
  to a class. A tool absent from the registry is `DENY`.
- `Verdict` (`APPROVE`, `ESCALATE`, `DENY`) with a `reason` from a closed vocabulary.
- `decide(identity, tool, args) -> Verdict`: class, then role permission (`TOOL_REGISTRY`), then argument
  checks (the command rules that today live in `srv_api_gateway_mcp.py` move here; that module imports them).

`core/broker.py`: `call(identity, tool, args, task_id) -> dict`. Order: policy; if `ESCALATE`, return an
approval request (the Nexus approval flow already exists); if `APPROVE`, execute and record. The result
never contains secrets; errors keep only the class name (as in the trace log).

The IDE agents keep using the MCP servers directly. The servers that can touch a host import
`core/policy`, so the rules are the same on both paths.

### 6.3 Mission lifecycle and gates

`Mission` and `Step` stay as defined in ADR-020. Before a mission starts, `CompoundGatePipeline.run_all`
receives the plan: `DagGate` (structure, roles, tools), `RuleComplianceGate`, `GroundingGate` (citations)
and `IdempotencyGate` (mutations need a key). Result handling: RED blocks the mission, YELLOW turns
into an approval request, GREEN proceeds. The gate result is recorded as a trace child event.
`validate_mission_envelope` is used by `ws_server.py` in place of its local check.

### 6.4 Test lights

- Playbook front matter gains `kind: test | runbook` (default `runbook`, so no existing note changes
  meaning) and optional `ttl_hours` (default 168).
- State per rule counts only active `kind: test` playbooks, in the environment the playbook declares.
- Colour: green = every counted playbook has a latest `pass`, inside its TTL, in its own environment;
  yellow = some counted playbook has no execution, only `skipped`, an expired `pass`, or only a `local`
  run where `hml` or `production` is required; red = the latest execution of any counted playbook is
  `fail` or `error`; grey = no counted playbook has any execution.
- Source of the colour is `evidence.list_rules`, exposed by `GET /api/rules` and consumed by the panel.
- An executions row gains optional `commit_sha` and `run_id` (migration with `ALTER TABLE ... ADD COLUMN`).
- Health light (Hub observation) keeps its own rules (stale after 180 s); the two never merge. The
  contradiction "tests green, health red" is an alert computed by the observation domain (D9).
- JEV fixes that belong to this feature: the observation route, `evidence_ref` required in the modal,
  `deprecated` replaced by `retired`, the rules endpoint, one origin for both APIs.

### 6.5 Observability and reports

Collectors stay read only (Hub post-deploy check, PM2 tools). Reports are generated by
`cli.py report <kind>` into Markdown on standard output or a file chosen by the user, never into the
vault: `hub-health` (latest observations and contradictions), `rule-evidence` (per rule: playbooks,
latest executions, light), `agent-activity` (calls by agent identity and mission from the trace log,
approvals asked and answered). A report states the time window and the data sources it read.

### 6.6 Telemetry

One correlation key, `trace_id`. Mission events sent to Nexus carry the `trace_id` of the mission, so the
agent view and the trace log describe the same facts. The local-task event log and the trace log stay
separate files with their own rotation.

## 7. Phases

Each phase gets its own plan and review; nothing starts before the plan is approved.

- **Phase 5: close the domain and unify the broker.** `core/policy/`, `core/broker.py`; the executor
  becomes an adapter; the tool registry matches reality (either implement `get_rule_evidence` and remove
  the tools nobody provides, or provide them); `run_safe_command` enters the domain as `PROD_READ`;
  gates wired into the mission start; `ws_server` uses `validate_mission_envelope`; `sqlite3` out of the
  generic list. Acceptance: no allowlist outside `core/policy/`; a plan with an unknown tool is RED at plan
  time; every orchestrator tool call appears in the trace with `agent:<role>` as caller.
- **Phase 6: observation domain and test lights.** `core/domain/observation/`, `kind`, TTL, the rules
  endpoint, the JEV fixes, the two-axis map. Acceptance: with PB-001 and PB-002 marked `kind: test` and the seed
  data, RULE-001 is not green until PB-002 also has a `pass`; a `fail` in either turns it red.
- **Phase 7: agent identity, specialties and the agent view.** Specialties in the domain; the view reads
  the trace by identity and mission.
- **Phase 8: reports.** The three `cli.py report` kinds.
- **Phase 9: runner integration (outside this repository).** A thin script in the Hub's CI calls
  `record_test_execution` after `npm test` and after the post-deploy check in homologation.

## 8. Testing

Every phase follows test first. Phase 5 minimum: policy table tests (class by tool, verdict by role and
class, fail-closed on malformed input); broker tests with the SSH layer mocked (approve, escalate, deny,
trace record with identity); a test that fails if any module outside `core/policy/` defines a command
allowlist; gate pipeline tests at mission start (RED blocks, YELLOW escalates); existing 419 Python tests
and the dashboard suite keep passing. Every new vault note is CRLF, and the dashboard snapshot is
regenerated from a clean checkout.

## 9. Risks and open points

- O1. Two dashboard UX gates fail on `main` (12 inline styles over the ceiling; the JEV modal is not a
  `<dialog>`). Fixing them is an interface task and is not part of these phases.
- O2. The owner's working folder holds uncommitted work on a stale branch (`fix/ddd-phase4-…`) that
  touches `ws_server.py`, the gateway and Nexus files. It must be saved or discarded before Phase 5
  edits the same files.
- O3. Who owns the runner (Phase 9) and how it authenticates. Until then executions are recorded by
  hand or by an agent, and are self-reported.
- O4. Whether reports should also run on a schedule; this spec delivers on-demand only.
- O5. ADR-018 stays "Proposto" because its latency success criterion was not met (17.6 s average per
  model call in the final `task-eval`); the owner decides whether to accept it or change the criterion.
- O6. `.memory-backups/` (1.2 MB of preserved originals) and `dashboard/analysis/` are untouched; the
  repository rules forbid editing the first, so removal needs the owner's explicit order.
- O7. ADR-022 (policy and broker) is written with Phase 5; ADR-012's four specialists and the five
  Nexus roles are documented there as two axes.

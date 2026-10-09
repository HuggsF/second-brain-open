# MCP trace IDs (step 0 of the observability plan)

Status: draft for review · Date: 2026-10-09 · Repository: `second-brain`

## 1. Purpose

Every tool call made by an agent through the four MCP servers leaves one record that can be
joined with the other calls of the same task. Today the servers record nothing, except the SSH
gateway's own `gateway-audit.jsonl`, and the BFF's `request_id` is a throwaway UUID. Without a
shared identifier the 360 analysis could not reconstruct "which agent action led to which effect"
(findings D09, D07; cross-dimension risk XR-04).

This is step 0 of the plan that later adds the evidence tree, the topology map and the agent
view. Those steps read the log defined here; they are out of scope now.

Success: given a `trace_id`, one command prints the ordered chain of calls of that task, with
tool, time, duration and outcome, and no credential value appears in the log.

## 2. Agreed requirements

Said by the owner: both per-call identification (A) and per-task grouping (B). The caller
identity (C) was left to the implementer's judgement and documented here. The log stays local.
The ID format follows W3C Trace Context.

Assumptions confirmed by the owner: W3C format; local file only; MCP carries no task id from the
agent, so the server creates one per call unless the agent passes `task_id`.

## 3. Non-goals

- Identifying people or agents beyond best effort (decision D3). Real user separation belongs to
  the governance work.
- Changing the BFF, the dashboard, Neo4j or any graph. They consume the log later.
- A retention policy beyond size-based rotation.
- Sending traces anywhere outside the machine.

## 4. Decisions

- D1. Central recording through FastMCP middleware (`on_call_tool`), not per-tool decorators:
  one place covers all 15 tools (brain 4, github 5, srv_api 5, hub observation 1) and any future
  tool.
- D2. IDs follow W3C Trace Context. `trace_id` = 32 lowercase hex, groups a task. `span_id` = 16
  lowercase hex, identifies one call.
- D3. `caller` is the MCP client name from the initialize handshake when the library exposes it,
  otherwise `unknown`. Nothing else is inferred. This is recorded, not enforced.
- D4. A tool call never fails because of tracing. Any error in the tracing code is swallowed
  after a best-effort single line on stderr.
- D5. The SSH gateway's `gateway-audit.jsonl` is replaced by the unified log. Its events become
  child records of the same call (same `trace_id`, same `span_id` parent).

## 5. Design

### 5.1 Identifiers

- With no `task_id` argument: `trace_id` is random per call (case A).
- With `task_id`:
  - if it already matches `^[0-9a-f]{32}$` it is used as `trace_id`;
  - otherwise `trace_id = sha256(task_id.strip())[:32]` and the original text is stored as
    `task_label` (at most 80 characters, control characters removed). The same text always yields
    the same `trace_id`, so calls of one task group without the agent generating UUIDs (case B).
- `span_id` is random per call.

### 5.2 Record (one JSON object per line)

`.runtime/trace-log.jsonl`, UTF-8, append only:

```
schema_version  1
ts              ISO-8601 with offset
trace_id        32 hex
span_id         16 hex
parent_span_id  16 hex or null (null for the call itself; set for child events)
task_label      string or null
server          e.g. "SRV-API Gateway"
tool            tool name
event           "call" | "ssh.exec" | "ssh.refused"   (child events come from the gateway)
status          "ok" | "error" | "refused"
duration_ms     integer (call events)
caller          string
args            redacted summary (see 5.3)
error_type      exception class name or null (never the message)
```

### 5.3 Argument summary

- Keys whose lowercase name contains `token`, `password`, `secret`, `key`, `authorization` or
  `credential` have the value replaced by `[redacted]`.
- Other string values are truncated to 200 characters; the gateway `command` is kept up to 500,
  as the old audit did.
- `task_id` is not copied into `args`.
- The summary is a bounded copy; the original arguments are never modified.

### 5.4 Components

- `core/tracing.py` — pure functions (`derive_trace_id`, `new_span_id`, `redact_args`,
  `write_record`, rotation, `read_trace`) and a `ContextVar` holding the current
  `(trace_id, span_id)` so code running inside a call can emit child events.
- `core/trace_middleware.py` — `TraceMiddleware(server_name)` subclass of
  `fastmcp.server.middleware.Middleware`; `on_call_tool(context, call_next)` times the call,
  sets the `ContextVar`, calls `call_next`, then writes the record. The call is recorded as
  `refused` when a child event `ssh.refused` was emitted during it (the result payload is never
  inspected), as `error` when the tool raised (the exception is re-raised unchanged), and as
  `ok` otherwise.
- Each `mcp_servers/*.py` registers the middleware (`mcp.add_middleware(...)`) and gives every
  tool an optional `task_id: Optional[str] = None` parameter that the tool ignores.
- `mcp_servers/srv_api_gateway_mcp.py` — `_audit` becomes a thin call into `core.tracing`
  emitting child events; `gateway-audit.jsonl` is no longer written.
- `cli.py trace <trace_id>` and `cli.py trace --recent N` — print the chain, oldest first.

### 5.5 Rotation

When the log exceeds 5 MB, it is renamed to `trace-log.1.jsonl` (older ones shift, three kept,
the oldest is deleted) and a new file starts. Rotation errors are swallowed (D4).

### 5.6 Data flow

agent → MCP tool call → `TraceMiddleware` (create ids, set ContextVar, start timer) → tool runs
(the gateway may emit child events) → middleware writes the `call` record → result returns to
the agent unchanged.

## 6. Error handling

- Log directory missing: created. Disk full or file locked: record dropped, the call succeeds.
- Malformed `task_id` (non-string, empty, only control characters): treated as absent.
- Concurrent writers (several servers, one file): each record is written with one `write` call
  in append mode; lines stay whole for records under the OS atomic-append size. Records are
  bounded to 4 KB by truncating `args`.
- The log may contain command text (gateway). It lives in `.runtime/`, which is gitignored.

## 7. Testing (written before the code)

1. `tests/test_tracing.py`: `derive_trace_id` (hex passthrough, hashing, stability, empty input);
   `redact_args` (secrets, truncation, original untouched); `write_record` creates the file, one
   valid JSON line, never raises on a read-only path; rotation keeps three files.
2. `tests/test_trace_middleware.py`: using the FastMCP in-process client against a small test
   server, one successful call, one exception and one refused call each leave exactly one
   record with the right `status`; two calls with the same `task_id` share `trace_id`; a call
   without it gets a fresh one; the tool result is identical with and without the middleware.
3. Per server: every registered tool exposes `task_id` as optional in its schema (this catches
   a future tool added without it), and the middleware is registered.
4. Gateway: a refused command and an executed command (SSH mocked) produce child events with
   the call's `trace_id`.
5. `cli.py trace` prints the chain for a known `trace_id` and exits 1 for an unknown one.
6. Regression: the existing 16 Python tests and the 30 dashboard tests still pass.

## 8. Documentation and housekeeping

- ADR-004 in `vault/adrs/`: "Trace IDs and unified trace log for MCP calls" with the discarded
  alternatives (per-tool decorators; begin/end task tools).
- `CLAUDE.md`: the audit-trail path in section 6 now points to `trace-log.jsonl`; section 2 is
  unchanged. The vault note `second-brain-observability-bff` gets one paragraph on the log.
- `docs/` or the vault gets no new architecture prose beyond the ADR.

## 9. Risks and open points

- O1. Whether the FastMCP 4.0.11 context exposes the client name for D3 is verified in the first
  test of step 2; if it does not, `caller` stays `unknown` and the spec is not changed.
- O2. An agent that never passes `task_id` produces one trace per call. That is accepted
  (case A) and visible in `cli.py trace --recent`.
- O3. The log is not tamper-evident. Out of scope; it is evidence for the owner, not for third
  parties (parameter P10 of the 360 canvas).
- O4. Rotation deletes old records without a retention decision by the owner; the 5 MB × 3 limit
  is a technical bound and can be changed in one constant.

# Progress — UI/UX Roadmap Phase 2

> **Plano:** `docs/superpowers/plans/2026-10-16-uiux-roadmap-phase2-plan.md`  
> **Branch:** `feature/uiux-roadmap-phase2`

| # | Wave | Brief | Título | Status | Depende de |
|---|:---:|-------|--------|:------:|:---:|
| 1 | 0 | `task-1-brief.md` | SEC-WS: Session Auth WS Handshake | `completed` ✅ | — |
| 2 | 1 | `task-2-brief.md` | BUS-01: SSE Event Bus Backend | `completed` ✅ | T1 |
| 3 | 1b | `task-3-brief.md` | BUS-01-FE: graph-events.js → BUS-01 | `completed` ✅ | T2 |
| 4 | 2 | `task-4-brief.md` | BUS-02: postMessage Bridge | `completed` ✅ | T2 |
| 5 | 2b | `task-5-brief.md` | DT-F1: Tema Orgânico Mobile Fix | `completed` ✅ | T4 |
| 6 | 3 | `task-6-brief.md` | MON-01: Tool Call Streaming | `completed` ✅ | T2 |
| 7 | 3b | `task-7-brief.md` | MON-02: Tool Call Visualizer UI | `completed` ✅ | T6 |

---

## Baseline de Testes (pré-execução)

| Suíte | Status | Falhas pré-existentes |
|-------|:------:|----------------------|
| Nexus | 84/84 ✅ | — |
| Dashboard (batch) | 174/178 | 4 state-leak em `knowledge-host.test.cjs` |
| JEV | 118/118 ✅ | — |
| Python | 1051/1059 | 7 em `test_nexus_ws.py` + 1 em `test_trace_servers.py` |

## Notas

- `test_total_tool_count_is_25` (55≠25): **out of scope** — baseline conhecida (DD-01)
- DD-02 (2 testes WS): incluído no brief T1 (SEC-WS)

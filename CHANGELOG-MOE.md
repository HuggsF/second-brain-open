# Changelog — KIOSK AI-OS MoE Zero-Trust Convergence

## [v1.0.0-moe] — 2026-10-15

### 🎯 Convergência Completa: Simulador MoE → KIOSK AI-OS

Implementação dos 19 gaps identificados entre o simulador MoE de governança
multi-agente e a plataforma KIOSK AI-OS. Cobertura de aplicação: **100%**.

### Sprint 0 — Quality Gates Reconnect (PR #17)
- `core/mission_guard.py`: kwargs para payloads de gates (grounding, rules, idempotency)
- 9 testes novos

### Sprint 1 — DLP Guardrail Engine (PR #18)
- `core/security/dlp_guardrail.py`: PII masking (CPF, CNPJ, email, cartão, API keys)
- `core/gates/dlp_gate.py`: Gate 5 com anti-injection detection
- 27 testes novos

### Sprint 2 — Scoped Context + MoE Router (PR #19)
- `core/routing/moe_router.py`: MoE Gating Network com keyword matching
- `core/memory/session_store.py`: ScopePolicy + get_scoped_view()
- 30 testes novos

### Sprint 3 — Circuit Breaker + Rate Limiter (PR #20)
- `core/resilience/circuit_breaker.py`: 3 estados (CLOSED/OPEN/HALF_OPEN)
- `core/resilience/rate_limiter.py`: Token bucket por tool
- 40 testes novos

### Sprint 4 — Schema Unificado + WORM Audit (PR #21)
- `core/schema/persona_contract.py`: PersonaContract kiosk.aios.io/v1
- `core/audit/worm_audit.py`: SHA-256 hash-chain append-only
- 4 BUILTIN_CONTRACTS (maia, eva, devops, finops)
- 50 testes novos

### Sprint 5 — Autonomy Levels + Forbidden Topics (PR #22)
- `core/policy/autonomy.py`: 3 níveis (auto_execute, supervisor_approval, conditional_hitl)
- `core/gates/forbidden_topics_gate.py`: Gate de tópicos proibidos
- 33 testes novos

### Sprint 6 — HITL Protocol + Handoff Tipado (PR #23)
- `core/governance/hitl_protocol.py`: HITLRequest/Response + PendingStore
- `core/governance/handoff_protocol.py`: 5 tipos (ESCALATION, DELEGATION, etc.)
- 46 testes novos

### Sprint 7 — Integration Pipeline (PR #24)
- `core/integration/__init__.py`: pre_call_pipeline + post_call_pipeline
- `core/broker.py`: opt-in via `persona_id=`
- `backend/orchestrator.py`: AGENT_PERSONA_MAP
- `backend/ws_server.py`: HITL_DECISION handler
- 29 testes novos

### Sprint 8 — Governança Avançada (PR #25)
- **R4**: Persona CX Triage (`cx-triage`) — 5º BUILTIN_CONTRACT
- **R5**: Post-mission gates execution (soft enforcement)
- **R6**: MoE Router wired no Orchestrator (dynamic agent routing)
- **R8**: Forbidden Topics per-persona (carregados do PersonaContract)
- **R9**: Max Hops enforcement + TTL 30s anti-loop
- 49 testes novos

### Sprint 9 — Refinamentos Avançados (PR #26)
- **R7**: Input/Output Contract validation (IOContractConfig)
- **R10**: Dynamic Tool Unbind (CB OPEN → tool removida do catálogo)
- **R11**: RBAC explícito por persona (RBACConfig com allow/deny lists)
- 55 testes novos

### Métricas Finais
| Métrica | Valor |
|:---|:---:|
| Módulos novos | 22 arquivos Python |
| Linhas de código (módulos) | ~4.500 |
| Linhas de código (testes) | ~3.900 |
| Testes automatizados | 421+ |
| BUILTIN PersonaContracts | 5 |
| PRs criados e mergeados | 10 (#17-#26) |
| Sprints executados | 10 (0-9) |
| Cobertura MoE (aplicação) | 100% |

### Gaps Residuais (Infraestrutura — fora do escopo)
- R1: mTLS entre agentes
- R2: JWT para API Gateway
- R3: Sandbox WASM

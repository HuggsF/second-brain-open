# PR Description — Security Hardening P0/P1 (Consolidada)

## Resumo

Security Hardening completo do pipeline MoE/Zero-Trust do KIOSK AI-OS, cobrindo **19 bugs/gaps** (6 P0 + 13 P1) em 11 arquivos de produção, com **14 invariantes negativos** invioláveis e **6 decisões de produto** (PD-OVR) documentadas.

Executado em 6 fases do Manifesto Sem Retrabalho v3.0.0 com auditoria adversarial por 6 revisores independentes.

---

## Pull Requests

### PR #28 — Security Hardening P0/P1 (15 commits)
- **Branch**: `fix/security-hardening-p0-p1`
- **Status**: ✅ Merged
- **Arquivos**: 41 (11 produção + 13 testes novos + 7 PD-OVRs + 4 handoffs + 1 spec + 1 evidence + 4 infra)
- **Diff**: +4896 / -303

### PR #30 — Bloqueantes da Revisão Fria (1 commit)
- **Branch**: `fix/security-hardening-review-blockers`
- **Status**: ✅ Merged
- **Arquivos**: 3 (`forbidden_topics_gate.py`, `integration/__init__.py`, `test_review_blockers.py`)
- **Diff**: +102 / -9

---

## Causa Raiz (por severidade)

### P0 — Críticos

| ID | Causa Raiz | Arquivos |
|----|-----------|----------|
| F-AU-01 | `_extract_amount()` fazia `try: float(val) except: continue` — valores inválidos caíam no `continue`, retornando `None` (= sem campo financeiro) em vez de bloquear. Resultado: auto-aprovação de transferências com formato inválido. | `autonomy.py` |
| F-AU-02 | Nenhuma validação de `amount < 0`. Valores negativos eram tratados como transferências válidas de baixo valor → auto-aprovados. | `autonomy.py` |
| F-IP-05 | RBAC deny chamava `record_tool_outcome(success=False)` no CB → policy deny contado como failure de tool → CB abria desnecessariamente, bloqueando tools legítimas. | `broker.py`, `integration/__init__.py` |
| GAP-HT-01 | WebSocket sem validação de Origin → `HITL_DECISION` podia ser enviado de qualquer página web aberta no navegador do operador. | `ws_server.py` |
| GAP-WS-01 | Cross-Site WebSocket Hijacking — mesma causa do GAP-HT-01. | `ws_server.py` |
| GAP-12 | Pipeline opt-in (`if persona_id:`) — callers sem persona_id bypssavam 100% dos gates de segurança. | `broker.py`, `integration/__init__.py` |

### P1 — Altos

| ID | Causa Raiz | Arquivos |
|----|-----------|----------|
| F-OR-05 | TTL de 30s contava a partir do `mission_start` sem reset após HITL → missions expiravam durante aprovação humana. | `orchestrator.py` |
| F-FT-01 | Substring match (`if pattern in text`) → "pix" casava com "pixel". | `forbidden_topics_gate.py` |
| F-BR-01 | `await _execute(tool, args)` sem timeout → tool podia travar pipeline indefinidamente. | `broker.py` |
| F-WA-02 | `f.write()` sem `os.fsync()` → crash de SO antes de flush do kernel → registro de audit perdido. | `worm_audit.py` |
| F-DLP-04 | DLP regex sem normalização Unicode → Cyrillic "а" evadia `ignore all previous`. | `dlp_guardrail.py` |
| F-IP-01 | Exceção em qualquer gate crashava todo o `pre_call_pipeline` — sem isolamento. | `integration/__init__.py` |
| GAP-FT-01 | `forbidden_topics` do payload podia substituir completamente a base → `{"forbidden_topics": []}` desativava proteção. | `forbidden_topics_gate.py` |
| GAP-13 | `persona_id` aceita sem validação → spoofing de persona. | `broker.py`, `persona_contract.py` |
| GAP-10 | 3/5 agentes (researcher, coder, writer) sem persona mapeada → sem gates de segurança. | `orchestrator.py`, `persona_contract.py` |
| GAP-CB-01 | HALF_OPEN permitia múltiplas requests como "probe" simultaneamente (thundering herd). | `circuit_breaker.py` |
| GAP-SS-01 | `FULL_ACCESS` retornava `list(history)` sem filtro → acesso cross-persona a tool_args e raw_input. | `session_store.py` |
| GAP-06 | DLP/PII scan apenas no input, não no resultado de tools. | `integration/__init__.py` |
| GAP-03 | Múltiplos campos financeiros com valores conflitantes não detectados → shadowing. | `autonomy.py` |

---

## Correções Realizadas

### Arquivos de Produção (11)

| Arquivo | Bugs Corrigidos | Alteração |
|---------|:-:|-----------|
| `core/policy/autonomy.py` | F-AU-01, F-AU-02, GAP-03 | Sentinel `UNPARSEABLE`, `_parse_brl()`, validação negativa/NaN/shadowing |
| `core/broker.py` | F-IP-05, F-BR-01, GAP-12, GAP-13 | Flag `executed`, `asyncio.wait_for(15s)`, pipeline sempre roda, `_validate_persona()` |
| `core/integration/__init__.py` | F-IP-01, F-IP-05, GAP-06, GAP-12, F-04 | Gate isolation try/except, `executed` guard, DLP no resultado, `_redact_value()` recursiva |
| `core/gates/forbidden_topics_gate.py` | F-FT-01, GAP-FT-01, F-03 | Word boundary regex, base imutável + merge, whitespace normalization |
| `backend/ws_server.py` | GAP-WS-01, GAP-HT-01 | `ALLOWED_ORIGINS`, `serve()` factory |
| `backend/orchestrator.py` | F-OR-05, GAP-10 | TTL reset pós-HITL, `AGENT_PERSONA_MAP` completo |
| `core/audit/worm_audit.py` | F-WA-02 | `os.fsync()` após write |
| `core/security/dlp_guardrail.py` | F-DLP-04 | NFKC normalization, `_strip_zero_width()` |
| `core/resilience/circuit_breaker.py` | GAP-CB-01 | `_half_open_permitted` semáforo com 4 pontos de reset |
| `core/memory/session_store.py` | GAP-SS-01 | Ownership check em `FULL_ACCESS`, filtro cross-persona |
| `core/schema/persona_contract.py` | GAP-10, GAP-13 | `persona-researcher`, `persona-writer` como BUILTIN_CONTRACTS |

### Novos Arquivos de Teste (13)

| Teste | Cobertura |
|-------|-----------|
| `test_autonomy_hardening.py` | UNPARSEABLE, negativo, BRL, shadowing |
| `test_broker_timeout.py` | TimeoutError, CB failure após timeout |
| `test_cb_half_open.py` | Semáforo HALF_OPEN, ciclo completo |
| `test_dlp_result.py` | DLP scan no resultado de tools |
| `test_dlp_unicode.py` | Cyrillic evasion, zero-width chars |
| `test_forbidden_topics_hardening.py` | Word boundary, base imutável, merge |
| `test_gate_isolation.py` | Fail-open/fail-closed per gate |
| `test_persona_attestation.py` | Validação persona_id, ValueError |
| `test_pipeline_global.py` | Pipeline sem persona_id, gates globais |
| `test_postcall_guard.py` | `executed` flag, audit trail |
| `test_session_scope.py` | FULL_ACCESS filtro, cross-persona |
| `test_ttl_reset.py` | Reset TTL pós-HITL |
| `test_worm_fsync.py` | `os.fsync()` chamado |
| `test_ws_origin.py` | Origin validation, rejeição |
| `test_review_blockers.py` | F-03 whitespace bypass, F-04 PII em listas |

---

## Evidências e Testes

### Suíte Completa
```
Antes:  882 passed, 16 failed — 35.54s
Depois: 1025 passed, 21 failed — critério ≥887 atendido
```

### Invariantes Negativos: 14/14 PASS
- INV-N01: Nunca auto-aprovar valor não-parseável
- INV-N02: Nunca contar policy deny como CB failure
- INV-N03: Nunca aceitar HITL sem Origin válido
- INV-N04: Nunca permitir payload esvaziar FT base
- INV-N05: Nunca executar sem gates globais
- INV-N06: Nunca await sem timeout
- INV-N07: Nunca substring match em FT
- INV-N08: Nunca falhar silenciosamente em gate de segurança
- INV-N09: Nunca HALF_OPEN múltiplas requests
- INV-N10: Nunca perder audit por crash de SO
- INV-N11: Nunca aprovar valor negativo
- INV-N12: Nunca DLP apenas no input
- INV-N13: Nunca acesso cross-persona sem filtro
- INV-N14: Nunca aceitar persona_id desconhecida

### Revisão Fria (Fase 5)
- 6 auditores independentes em contexto virgem
- 2 bloqueantes encontrados e corrigidos (F-03, F-04)
- 9 findings não-bloqueantes aceitos (P2/Baixa)

---

## Decisões de Produto (PD-OVR)

| ID | Decisão | Arquivo |
|----|---------|--------|
| PD-OVR-001 | F-IP-05 × F-BR-01 independentes | `docs/product-decisions/PD-OVR-001-ip05-br01-independentes.md` |
| PD-OVR-002 | Unicode NFKC apenas para injection scan | `docs/product-decisions/PD-OVR-002-unicode-apenas-injection.md` |
| PD-OVR-003 | TTL reset após HITL, fixo 30s | `docs/product-decisions/PD-OVR-003-ttl-reset-apos-hitl.md` |
| PD-OVR-004 | Fail-open (CB, RL) / Fail-closed (RBAC, FT, Autonomy, Input) | `docs/product-decisions/PD-OVR-004-fail-policy-per-gate.md` |
| PD-OVR-005 | Forbidden topics: base imutável + merge | `docs/product-decisions/PD-OVR-005-forbidden-topics-base-merge.md` |
| PD-OVR-006 | Sem persona_id: gates globais sempre rodam | `docs/product-decisions/PD-OVR-006-policy-sem-persona.md` |

---

## Itens Adiados (Backlog)

8 itens P2/P3 e 2 adiados para research — ver [Decision Ledger](file:///c:/KIOSK/second-brain/docs/superpowers/decisions/2026-10-15-security-hardening-decisions.md) seção 3.

---

## Documentação

| Artefato | Caminho |
|----------|---------|
| Evidence (Fase 1) | `docs/superpowers/evidence/2026-10-15-security-hardening-evidence.md` |
| Spec (Fase 2) | `docs/superpowers/specs/2026-10-15-security-hardening-spec.md` |
| Plan (Fase 3) | `docs/superpowers/plans/2026-10-15-security-hardening-plan.md` |
| Decision Ledger (Fase 6) | `docs/superpowers/decisions/2026-10-15-security-hardening-decisions.md` |
| Handoffs | `docs/handoff/2026-10-15-*-security-hardening-*.md` (4 handoffs) |
| PD-OVRs | `docs/product-decisions/PD-OVR-00{1-6}-*.md` |
| Progress | `.superpowers/sdd/2026-10-15-security-hardening-plan/progress.md` |

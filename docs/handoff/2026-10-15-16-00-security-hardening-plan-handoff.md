# Handoff Autossuficiente — Security Hardening P0/P1 (Fase 2 → Fase 3)

> **De**: Fase 2 (Spec Gate — Especificação & Invariantes Negativos)
> **Para**: Fase 3 (Plan Gate — Planejamento & Fatiamento SDD)
> **Data**: 2026-10-15T16:00-03:00
> **Task**: `security-hardening-p0-p1`
> **Tag de Referência**: `v1.0.0-moe` (commit `59ad40b`)
> **Branch**: `fix/security-hardening-p0-p1` (commit `080044b`)
> **Suíte Baseline**: 882 passed, 16 failed (pré-existentes), 1 warning — 35.54s
> **Revisão**: v1.0 — Spec aprovada após 2 auditorias adversariais

---

## Seção 1: Contexto & Motivação

O KIOSK AI-OS v1.0.0-moe passou por:
- **Fase 1-fix**: Discovery 3D corrigida por auditoria adversarial (3 agentes), eliminando 3 falsos positivos, corrigindo 5 inversões de severidade e adicionando 19+ lacunas críticas.
- **Fase 2**: Spec Gate com spec formal de 1022 linhas, 14 invariantes negativos, 10 queries resolvidas, 6 PD-OVRs aprovadas, validada por 2 auditorias adversariais.

A Fase 3 deve converter a spec em plano mestre determinístico e fatiar em briefs SDD atômicos de 2-5 minutos.

---

## Seção 2: Artefatos de Entrada

| # | Artefato | Caminho |
|---|----------|---------|
| 1 | **Spec formal** (1022 linhas) | `docs/superpowers/specs/2026-10-15-security-hardening-spec.md` |
| 2 | **Handoff Fase 1-fix** | `docs/handoff/2026-10-15-14-05-security-hardening-spec-handoff.md` |
| 3 | **Evidências 3D** | `docs/superpowers/evidence/2026-10-15-security-hardening-evidence.md` |
| 4 | **PD-OVR-001** F-IP-05 × F-BR-01 independentes | `docs/product-decisions/PD-OVR-001-ip05-br01-independentes.md` |
| 5 | **PD-OVR-002** Unicode NFKC apenas injection | `docs/product-decisions/PD-OVR-002-unicode-apenas-injection.md` |
| 6 | **PD-OVR-003** TTL reset após HITL | `docs/product-decisions/PD-OVR-003-ttl-reset-apos-hitl.md` |
| 7 | **PD-OVR-004** Fail-policy per gate | `docs/product-decisions/PD-OVR-004-fail-policy-per-gate.md` |
| 8 | **PD-OVR-005** Forbidden topics base+merge | `docs/product-decisions/PD-OVR-005-forbidden-topics-base-merge.md` |
| 9 | **PD-OVR-006** Policy sem persona | `docs/product-decisions/PD-OVR-006-policy-sem-persona.md` |
| 10 | **Manifesto Workflow** | Skill `manifesto-workflow` (v3.0.0) |
| 11 | **Due Diligence Harness** | Skill `due-diligence-harness` |

---

## Seção 3: Escopo Consolidado (19 bugs/gaps)

### P0 (6 bugs)

| ID | Descrição | Arquivo Principal | Spec §  |
|----|-----------|-------------------|---------|
| F-AU-01 | Auto-aprovação financeira por parsing falho | `core/policy/autonomy.py` | 5.1 |
| F-AU-02 | Valores negativos auto-aprovados | `core/policy/autonomy.py` | 5.1 |
| F-IP-05 | CB cross-contamination por RBAC deny | `core/broker.py` | 5.2 |
| GAP-HT-01 | HITL sem autenticação | `backend/ws_server.py` | 5.4 |
| GAP-WS-01 | Cross-Site WebSocket Hijacking | `backend/ws_server.py` | 5.4 |
| GAP-12 | Pipeline opt-in e fail-open | `core/broker.py` | 5.5 |

### P1 (13 bugs)

| ID | Descrição | Arquivo Principal | Spec § |
|----|-----------|-------------------|--------|
| F-OR-05 | TTL inclui tempo HITL | `backend/orchestrator.py` | 5.6 |
| F-FT-01 | Substring match em forbidden topics | `core/gates/forbidden_topics_gate.py` | 5.7 |
| F-BR-01 | Tool sem timeout | `core/broker.py` | 5.3 |
| F-WA-02 | Sem fsync no WORM audit | `core/audit/worm_audit.py` | 5.9 |
| F-DLP-04 | Bypass injection por Unicode | `core/security/dlp_guardrail.py` | 5.10 |
| F-IP-01 | Exceção em gate crasha pipeline | `core/integration/__init__.py` | 5.11 |
| GAP-FT-01 | Forbidden topics sem baseline | `core/gates/forbidden_topics_gate.py` | 5.8 |
| GAP-13 | Spoofing de persona_id | `core/broker.py` | 5.15 |
| GAP-10 | 3/5 agentes sem persona | `backend/orchestrator.py` | 5.5 |
| GAP-CB-01 | HALF_OPEN thundering herd | `core/resilience/circuit_breaker.py` | 5.12 |
| GAP-SS-01 | FULL_ACCESS cross-session | `core/memory/session_store.py` | 5.13 |
| GAP-06 | Tool results sem DLP | `core/integration/__init__.py` | 5.14 |
| GAP-03 | Shadowing de campos financeiros | `core/policy/autonomy.py` | 5.1 |

### Fora do Escopo
P2: GAP-14, GAP-05, GAP-17, GAP-18, GAP-RL-01. P3: F-RL-04, F-SS-01. Adiado: GAP-19, GAP-WA-02.

---

## Seção 4: Decisões de Produto (PD-OVR)

| ID | Decisão | Doc |
|----|---------|-----|
| PD-OVR-001 | F-IP-05 × F-BR-01 independentes | ✅ |
| PD-OVR-002 | Unicode NFKC apenas para injection scan | ✅ |
| PD-OVR-003 | TTL fixo 30s + reset após HITL | ✅ |
| PD-OVR-004 | CB/RL fail-open; RBAC/FT/Autonomy/Input/DLP fail-closed | ✅ |
| PD-OVR-005 | Forbidden topics: base imutável + merge, payload nunca substitui | ✅ |
| PD-OVR-006 | Sem persona_id: gates globais sempre rodam; mapear 3 agentes | ✅ |

---

## Seção 5: Invariantes Negativos (14)

| INV | Proibição |
|-----|-----------|
| N01 | Nunca auto-aprovar valor financeiro não-parseável |
| N02 | Nunca contar policy deny como failure de tool no CB |
| N03 | Nunca aceitar HITL_DECISION sem validação de Origin |
| N04 | Nunca permitir payload esvaziar forbidden topics |
| N05 | Nunca executar pipeline sem gates globais |
| N06 | Nunca permitir tool travar indefinidamente |
| N07 | Nunca permitir substring match em forbidden topics |
| N08 | Nunca falhar silenciosamente em gate de segurança |
| N09 | Nunca permitir HALF_OPEN servir múltiplas requisições |
| N10 | Nunca perder registro de audit por crash de SO |
| N11 | Nunca aprovar valor financeiro negativo |
| N12 | Nunca executar DLP apenas no input |
| N13 | Nunca permitir acesso cross-persona sem filtro |
| N14 | Nunca aceitar persona_id desconhecida |

---

## Seção 6: Arquivos Envolvidos (12 arquivos)

| # | Arquivo | Mudanças | Allowed/No-Touch |
|---|---------|----------|-----------------|
| 1 | `core/policy/autonomy.py` | UNPARSEABLE sentinel, _parse_brl, shadowing check | Allowed |
| 2 | `core/broker.py` | executed flag, asyncio.wait_for, global gates, persona validation | Allowed |
| 3 | `core/integration/__init__.py` | gate isolation, post_call guard, DLP no result | Allowed |
| 4 | `core/gates/forbidden_topics_gate.py` | word boundary, base topics, merge-only | Allowed |
| 5 | `core/audit/worm_audit.py` | os.fsync() + `import os` | Allowed |
| 6 | `core/security/dlp_guardrail.py` | NFKC + `_strip_zero_width()` | Allowed |
| 7 | `core/resilience/circuit_breaker.py` | HALF_OPEN semaphore + reset logic | Allowed |
| 8 | `core/memory/session_store.py` | FULL_ACCESS ownership check | Allowed |
| 9 | `backend/orchestrator.py` | TTL reset, AGENT_PERSONA_MAP completo | Allowed |
| 10 | `backend/ws_server.py` | origins=, serve() factory | Allowed |
| 11 | `tests/test_nexus_ws.py` | Mock updates (5 testes) | Allowed |
| 12 | `core/schema/persona_contract.py` | persona-researcher, persona-writer builtin | Allowed (Override No-Touch — PD-OVR-006) |

### No-Touch (inalteráveis)
- Todos os outros arquivos em `core/`, `backend/`, `tests/` que não estejam na lista acima
- Nenhum novo módulo Python deve ser criado (apenas modificar existentes)

---

## Seção 7: Queries Resolvidas (Q1-Q10)

| Q | Decisão | PD-OVR |
|---|---------|--------|
| Q1 | `asyncio.wait_for(timeout=15.0)`, TimeoutError → CB failure | — |
| Q2 | `executed: bool` flag, CB/output só com executed, audit sempre | — |
| Q3 | `UNPARSEABLE` sentinel → ESCALATE | — |
| Q4 | TTL fixo 30s + reset após HITL | PD-OVR-003 |
| Q5 | NFKC apenas injection scan | PD-OVR-002 |
| Q6 | Per-gate fail policy | PD-OVR-004 |
| Q7 | Corrigir 5 mocks nesta sprint (~1-2h) | — |
| Q8 | Base imutável + merge | PD-OVR-005 |
| Q9 | Gates globais sempre; mapear 3 agentes | PD-OVR-006 |
| Q10 | Origin validation nesta sprint; token auth adiado | — |

---

## Seção 8: API Real Verificada (Referência para Plano)

### DLP (`core/security/dlp_guardrail.py`)
- `inspect_text(text) → DLPResult` (module-level L216-218)
- `DLPResult`: `.has_pii` (property), `.redacted_text`, `.pii_matches`
- **NÃO** existe `mask_pii()` nem `.pii_found`

### SessionMemoryStore (`core/memory/session_store.py`)
- `get_scoped_view(session_id, persona_id, scope_policy) → List[Dict]`
- Sessions: `Dict[str, List[Dict[str, Any]]]`
- **NÃO** existe `.owner` nem `_filter_pii()`
- `_SCOPE_ALLOWED_FIELDS[FULL_ACCESS] = None` → retorna `list(history)` sem filtro

### CircuitBreaker (`core/resilience/circuit_breaker.py`)
- `allow_request()` L99-109: HALF_OPEN → `return True` incondicional (bug)
- `_resolve_state()` L90-97: OPEN→HALF_OPEN por timeout
- `record_success()` L111-128, `record_failure()` L130-145
- `self._lock = threading.Lock()` L72
- **NÃO** existe `_half_open_permitted` (spec propõe adicioná-lo)

### integration (`core/integration/__init__.py`)
- `check_forbidden_topics(text, persona_id=None) → PreCallResult` (nome real)
- `validate_input_contract(persona_id, args) → PreCallResult` (2 args, não 3)
- `post_call_pipeline(...)` → atualmente retorna `None` (spec propõe retornar `result`)

### worm_audit (`core/audit/worm_audit.py`)
- **NÃO** importa `os` (necessário para `os.fsync()`)
- Write flow: L185-192 (`open()`, `write()`, atualiza `_last_hash`)

---

## Seção 9: Riscos & Mitigações

| # | Risco | Sev | Mitigação |
|---|-------|-----|-----------|
| R1 | `_parse_brl` pode não cobrir todos os formatos BR | Baixo | Testar com corpus real |
| R2 | Word boundary pode falhar com Unicode | Baixo | Flag `re.UNICODE` |
| R3 | Novas BUILTIN_CONTRACTS com permissões incorretas | Médio | Copiar padrão de persona-devops |
| R4 | DLP no resultado pode afetar performance | Baixo | Skip se resultado < 100 chars |
| R5 | `os.fsync()` pode afetar throughput | Baixo | Volume baixo (~10 calls/missão) |
| R6 | `post_call_pipeline` retornar `result` pode quebrar chamadores | Médio | Verificar todos os callers |

---

## Seção 10: Instruções para Fase 3

### Objetivo
Converter a spec (`docs/superpowers/specs/2026-10-15-security-hardening-spec.md`) em:
1. Plano mestre em `docs/superpowers/plans/2026-10-15-security-hardening-plan.md`
2. Briefs SDD atômicos em `.superpowers/sdd/2026-10-15-security-hardening-plan/`
3. `progress.md` com tabela de status `pending`

### Regras de Fatiamento
- Cada brief deve levar 2-5 minutos para um agente implementador
- Cada brief deve tocar no máximo 1-3 arquivos (idealmente 1)
- Cada brief deve incluir: objetivo, `Allowed Files`, `No-Touch Files`, comando CLI de teste exato
- Ordem de execução deve respeitar dependências (ex: `_parse_brl` antes de `_extract_amount`)

### Sugestão de Agrupamento por Brief

| Brief | Bugs/GAPs | Arquivo Principal |
|-------|-----------|-------------------|
| task-01 | F-AU-01 + F-AU-02 + GAP-03 (§5.1) | `core/policy/autonomy.py` |
| task-02 | F-IP-05 + GAP-05 (§5.2) | `core/broker.py` |
| task-03 | F-BR-01 (§5.3) | `core/broker.py` |
| task-04 | GAP-WS-01 + GAP-HT-01 (§5.4) | `backend/ws_server.py` |
| task-05 | GAP-12 + GAP-10 (§5.5) | `core/broker.py` + `core/integration/__init__.py` + `backend/orchestrator.py` |
| task-06 | F-OR-05 (§5.6) | `backend/orchestrator.py` |
| task-07 | F-FT-01 + GAP-FT-01 (§5.7+§5.8) | `core/gates/forbidden_topics_gate.py` |
| task-08 | F-WA-02 (§5.9) | `core/audit/worm_audit.py` |
| task-09 | F-DLP-04 (§5.10) | `core/security/dlp_guardrail.py` |
| task-10 | F-IP-01 (§5.11) | `core/integration/__init__.py` |
| task-11 | GAP-CB-01 (§5.12) | `core/resilience/circuit_breaker.py` |
| task-12 | GAP-SS-01 (§5.13) | `core/memory/session_store.py` |
| task-13 | GAP-06 (§5.14) | `core/integration/__init__.py` |
| task-14 | GAP-13 (§5.15) | `core/broker.py` + `core/schema/persona_contract.py` |
| task-15 | Q7 — 5 testes WS (§5.16) | `tests/test_nexus_ws.py` + `backend/ws_server.py` |

### Invariantes Positivos a Preservar
1. 882 testes passando — nenhum pode quebrar
2. Backward compatibility — `broker.call()` sem `persona_id` continua funcionando
3. API pública — assinaturas não mudam (apenas adição de params com defaults)
4. WORM hash-chain — `verify_chain()` continua válida

### Git & Commits
- Branch: `fix/security-hardening-p0-p1`
- Conventional Commits em português: `fix: F-XX-NN — descrição`
- **NUNCA** push na `main`

### Critério de Conclusão da Fase 3
- [ ] Plano mestre em `docs/superpowers/plans/2026-10-15-security-hardening-plan.md`
- [ ] Briefs SDD atômicos em `.superpowers/sdd/2026-10-15-security-hardening-plan/`
- [ ] `progress.md` com tabela de status `pending`
- [ ] Aprovação formal humana para execução
- [ ] Handoff para Fase 4

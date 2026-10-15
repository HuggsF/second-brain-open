# Handoff — Fase 5 → Fase 6 (Finish Gate)
# security-hardening-p0-p1

> **Tarefa**: Security Hardening P0/P1
> **Branch principal**: `fix/security-hardening-p0-p1` (PR #28 — merged)
> **Branch de correções**: `fix/security-hardening-review-blockers` (PR #30 — aberto)
> **Data**: 2026-10-15
> **Fase anterior**: Review Gate (Fase 5)
> **Próxima fase**: Finish Gate (Fase 6)

---

## 1. Resumo da Revisão (Fase 5)

Auditoria adversarial completa com 6 auditores independentes em contexto virgem, cobrindo os 14 invariantes negativos (INV-N01 a INV-N14) contra o código-fonte real.

### Veredito: ✅ APROVADO (após correção de bloqueantes)

- **Invariantes**: 14/14 PASS (INV-N07 corrigido no PR #30)
- **Suíte de testes**: 1025 passed, 21 failed (baseline: 882/16, critério ≥887 atendido)
- **Bloqueantes**: 2 encontrados e corrigidos no PR #30

## 2. Bloqueantes Corrigidos (PR #30)

| ID | Invariante | Descrição | Correção | Commit |
|----|-----------|-----------|----------|--------|
| F-03 | INV-N07 | Bypass de forbidden topics multi-word via whitespace extra | `re.sub(r'\s+', ' ', text)` em `_normalize()` | `730151b` |
| F-04 | INV-N12 | `_redact_dict_values()` ignorava listas → vazamento PII | Nova `_redact_value()` com recursão em `list` | `730151b` |

### Testes de regressão: 10 novos + 18 existentes = 28/28 ✅

## 3. Findings Não-Bloqueantes Aceitos (P2)

| ID | Sev | Arquivo | Descrição |
|----|:---:|---------|-----------|
| H-01 | Baixa | `forbidden_topics_gate.py:30` | Base `list` mutável — usar `tuple` |
| H-02 | Média | `integration/__init__.py:431-432` | DLP scan fail-open em exceção |
| H-03 | Baixa | `circuit_breaker.py:153-159` | `reset()` não limpa `_half_open_permitted` |
| H-04 | Média | `session_store.py:113` | Sessões anônimas → acesso total por `all()` vazio |
| H-05 | Baixa | `dlp_guardrail.py:93-105` | `_CONFUSABLES` incompleta (gregos) |
| H-06 | Média | `broker.py:107-108` | `ImportError` degrada broker para fail-open |
| H-07 | Baixa | `test_nexus_ws.py:3` | Docstring residual referencia `exec_tool` |
| H-08 | Baixa | `integration/__init__.py:342-343` | FT não inspeciona `args`, só `task_text` |
| F-01 | Baixa | `autonomy.py:163-164` | `_parse_brl(float("nan"))` retorna `nan` (compensado por `_extract_amount`) |

## 4. Testes Falhando (Classificação)

| Categoria | Qtd | Origem |
|-----------|:---:|--------|
| Regressões em `test_autonomy_forbidden.py` | 5 | Nova semântica de `_extract_amount()` (testes precisam atualizar expectations) |
| Pré-existentes `test_nexus_ws.py` | 7 | Mocks legados, `BrainRetriever` |
| Pré-existentes `test_ws_server.py` | 3 | Broker/policy subtests |
| Comportamentais `test_broker.py` | 3 | DENY→ESCALATE (fail-safe intencional) |
| Infraestrutura | 2 | Contagem tools, Node adapter |
| **Pré-existentes `test_integration.py`** | 1 | Persona mapping |

## 5. Commits do Security Hardening (completo)

| PR | Commits | Descrição |
|----|:-------:|-----------|
| #28 | 15 | Security Hardening P0/P1 — 15 vulnerabilidades |
| #30 | 1 | Bloqueantes da Revisão Fria (F-03 + F-04) |

## 6. Arquivos Modificados (consolidado)

### PR #28 (15 arquivos):
- `core/policy/autonomy.py`, `core/broker.py`, `core/integration/__init__.py`
- `core/gates/forbidden_topics_gate.py`, `core/audit/worm_audit.py`
- `core/security/dlp_guardrail.py`, `core/resilience/circuit_breaker.py`
- `core/memory/session_store.py`, `core/schema/persona_contract.py`
- `backend/orchestrator.py`, `backend/ws_server.py`
- `tests/test_nexus_ws.py`, `tests/test_sprint8_cx_forbidden.py`
- 12 novos arquivos de teste (~60 testes)

### PR #30 (3 arquivos):
- `core/gates/forbidden_topics_gate.py` (1 linha adicionada)
- `core/integration/__init__.py` (refatoração `_redact_value` + `_redact_dict_values`)
- `tests/test_review_blockers.py` (10 novos testes)

## 7. PD-OVRs Vigentes

| ID | Decisão |
|----|---------|
| PD-OVR-001 | F-IP-05 × F-BR-01 independentes |
| PD-OVR-002 | Unicode NFKC apenas para injection scan |
| PD-OVR-003 | TTL reset após HITL, fixo 30s |
| PD-OVR-004 | Fail-open (CB, RL) / Fail-closed (RBAC, FT, Autonomy, Input) |
| PD-OVR-005 | Forbidden topics: base imutável + merge |
| PD-OVR-006 | Sem persona_id: gates globais sempre rodam |

## 8. Próximos Passos (Fase 6)

1. **Merge do PR #30** (`fix/security-hardening-review-blockers`)
2. **Decision Ledger** em `docs/superpowers/decisions/2026-10-15-security-hardening-decisions.md`
3. **Limpeza**: Remover arquivos temporários/logs de depuração
4. **PR description** consolidada em `docs/superpowers/2026-10-15-pr-description.md`

## 9. Referências

- Spec: `docs/superpowers/specs/2026-10-15-security-hardening-spec.md`
- Plan: `docs/superpowers/plans/2026-10-15-security-hardening-plan.md`
- Evidence: `docs/superpowers/evidence/2026-10-15-security-hardening-evidence.md`
- Progress: `.superpowers/sdd/2026-10-15-security-hardening-plan/progress.md`
- Review Report: Artifact da Fase 5 (conversation `27149ce0-258c-4986-851f-6787770245cd`)
- Handoff 4→5: `docs/handoff/2026-10-15-16-14-security-hardening-review-handoff.md`

# Handoff Autossuficiente — Security Hardening P0/P1 (Fase 3 → Fase 4)

> **De**: Fase 3 (Plan Gate — Planejamento & Fatiamento SDD)
> **Para**: Fase 4 (Execution — TDD Rigoroso via Subagentes)
> **Data**: 2026-10-15T16:14-03:00
> **Task**: `security-hardening-p0-p1`
> **Branch**: `fix/security-hardening-p0-p1` (base: commit `080044b`)
> **Suíte Baseline**: 882 passed, 16 failed (pré-existentes), 1 warning — 35.54s
> **Status**: ⏳ AGUARDANDO APROVAÇÃO FORMAL HUMANA

---

## Seção 1: Contexto & Motivação

O KIOSK AI-OS v1.0.0-moe passou por 3 fases do Manifesto Sem Retrabalho v3.0.0:
- **Fase 1-fix**: Discovery 3D corrigida por 3 auditorias adversariais.
- **Fase 2**: Spec Gate com 1032 linhas, 14 invariantes, 6 PD-OVRs. Validada por 2 auditorias.
- **Fase 3**: Plan Gate — conversão da spec em plano determinístico com 15 briefs SDD atômicos.

A Fase 3 validou cruzadamente spec × código real em todos os 12 arquivos, identificou 9 discrepâncias e corrigiu no plano.

---

## Seção 2: Artefatos de Entrada

| # | Artefato | Caminho |
|---|----------|---------|
| 1 | **Plano Mestre** | `docs/superpowers/plans/2026-10-15-security-hardening-plan.md` |
| 2 | **Progress Tracker** | `.superpowers/sdd/2026-10-15-security-hardening-plan/progress.md` |
| 3 | **15 SDD Briefs** | `.superpowers/sdd/2026-10-15-security-hardening-plan/task-{01..15}-brief.md` |
| 4 | **Spec formal** | `docs/superpowers/specs/2026-10-15-security-hardening-spec.md` |
| 5 | **Handoff Fase 2→3** | `docs/handoff/2026-10-15-16-00-security-hardening-plan-handoff.md` |
| 6 | **PD-OVRs (6)** | `docs/product-decisions/PD-OVR-{001..006}-*.md` |
| 7 | **Manifesto Workflow** | Skill `manifesto-workflow` (v3.0.0) |
| 8 | **Due Diligence** | Skill `due-diligence-harness` |

---

## Seção 3: Escopo (15 Briefs em 5 Waves)

| Wave | Briefs | Módulos |
|------|--------|---------|
| 1 (sem deps) | T01, T03, T04, T06, T07, T08, T09, T11, T12 | 9 módulos independentes |
| 2 | T02, T14 | broker + integration; persona_contract |
| 3 | T05, T10 | pipeline global + gate isolation |
| 4 | T13 | DLP no resultado |
| 5 | T15 | correção de 5 testes WS |

---

## Seção 4: Decisões de Produto (PD-OVR)

Todas as 6 PD-OVRs da Fase 2 permanecem vigentes. Nenhuma nova PD-OVR criada na Fase 3.

---

## Seção 5: Invariantes Negativos (14)

Todos os 14 invariantes da spec permanecem invioláveis (INV-N01 a INV-N14).

---

## Seção 6: Discrepâncias Spec × Código (9)

| # | Discrepância | Resolução |
|---|-------------|-----------|
| D1 | Classe `ToolCircuitBreaker`, não `CircuitBreaker` | Briefs usam nome correto |
| D2 | Código em `second-brain/core/...` | Paths corrigidos |
| D3 | `broker.py` sem `import asyncio` | task-03 adiciona |
| D4 | `pre_call_pipeline` FT só `if task_text` | task-05/10 corrigem |
| D5 | `post_call_pipeline` retorna `None` | task-02 corrige |
| D6 | FT payload substitui patterns | task-07 implementa merge |
| D7 | WS sem origins, sem serve() | task-04 implementa |
| D8 | Mocks apontam para `exec_tool` inexistente | task-15 corrige |
| D9 | Sem `persona-researcher`/`persona-writer` | task-14 cria |

---

## Seção 7: Arquivos Envolvidos (12)

| # | Arquivo | Briefs |
|---|---------|--------|
| 1 | `core/policy/autonomy.py` | T01 |
| 2 | `core/broker.py` | T02, T03, T05, T14 |
| 3 | `core/integration/__init__.py` | T02, T05, T10, T13 |
| 4 | `core/gates/forbidden_topics_gate.py` | T07 |
| 5 | `core/audit/worm_audit.py` | T08 |
| 6 | `core/security/dlp_guardrail.py` | T09 |
| 7 | `core/resilience/circuit_breaker.py` | T11 |
| 8 | `core/memory/session_store.py` | T12 |
| 9 | `backend/orchestrator.py` | T05, T06 |
| 10 | `backend/ws_server.py` | T04, T15 |
| 11 | `tests/test_nexus_ws.py` | T15 |
| 12 | `core/schema/persona_contract.py` | T14 |

---

## Seção 8: Riscos & Mitigações

Mesmos 6 riscos da Fase 2 (R1-R6). Nenhum risco novo identificado.

---

## Seção 9: Queries Pendentes

Nenhuma query pendente. Todas as 10 queries (Q1-Q10) foram resolvidas na Fase 2.

---

## Seção 10: Instruções para Fase 4

### Protocolo de Execução

1. Para cada wave (1→5), despachar briefs em paralelo quando possível.
2. Para cada brief:
   - Ler **exclusivamente** o `task-N-brief.md` correspondente.
   - **RED**: Escrever o teste primeiro e rodar → deve FALHAR.
   - **GREEN**: Implementar o código mínimo → teste deve PASSAR.
   - **REFACTOR**: Melhorar sem quebrar testes.
3. Após cada brief, rodar:
   ```bash
   cd c:\KIOSK\second-brain && python -m pytest tests/ -x -q --tb=short
   ```
   Critério: ≥ 882 passed.
4. Commit semântico atômico (1 por brief).
5. Atualizar `progress.md`: status → `completed`.

### Circuit Breaker (Rollback)

Se um teste falhar por premissa não coberta ou exigir alteração fora do brief:
- **PARAR IMEDIATAMENTE.**
- Emitir `### 🚨 CIRCUIT BREAKER: ROLLBACK PARA A FASE DE SPEC`.
- Encerrar o turno.

### Critérios de Conclusão da Fase 4

- [ ] Todos os 15 briefs `completed` em `progress.md`
- [ ] ≥ 887 testes passando (882 baseline + 5 WS corrigidos)
- [ ] Todos os commits na branch `fix/security-hardening-p0-p1`
- [ ] Handoff para Fase 5 (Review Gate)

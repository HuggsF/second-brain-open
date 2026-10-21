# Handoff Autossuficiente — V1 Clean Architecture Constants (Fase 2 → Fase 3)

> **De:** Fase 2 (Spec Gate) → **Para:** Fase 3 (Plan Gate)  
> **Data:** 17/10/2026 · **Task:** v1-clean-arch-constants  
> **Branch:** `refactor/v1-clean-arch-constants`  
> **Pré-requisito:** Architecture Assessment (Violação V1 identificada, aprovada pelo Tech Lead)

---

## 1. Contexto do Problema

`core/graph/nodes.py:74-78` (camada Application) importa 3 constantes de `backend/orchestrator.py` (camada Interface), violando a Dependency Rule da Clean Architecture. As constantes `AGENT_PERSONA_MAP`, `DEFAULT_STEPS` e `MISSION_PATTERNS` são dados de domínio de workflow que pertencem a `core/domain/workflow/`.

---

## 2. O que foi feito nesta Fase

Especificação formal com:
- 8 invariantes negativos (INV-N01 a INV-N08)
- 7 critérios de aceite com comandos CLI de verificação
- Mapa completo de blast radius: 2 arquivos de produção + 2 arquivos de teste + 1 novo arquivo
- 6 testes legados NÃO alterados (re-export preserva retrocompatibilidade)
- 3 decisões de design (DQ-01 a DQ-03) resolvidas
- Risco R1 **confirmado e investigado** — `sys.modules` injection em 2 test files

---

## 3. Evidências Produzidas

- [Spec Formal](file:///c:/KIOSK/second-brain-WO-0001/docs/superpowers/specs/2026-10-17-v1-clean-arch-constants-spec.md) — 10 seções
- [Architecture Assessment](file:///C:/Users/HugoMelo/.gemini/antigravity/brain/83e8e607-f494-4e31-ac3b-110dd2444c23/architecture-assessment.md) — Diagnóstico original (Fase 1 equivalente)

---

## 4. Decisões Tomadas

| Decisão | Justificativa |
|---------|---------------|
| Move + Re-export (não Extract + Delete) | Preserva retrocompatibilidade durante Strangler Fig window |
| `__all__` explícito em `constants.py` | Segue padrão de todos os módulos `core/` |
| Re-export via `from ... import` direto | Mais legível e IDE-friendly que atribuição |
| Testes do graph SERÃO atualizados | `sys.modules` injection precisa apontar para novo módulo |
| Testes legados NÃO alterados | Re-export em orchestrator.py garante compatibilidade |

---

## 5. Riscos e Dívidas

| Risco | Prob. | Impacto | Status |
|-------|:---:|:---:|--------|
| R1: `sys.modules["backend.orchestrator"]` em testes graph | **Alta** | **Alto** | ✅ Investigado — mocks DEVEM mudar para `core.domain.workflow.constants` |
| R2: Circular import `constants.py` ↔ `entities.py` | Baixa | Médio | ✅ Mitigado: `constants.py` não importa nada do projeto |
| R3: Side effects em module-level de orchestrator | Baixa | Baixo | ✅ Mitigado: constantes são dicts/lists puros |

---

## 6. Mapa de Arquivos

| Arquivo | Ação |
|---------|:----:|
| `core/domain/workflow/constants.py` | CREATE |
| `core/graph/nodes.py` | MODIFY (linhas 74-78) |
| `backend/orchestrator.py` | MODIFY (linhas 41-90) |
| `tests/test_graph_unit.py` | MODIFY (linhas 542-548) |
| `tests/test_graph_integration.py` | MODIFY (linhas 37, 51-54, 202-207) |

---

## 7. Estado dos Testes

| Suíte | Antes | Status |
|-------|:-----:|:------:|
| Backend (pytest) | 1.212 pass | Baseline inalterado (Fase 2 = +0/-0) |
| Frontend (Nexus) | 11 pass | Baseline inalterado |

---

## 8. DoD — Checklist da Fase 2 (Spec Gate)

- [x] Handoff da Fase 1 lido (architecture-assessment.md)
- [x] Casos de borda questionados: circular imports, sys.modules injection, side effects
- [x] 8 Invariantes Negativos declarados (INV-N01 a INV-N08)
- [x] 7 Critérios de Aceite com comandos CLI
- [x] Blast radius completo mapeado (2 prod + 2 test + 1 novo + 6 legados inalterados)
- [x] Risco R1 confirmado com evidência de código
- [x] 3 decisões de design resolvidas (DQ-01 a DQ-03)
- [x] Aprovação formal humana obtida ✅
- [x] Saldo de código: +0 / -0

---

## 9. Queries para Plan Gate

1. **Ordenação dos briefs:** Qual a ordem ótima? Sugestão: (1) CREATE constants.py → (2) MODIFY nodes.py → (3) MODIFY orchestrator.py → (4) UPDATE tests → (5) Validação final
2. **Granularidade dos briefs:** 5 briefs atômicos ou consolidar (2) e (3) num único brief?

---

## 10. Próximo Passo

**Fase 3 (Plan Gate):** Converter a spec em plano determinístico com briefs SDD atômicos. Cada brief deve ter objetivo, comando CLI exato, `Allowed Files` e `No-Touch Files`. **PARAR e exigir aprovação formal humana antes da execução.**

---

*Handoff gerado seguindo o Manifesto Sem Retrabalho v3.0.0 — 10 seções canônicas. Saldo de código: +0 / -0.*

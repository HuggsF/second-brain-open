# Decision Ledger — V1 Clean Architecture: Extração de Constantes de Domínio

> **Ciclo:** V1 Clean Arch Constants  
> **Data:** 17/10/2026  
> **PRs:** [#44](https://github.com/HuggsF/second-brain/pull/44)  
> **Branch:** `refactor/v1-clean-arch-constants`  
> **Commit:** `60b25ae`

---

## Decisões Técnicas

### DT-01 — Move + Re-export (não Extract + Delete)

**Contexto:** As 3 constantes (`AGENT_PERSONA_MAP`, `DEFAULT_STEPS`, `MISSION_PATTERNS`) precisavam sair de `backend/orchestrator.py` para `core/domain/workflow/constants.py`, mas 6 arquivos de teste importam de `backend.orchestrator`.

**Decisão:** Mover definições para o domínio e manter re-export em `backend/orchestrator.py` via `from core.domain.workflow.constants import ...`.

**Alternativas descartadas:**
- *Extract + Delete:* quebraria 6 arquivos de teste legados e todos os consumidores que importam de `backend.orchestrator`.
- *Alias (atribuição):* `AGENT_PERSONA_MAP = constants.AGENT_PERSONA_MAP` — não preserva identity (`is`), cria cópia de referência desnecessária.

**Consequências:** Zero quebra. Re-export será removido quando o Strangler Fig migration window fechar (~4 semanas).

---

### DT-02 — `sys.modules` injection atualizado nos testes graph

**Contexto:** `test_graph_unit.py` e `test_graph_integration.py` usam `sys.modules["backend.orchestrator"]` para injetar mocks nas lazy imports do `plan_node`.

**Decisão:** Atualizar a chave de `sys.modules` para `"core.domain.workflow.constants"` em ambos os arquivos.

**Justificativa:** O `plan_node` agora faz `from core.domain.workflow.constants import ...`, então o mock precisa interceptar o novo módulo.

---

### DT-03 — `constants.py` sem imports do projeto

**Contexto:** `core/domain/workflow/entities.py` importa de `core/domain/nexus/entities.py`. A questão era se `constants.py` deveria importar de `entities.py` (e.g., para validar tipos dos steps).

**Decisão:** `constants.py` tem **zero imports do projeto**. Apenas dados puros (dicts e lists) sem dependências.

**Justificativa:** Minimiza risco de circular import e mantém o módulo como leaf node no grafo de dependências.

---

### DT-04 — Constantes de protocolo (`MAX_*`) permanecem no orchestrator

**Contexto:** `MAX_MESSAGE_CHARS` (1000) e `MAX_BUBBLE_CHARS` (240) são definidos no `orchestrator.py`.

**Decisão:** Não mover. São constantes de protocolo de interface (limites do `event-protocol.js` do Nexus), não dados de domínio.

**Justificativa:** Pertencem à camada de Interface, não ao domínio de workflow.

---

## Tech Debt Registry

| ID | Descrição | Prazo | Status |
|----|-----------|-------|:------:|
| **V1** | ~~`core/graph/nodes.py` importa de `backend.orchestrator`~~ | ~~4 semanas~~ | ✅ **RESOLVIDO** |
| **V1-RE** | Re-export em `backend/orchestrator.py` deve ser removido ao fechar Strangler Fig | 4 semanas (de 17/10/2026) | 🟡 Pendente |
| **V2** | Import direto de telemetria no `entrypoint.py` | Backlog | 🟢 Baixa |
| **V3** | Service Locator lazy em `telemetry.py` | Backlog | 🟢 Baixa |

---

*Decision Ledger gerado seguindo o Manifesto Sem Retrabalho v3.0.0 — Fase 6.*

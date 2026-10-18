# Especificação — V1 Clean Architecture: Extração de Constantes de Domínio

> **Fase:** 2 — Spec Gate  
> **Data:** 17/10/2026  
> **Task:** v1-clean-arch-constants  
> **Branch:** `refactor/v1-clean-arch-constants`  
> **Handoff de origem:** [architecture-assessment.md](file:///C:/Users/HugoMelo/.gemini/antigravity/brain/83e8e607-f494-4e31-ac3b-110dd2444c23/architecture-assessment.md) (Violação V1)  
> **Pré-requisito:** PR #42 mergeada (`main` em `efd6892`)

---

## 1. Problema

A camada de **Application** (`core/graph/nodes.py:74-78`) importa 3 constantes de domínio da camada de **Interface** (`backend/orchestrator.py`):

```python
# core/graph/nodes.py:74-78 — VIOLAÇÃO
from backend.orchestrator import (
    AGENT_PERSONA_MAP,      # L41-47 do orchestrator
    DEFAULT_STEPS,          # L88-90 do orchestrator
    MISSION_PATTERNS,       # L50-85 do orchestrator
)
```

Isso viola a **Dependency Rule** da Clean Architecture: dependências devem apontar **para dentro** (Interface → Application → Domain). Aqui, Application aponta para Interface.

### Causa Raiz

As constantes foram originalmente definidas no `backend/orchestrator.py` (Sprint 7) porque era o único consumidor. Com a introdução do Node Loop Graph (`core/graph/`), o `plan_node` precisou dos mesmos dados e fez um import lazy como atalho temporário (Strangler Fig pattern — DT-07 no Decision Ledger).

### Classificação

**(c) Regra defasada (ADR drift)** — as constantes pertencem ao domínio de workflow, não à camada de interface/transporte.

---

## 2. Solução Proposta

Criar `core/domain/workflow/constants.py` como **Single Source of Truth** para as 3 constantes, e atualizar todos os importadores:

```
core/domain/workflow/
├── __init__.py          (existente)
├── entities.py          (existente — Step, Mission, AgentEvent)
└── constants.py         (NOVO — AGENT_PERSONA_MAP, DEFAULT_STEPS, MISSION_PATTERNS)
```

### Estratégia: Move + Re-export

1. **Mover** as definições de `backend/orchestrator.py` para `core/domain/workflow/constants.py`
2. **Re-exportar** de `backend/orchestrator.py` via `from core.domain.workflow.constants import ...` para manter retrocompatibilidade durante o Strangler Fig window
3. **Atualizar** `core/graph/nodes.py` para importar de `core.domain.workflow.constants`
4. **Não alterar** nenhum teste legado que importa de `backend.orchestrator` (re-export garante compatibilidade)

---

## 3. Invariantes Negativos (o que é PROIBIDO)

| # | Invariante | Justificativa |
|---|-----------|---------------|
| **INV-N01** | `core/graph/**` NUNCA importa de `backend/**` | Dependency Rule: Application → Domain, nunca Application → Interface |
| **INV-N02** | `core/domain/**` NUNCA importa de `backend/**` nem de `core/graph/**` | Domain layer é o núcleo — zero dependências outward |
| **INV-N03** | As constantes `AGENT_PERSONA_MAP`, `DEFAULT_STEPS` e `MISSION_PATTERNS` NÃO podem ser definidas em `backend/orchestrator.py` | Source of Truth único em `core/domain/workflow/constants.py` |
| **INV-N04** | Nenhum teste existente pode falhar após a refatoração | Zero regressão — re-export garante retrocompatibilidade |
| **INV-N05** | O re-export em `backend/orchestrator.py` NÃO pode alterar o valor das constantes | Import + re-assign é proibido. Deve ser `from ... import *` ou import explícito |
| **INV-N06** | Nenhum comportamento funcional pode mudar | Refatoração pura de estrutura — mesmo input → mesmo output |
| **INV-N07** | `MAX_MESSAGE_CHARS` e `MAX_BUBBLE_CHARS` permanecem em `backend/orchestrator.py` | São constantes de protocolo de interface, não de domínio |
| **INV-N08** | O docstring/comentário de `constants.py` DEVE proibir imports de I/O, HTTP ou WebSocket | Mesmo padrão de `entities.py:8` |

---

## 4. Critérios de Aceite

| # | Critério | Comando de Verificação |
|---|---------|----------------------|
| **AC-01** | `core/domain/workflow/constants.py` existe e define `AGENT_PERSONA_MAP`, `DEFAULT_STEPS`, `MISSION_PATTERNS` | `C:\Python314\python.exe -c "from core.domain.workflow.constants import AGENT_PERSONA_MAP, DEFAULT_STEPS, MISSION_PATTERNS; print('OK')"` |
| **AC-02** | `core/graph/nodes.py` importa de `core.domain.workflow.constants`, NÃO de `backend.orchestrator` | `Select-String -Path "core\graph\nodes.py" -Pattern "from backend"` → 0 matches |
| **AC-03** | `backend/orchestrator.py` re-exporta as 3 constantes de `core.domain.workflow.constants` | `C:\Python314\python.exe -c "from backend.orchestrator import AGENT_PERSONA_MAP; print(AGENT_PERSONA_MAP)"` |
| **AC-04** | Suíte completa de testes backend passa (0 failures) | `C:\Python314\python.exe -m pytest tests/ -v --tb=short` |
| **AC-05** | Suíte de testes frontend Nexus passa (0 failures) | `node --test --test-isolation=none nexus/tests/adapters.test.mjs` |
| **AC-06** | Grep por `from backend` em `core/` retorna 0 matches | `Get-ChildItem -Path "core" -Filter "*.py" -Recurse \| Select-String "from backend"` |
| **AC-07** | `constants.py` tem zero imports de I/O, HTTP, WebSocket | `Select-String -Path "core\domain\workflow\constants.py" -Pattern "import (aiohttp\|websockets\|asyncio\|pathlib\|os\|json)"` → 0 |

---

## 5. Blast Radius — Mapa de Consumidores

### 5.1 Produção (2 arquivos)

| Arquivo | Constantes usadas | Ação |
|---------|-------------------|------|
| `backend/orchestrator.py` L41-90 | **Define** `AGENT_PERSONA_MAP`, `MISSION_PATTERNS`, `DEFAULT_STEPS` | MODIFY: mover definições → re-export |
| `core/graph/nodes.py` L74-78 | **Importa** as 3 constantes | MODIFY: alterar import source |

### 5.2 Testes (6 arquivos — NÃO alterados)

| Arquivo | Importa de | Ação |
|---------|-----------|------|
| `tests/test_integration.py` L289,297 | `backend.orchestrator` | NENHUMA (re-export preserva) |
| `tests/test_mission_guard.py` L9 | `backend.orchestrator` | NENHUMA (re-export preserva) |
| `tests/test_nexus_ws.py` L149-177 | `backend.orchestrator` (module ref) | NENHUMA (re-export preserva) |
| `tests/test_pipeline_global.py` L5 | `backend.orchestrator` | NENHUMA (re-export preserva) |
| `tests/test_sprint8_moe_wiring.py` L15-16 | `backend.orchestrator` | NENHUMA (re-export preserva) |
| `tests/test_sprint8_postmission_hops.py` L20 | `backend.orchestrator` | NENHUMA (re-export preserva) |
| `tests/test_graph_unit.py` L543-545 | Mock via `sys.modules["backend.orchestrator"]` | MODIFY: apontar mock para `core.domain.workflow.constants` |
| `tests/test_graph_integration.py` L46-54,207 | Mock via `sys.modules["backend.orchestrator"]` | MODIFY: apontar mock para `core.domain.workflow.constants` |

### 5.3 Novo arquivo (1 arquivo)

| Arquivo | Ação |
|---------|------|
| `core/domain/workflow/constants.py` | CREATE: Single Source of Truth das 3 constantes |

---

## 6. Edge Cases & Risks

| # | Risk | Probabilidade | Mitigação |
|---|------|:---:|-----------|
| R1 | ✅ **CONFIRMADO:** `sys.modules["backend.orchestrator"]` em testes do graph | **Alta** | `test_graph_unit.py:548` e `test_graph_integration.py:207` injetam mocks via `sys.modules["backend.orchestrator"]`. Após refactor, `nodes.py` importa de `core.domain.workflow.constants` — os mocks **DEVEM** ser atualizados para `sys.modules["core.domain.workflow.constants"]`. Isso altera 2 arquivos de teste (escopo ajustado). |
| R2 | Circular import se `constants.py` importar de `entities.py` | Baixa | `constants.py` não importa nada do projeto — apenas stdlib `copy` se necessário |
| R3 | `orchestrator.py` tem side effects no module-level que dependem das constantes | Baixa | As constantes são dicts/lists puros, sem side effects. O import order não muda |

> [!WARNING]
> **R1 é o risco principal.** Os testes `test_graph_unit.py` e `test_graph_integration.py` usam `monkeypatch` para substituir `MISSION_PATTERNS`, `DEFAULT_STEPS` e `AGENT_PERSONA_MAP`. Após o refactor, o `plan_node` importará de `core.domain.workflow.constants`, mas o `monkeypatch` precisa apontar para `core.graph.nodes.MISSION_PATTERNS` (onde o nome é bound no namespace do módulo). **Verificar se os patches já apontam para `core.graph.nodes` ou `backend.orchestrator`.**

---

## 7. PD-OVRs Aplicáveis

| PD-OVR | Relevância |
|--------|-----------|
| PD-OVR-004 | Fail-open resiliência — se o import falhar, o sistema não deve travar |
| Demais (001-006) | Nenhuma relação direta |

---

## 8. Fora de Escopo (Explícito)

- ❌ Remover `AGENT_PERSONA_MAP` do `backend/orchestrator.py` (re-export permanece durante Strangler Fig)
- ❌ Mover `MAX_MESSAGE_CHARS` / `MAX_BUBBLE_CHARS` (são constantes de protocolo de interface)
- ❌ Refatorar o `plan_node` em si (SRP de nodes.py — item separado)
- ❌ Remover o Strangler Fig flag `MISSION_ENGINE` (prazo separado)
- ❌ Alterar testes existentes que importam de `backend.orchestrator`
- ❌ Resolver V2 (`entrypoint.py` → telemetry) ou V3 (Service Locator em `telemetry.py`)

---

## 9. Decisões Pendentes

| # | Questão | Recomendação |
|---|---------|-------------|
| DQ-01 | O `__all__` de `constants.py` deve incluir `MISSION_PATTERNS`, `DEFAULT_STEPS`, `AGENT_PERSONA_MAP`? | **Sim** — seguir padrão de todos os módulos `core/` |
| DQ-02 | Re-export em `orchestrator.py` via `from ... import X` ou via atribuição de alias? | **Import direto** — `from core.domain.workflow.constants import AGENT_PERSONA_MAP, DEFAULT_STEPS, MISSION_PATTERNS` |
| DQ-03 | Adicionar `constants.py` ao `__all__` do `core/domain/workflow/__init__.py`? | **Não** — manter `__init__.py` mínimo, consumidores importam direto do módulo |

---

## 10. Próximo Passo

**Fase 3 (Plan Gate):** Converter esta spec em plano determinístico com briefs SDD atômicos. O plano deve conter:
1. Brief T1: Criar `core/domain/workflow/constants.py` com as 3 constantes
2. Brief T2: Atualizar `core/graph/nodes.py` para importar do novo módulo
3. Brief T3: Converter `backend/orchestrator.py` para re-export
4. Brief T4: Validar testes (suíte completa + verificação de monkeypatch paths)

**PARAR E EXIGIR APROVAÇÃO FORMAL HUMANA ANTES DE QUALQUER PLANO.**

---

*Especificação gerada seguindo o Manifesto Sem Retrabalho v3.0.0 — Fase 2 (Spec Gate). Saldo de código: +0 / -0.*

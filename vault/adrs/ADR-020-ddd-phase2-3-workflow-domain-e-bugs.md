---
id: ADR-020
title: "DDD Phase 2-3: Workflow Domain Entities e Correção de Bugs Estruturais"
status: active
date: 2026-10-13
tags: [ddd, workflow, domain, tdd, sdd, bug-fix]
---

# ADR-020: DDD Phase 2-3 — Workflow Domain Entities e Correção de Bugs Estruturais

## Contexto

Após a Phase 1 (ADR-019) estabelecer `core/domain/nexus/entities.py` como fonte de verdade para roles e ferramentas, a auditoria DDD identificou:

1. **IC-3** (Phase 2): `PlaybooksApi` em `dashboard/serve.py` usava parser de frontmatter local e SQL raw, violando o princípio DDD de single source of truth via `core.evidence`.

2. **IC-5** (Phase 2): `backend/orchestrator.py` mantinha `AUTO_TOOLS` como frozenset hardcoded, divergindo de `core.domain.nexus.entities`.

3. **IC-4** (Phase 3): A taxonomia de IDs estava fragmentada: `missionId` (int, WS), `workflow_id` (str, dashboard), `task_id` (str, tracing), `session_id` (str, memory) — quatro conceitos sem coordenação de domínio.

4. **Bug crítico** (Phase 3): `backend/tool_executor.py:93` usava `r.get("last_result", "unknown")` mas `evidence.list_rules()` retorna o campo `state`, não `last_result`. Causava o emoji `❓` sempre no balão de resumo do agente Maia.

## Decisões

### 1. `core/domain/workflow/entities.py` (novo)

Criado para unificar a taxonomia de workflow no domínio Python:

- **`Mission`** (dataclass): `id: int`, `task: str`, `steps: List[Step]`, `status: str`
  - `id` é o `missionId` canônico — int positivo, JS-safe (≤ 2^53-1)
- **`Step`** (dataclass frozen): `agent`, `tool`, `input`, `bubble`, `requires_approval`
  - Valida `agent ∈ ALLOWED_ROLES` e `tool != ""`
  - `requires_approval = tool not in AUTO_TOOLS`
- **`AgentEvent`** (dataclass frozen): serializa para wire format de `event-protocol.js`
- **`validate_mission_envelope()`**: helper para validar envelopes WebSocket `START`/`NEW_TASK`
- **`EVENT_TYPES`**: frozenset dos tipos de eventos válidos

### 2. Taxonomia canônica de IDs

| Conceito | Tipo | Uso |
|---|---|---|
| `missionId` | `int` | Geração de sincronização WS + Nexus reducer |
| `task` | `str` | Texto do prompt do usuário |
| `trace_id` | `str` (UUID hex) | Rastreabilidade distribuída (audit log) |
| `task_label` | `str` | Rótulo legível do trace (extraído de `task_id`) |
| `workflowId` | `str` (slug) | Template de workflow do dashboard (diferente de mission) |

### 3. Correção do bug em `tool_executor.py`

`r.get("last_result", "unknown")` → `r.get("state", "unknown")`

O campo correto retornado por `evidence.list_rules()` é `state` (valores: `"ok"`, `"falha"`, `"parcial"`, `"sem evidência ainda"`).

### 4. SDD criados

- `docs/sdd/SDD-001-playbooks-api.md`
- `docs/sdd/SDD-002-workflow-api.md`
- `docs/sdd/SDD-003-evidence-store.md`

## Consequências

**Positivas:**
- `validate_mission_envelope()` pode ser reutilizado em `ws_server.py` para substituir `_mission_target()` ou complementá-la
- `AgentEvent.to_dict()` é a definição canônica do wire format — sync com `event-protocol.js`
- Bug corrigido: balão do agente mostra `"ok"`, `"falha"`, `"parcial"` em vez de sempre `❓`
- 41 novos testes cobrem invariantes do workflow domain

**Pendentes (Phase 4):**
- `ws_server.py` deve importar `validate_mission_envelope` em vez de duplicar a validação em `_mission_target()`
- `nexus/src/scene/constants3d.js` deve ser sincronizado com `entities.py` (divergência de `label`/`role`/`name` e dimensões de salas)
- Script `scripts/generate_nexus_constants.py` para gerar `nexus/src/generated/nexus-entities.js`

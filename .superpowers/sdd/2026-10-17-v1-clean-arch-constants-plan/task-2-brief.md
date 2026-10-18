# Brief T2 — MODIFY `core/graph/nodes.py` (import source)

## Objetivo
Alterar o lazy import em `plan_node()` para importar de `core.domain.workflow.constants` em vez de `backend.orchestrator`.

## Allowed Files
- `core/graph/nodes.py` — **MODIFY** (linhas 73-78)

## No-Touch Files
- Todos os demais arquivos

## Implementação Exata

Em `core/graph/nodes.py`, substituir:

```python
    # Lazy imports — backend.orchestrator has heavy module-level side effects
    from backend.orchestrator import (  # noqa: WPS433
        AGENT_PERSONA_MAP,
        DEFAULT_STEPS,
        MISSION_PATTERNS,
    )
```

Por:

```python
    # Workflow domain constants — extracted from backend.orchestrator (V1 Clean Arch)
    from core.domain.workflow.constants import (  # noqa: WPS433
        AGENT_PERSONA_MAP,
        DEFAULT_STEPS,
        MISSION_PATTERNS,
    )
```

## Comando de Verificação

```powershell
# INV-N01: core/graph/ NUNCA importa de backend/
Select-String -Path "c:\KIOSK\second-brain-WO-0001\core\graph\nodes.py" -Pattern "from backend"
# Esperado: 0 matches
```

## Critérios de Aceite
- [x] `from backend` não aparece em `core/graph/nodes.py`
- [x] `from core.domain.workflow.constants import` aparece
- [x] Nenhuma outra alteração no arquivo

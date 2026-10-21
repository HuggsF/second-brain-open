# Brief T3 — MODIFY `backend/orchestrator.py` (re-export)

## Objetivo
Converter `backend/orchestrator.py` de **definidor** para **re-exportador** das 3 constantes, mantendo retrocompatibilidade total para todos os consumidores legados.

## Allowed Files
- `backend/orchestrator.py` — **MODIFY** (linhas 39-90)

## No-Touch Files
- Todos os demais arquivos

## Implementação Exata

Em `backend/orchestrator.py`, substituir as linhas 39-90 (definições das constantes) por:

```python
# Sprint 7: Workflow domain constants — canonical source in core/domain/workflow/constants.py
# Re-exported here for backward compatibility during Strangler Fig migration.
from core.domain.workflow.constants import (  # noqa: F401, WPS433
    AGENT_PERSONA_MAP,
    DEFAULT_STEPS,
    MISSION_PATTERNS,
)
```

**PRESERVAR** o comentário na linha 92 (`# Quem decide se uma ferramenta roda...`) e as constantes `MAX_MESSAGE_CHARS` (L96) e `MAX_BUBBLE_CHARS` (L97).

## Comando de Verificação

```powershell
# Retrocompatibilidade: import antigo ainda funciona
C:\Python314\python.exe -c "from backend.orchestrator import AGENT_PERSONA_MAP, DEFAULT_STEPS, MISSION_PATTERNS; print(f'retrocompat OK: {len(AGENT_PERSONA_MAP)} agents')"
```

**Esperado:** `retrocompat OK: 5 agents`

## Critérios de Aceite
- [x] `backend/orchestrator.py` não define mais as constantes inline
- [x] `from backend.orchestrator import AGENT_PERSONA_MAP` continua funcionando
- [x] `MAX_MESSAGE_CHARS` e `MAX_BUBBLE_CHARS` permanecem inalterados
- [x] Nenhuma outra alteração funcional no arquivo

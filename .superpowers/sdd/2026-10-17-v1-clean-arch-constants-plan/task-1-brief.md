# Brief T1 — CREATE `core/domain/workflow/constants.py`

## Objetivo
Criar o novo módulo `core/domain/workflow/constants.py` como Single Source of Truth para as 3 constantes de domínio de workflow: `AGENT_PERSONA_MAP`, `DEFAULT_STEPS` e `MISSION_PATTERNS`.

## Allowed Files
- `core/domain/workflow/constants.py` — **CREATE**

## No-Touch Files
- Todos os demais arquivos

## Implementação Exata

Criar `core/domain/workflow/constants.py` com:

1. **Docstring** proibindo imports de I/O, HTTP ou WebSocket (padrão `entities.py:8`)
2. **`__all__`** com as 3 constantes
3. **`AGENT_PERSONA_MAP`** — dict `str → str` (5 entradas: manager, reviewer, researcher, coder, writer)
4. **`MISSION_PATTERNS`** — list de dicts com `keywords` e `steps` (5 patterns)
5. **`DEFAULT_STEPS`** — list de 1 dict (fallback genérico)

Copiar EXATAMENTE as definições de `backend/orchestrator.py` linhas 41-90 (sem modificar valores).

## Comando de Verificação

```powershell
C:\Python314\python.exe -c "from core.domain.workflow.constants import AGENT_PERSONA_MAP, DEFAULT_STEPS, MISSION_PATTERNS; print(f'OK: {len(AGENT_PERSONA_MAP)} agents, {len(MISSION_PATTERNS)} patterns, {len(DEFAULT_STEPS)} defaults')"
```

**Esperado:** `OK: 5 agents, 5 patterns, 1 defaults`

## Critérios de Aceite
- [x] Módulo existe e é importável
- [x] `__all__` declara as 3 constantes
- [x] Docstring proíbe I/O imports
- [x] Zero imports do projeto (apenas stdlib se necessário)
- [x] Valores idênticos ao `backend/orchestrator.py`

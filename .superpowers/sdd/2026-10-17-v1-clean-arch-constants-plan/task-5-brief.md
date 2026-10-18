# Brief T5 — VALIDATE suíte completa

## Objetivo
Executar a suíte de testes completa do repositório e verificar todos os critérios de aceite e invariantes negativos da spec.

## Allowed Files
- **NENHUM** — brief de validação apenas

## Comandos de Verificação

### 1. Suíte backend completa

```powershell
C:\Python314\python.exe -m pytest tests/ -v --tb=short
```

**Esperado:** 1.212+ passed, 0 failed

### 2. Suíte frontend Nexus

```powershell
node --test --test-isolation=none nexus/tests/adapters.test.mjs
```

**Esperado:** 11 passed, 0 failed

### 3. INV-N01: core/ nunca importa de backend/

```powershell
Get-ChildItem -Path "core" -Filter "*.py" -Recurse | Where-Object { $_.FullName -notlike "*__pycache__*" } | Select-String "from backend"
```

**Esperado:** 0 matches

### 4. INV-N03: Source of Truth é constants.py

```powershell
C:\Python314\python.exe -c "from core.domain.workflow.constants import AGENT_PERSONA_MAP, DEFAULT_STEPS, MISSION_PATTERNS; print('Source OK')"
```

### 5. INV-N05: Retrocompatibilidade do re-export

```powershell
C:\Python314\python.exe -c "from backend.orchestrator import AGENT_PERSONA_MAP; from core.domain.workflow.constants import AGENT_PERSONA_MAP as C; assert AGENT_PERSONA_MAP is C, 'MISMATCH'; print('Identity OK')"
```

**Esperado:** `Identity OK` (mesmo objeto em memória)

### 6. INV-N07: Constantes de protocolo intactas

```powershell
C:\Python314\python.exe -c "from backend.orchestrator import MAX_MESSAGE_CHARS, MAX_BUBBLE_CHARS; print(f'MSG={MAX_MESSAGE_CHARS}, BUBBLE={MAX_BUBBLE_CHARS}')"
```

**Esperado:** `MSG=1000, BUBBLE=240`

## Critérios de Aceite
- [x] Backend: 1.212+ passed, 0 failed
- [x] Nexus: 11 passed, 0 failed
- [x] INV-N01: 0 matches `from backend` em `core/`
- [x] INV-N03: Import direto funciona
- [x] INV-N05: `is` identity confirma mesmo objeto
- [x] INV-N07: `MAX_MESSAGE_CHARS=1000`, `MAX_BUBBLE_CHARS=240`

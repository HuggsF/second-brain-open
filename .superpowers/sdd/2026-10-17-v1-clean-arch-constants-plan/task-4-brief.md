# Brief T4 — UPDATE test mocks (sys.modules injection)

## Objetivo
Atualizar os mocks em `test_graph_unit.py` e `test_graph_integration.py` para injetar via `sys.modules["core.domain.workflow.constants"]` em vez de `sys.modules["backend.orchestrator"]`.

## Allowed Files
- `tests/test_graph_unit.py` — **MODIFY** (linhas 539-548)
- `tests/test_graph_integration.py` — **MODIFY** (linhas 37, 202-207)

## No-Touch Files
- Todos os demais arquivos de teste

## Implementação Exata

### `test_graph_unit.py`

Substituir linhas 539-548:

```python
        # plan_node does lazy imports from backend.orchestrator and
        # core.integration inside its body, so we must mock the source
        # modules via sys.modules + patch on the real module path.
        mock_orchestrator = MagicMock(
            MISSION_PATTERNS=mock_patterns,
            DEFAULT_STEPS=mock_defaults,
            AGENT_PERSONA_MAP=mock_agent_map,
        )
        with (
            patch.dict("sys.modules", {"backend.orchestrator": mock_orchestrator}),
            patch("core.integration.get_persona_contract", return_value=None),
        ):
```

Por:

```python
        # plan_node does lazy imports from core.domain.workflow.constants and
        # core.integration inside its body, so we must mock the source
        # modules via sys.modules + patch on the real module path.
        mock_constants = MagicMock(
            MISSION_PATTERNS=mock_patterns,
            DEFAULT_STEPS=mock_defaults,
            AGENT_PERSONA_MAP=mock_agent_map,
        )
        with (
            patch.dict("sys.modules", {"core.domain.workflow.constants": mock_constants}),
            patch("core.integration.get_persona_contract", return_value=None),
        ):
```

### `test_graph_integration.py`

1. Substituir comentário na linha 37:

```python
# -- Mock for backend.orchestrator module (lazy import in plan_node) --
```

Por:

```python
# -- Mock for core.domain.workflow.constants module (lazy import in plan_node) --
```

2. Substituir linhas 202-207:

```python
    # backend.orchestrator: plan_node does `from backend.orchestrator import ...`
    orch = orchestrator_module if orchestrator_module is not None else _mock_orchestrator

    # -- Collect modules to inject --
    injected = {
        "backend.orchestrator": orch,
```

Por:

```python
    # core.domain.workflow.constants: plan_node does `from core.domain.workflow.constants import ...`
    constants_mod = orchestrator_module if orchestrator_module is not None else _mock_orchestrator

    # -- Collect modules to inject --
    injected = {
        "core.domain.workflow.constants": constants_mod,
```

## Comando de Verificação

```powershell
# Testes do graph engine
C:\Python314\python.exe -m pytest tests/test_graph_unit.py tests/test_graph_integration.py -v --tb=short
```

**Esperado:** Todos os testes passam (138 graph tests + subtests)

## Critérios de Aceite
- [x] `"backend.orchestrator"` não aparece como chave de `sys.modules` nos testes graph
- [x] `"core.domain.workflow.constants"` é a nova chave
- [x] Todos os testes graph passam
- [x] Semântica dos mocks inalterada (mesmas constantes mock injetadas)

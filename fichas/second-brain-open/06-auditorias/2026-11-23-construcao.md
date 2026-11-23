---
etapa: construcao
data: 2026-11-23
veredito: ambar
criterio: "A suíte de testes passa."
evidencia: fichas/second-brain-open/06-auditorias/evidencias/2026-11-23-pytest.txt
pendencia: "92 testes assíncronos não rodam: pytest.ini pede asyncio_mode, mas requirements.txt não instala pytest-asyncio. Declarar a dependência e conferir se os 92 passam."
prazo: 2026-12-31
dono: mantenedor
---
# Auditoria de construção, 2026-11-23

## Critério

A suíte de testes passa.

## O que foi feito

`python -m pytest -q` na branch `feat/ficha-de-projeto`, com Python 3.14.3 e só as dependências de
`requirements.txt`. A saída inteira está na evidência; o caminho da pasta do repositório foi trocado por
`.` e nada mais foi alterado.

## Resultado

Âmbar: 944 testes passam e 92 falham.

As 92 falhas têm a mesma mensagem, "async def functions are not natively supported". O `pytest.ini` define
`asyncio_mode = strict`, mas o `requirements.txt` não lista o `pytest-asyncio`, então os testes
assíncronos nem chegam a rodar. Eles estão em seis arquivos: `test_graph_unit.py`,
`test_graph_nexus_adapter.py`, `test_graph_integration.py`, `test_graph_entrypoint.py`,
`test_graph_ws_smoke.py` e `test_broker_timeout.py`.

As mesmas 92 falhas apareceram na execução feita antes de qualquer mudança desta branch.

## Pendência

Declarar `pytest-asyncio` em `requirements.txt`, rodar a suíte de novo e registrar uma nova auditoria. Só
então se sabe se o grafo de missão e o servidor WebSocket funcionam como a ficha descreve. Até lá, a ficha
não pode ser verde.

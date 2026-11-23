---
id: ADR-002
status: aceito
data: 2026-11-23
---
# Portões determinísticos antes e depois de cada missão

## Contexto

A saída de um modelo de linguagem não é confiável por si. É preciso barrar vazamento de dado,
resposta sem fonte, plano com ciclo, violação de regra e repetição de uma ação que altera estado.
Código que sustenta: `core/gates/__init__.py` (`CompoundGatePipeline`) e um arquivo por portão em
`core/gates/`.

## Opções consideradas

1. **Portões determinísticos em código, com semáforo.** Mesmo resultado para a mesma entrada; testável.
2. **Pedir a um segundo modelo que revise.** Flexível, mas não determinístico e com custo por chamada.
3. **Revisão humana de toda missão.** Segura, mas não escala nem para uma pessoa.

## Decisão

Opção 1. Cada portão avalia o que lhe cabe e devolve verde, amarelo ou vermelho; o pior resultado é o
semáforo da missão. A revisão humana fica para o que a política escala.

## Consequências

- Um portão só pega o que foi previsto em código.
- Cada portão novo precisa de teste próprio (`tests/test_gates.py`, `tests/test_gate_isolation.py`).
- O portão roda conforme o conteúdo da missão: missão sem citação não passa pelo de fundamentação.

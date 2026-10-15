---
id: ADR-023
title: Luzes de Teste e Domínio de Observação
status: accepted
date: 2026-10-14
domain: platform
evidence: implementado
---

# ADR-023 — Luzes de Teste e Domínio de Observação

## Contexto

O JEV (frontend React 19) precisa de um mecanismo visual para representar o status das regras de negócio e testes do Hub Logístico. As "luzes de teste" são indicadores coloridos (verde/amarelo/vermelho) que refletem o nível de cobertura e conformidade de cada regra.

## Decisão

Adotar o conceito de **luzes de teste** como primitiva de observabilidade:

- **Verde**: regra coberta por testes automatizados E em conformidade no último deploy
- **Amarelo**: regra com testes parciais ou sem execução recente
- **Vermelho**: regra sem cobertura ou com falha documentada

O **domínio de observação** é definido pelo recorte funcional (ex: emissão de etiquetas, processamento de pedidos) e agrupa luzes relacionadas.

## Consequências

- O JEV exibe um painel hierárquico: domínio → regras → luzes
- A Árvore de Evidências fornece os dados brutos que alimentam as luzes
- O Second Brain Dashboard integra o JEV via iframe na página dedicada
- Regras sem cobertura ficam visíveis, incentivando a escrita de testes

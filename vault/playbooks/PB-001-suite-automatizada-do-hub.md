---
id: PB-001
title: Suíte automatizada do Hub (npm test)
status: active
validates: [RULE-001, RULE-002]
environment: local
targets: [Hub Logístico]
---

# PB-001: Suíte automatizada do Hub (npm test)

## Cenário

- **Dado** o repositório do Hub Logístico no estado a verificar.
- **Quando** `npm test` é executado (localmente ou no CI com Node 18 e 20).
- **Então** todos os cenários passam, incluindo as proteções de NF e de homologação.

## Resultado esperado

Suíte inteira aprovada, sem cenários ignorados. Reprovação em qualquer cenário de NF ou de homologação invalida RULE-001 ou RULE-002 até a correção.

## Registro

O Second Brain não executa a suíte: quem a roda registra o resultado com a ferramenta MCP `record_test_execution`. A única execução existente foi importada da nota [[protecoes-processamento-emissao-hub]] (linha 47), com data aproximada.

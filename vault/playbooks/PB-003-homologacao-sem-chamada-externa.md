---
id: PB-003
title: Homologação não faz chamada externa
status: active
validates: [RULE-002]
environment: hml
targets: [Hub Logístico, ERP, J&T, WMS]
---

# PB-003: Homologação não faz chamada externa

## Cenário

- **Dado** uma instância do Hub com `HUB_ENV=hml` e jobs pendentes.
- **Quando** o motor processa a fila e, separadamente, `generateLabel` é chamado diretamente.
- **Então** nenhuma chamada a ERP, J&T ou WMS ocorre, os jobs continuam pendentes e a chamada direta é rejeitada.

## Resultado esperado

Zero chamadas externas observadas e nenhum job saindo de pendente. Ligar uma loja ou enviar manualmente não altera o resultado.

## Registro

Ainda sem execuções registradas. Quem executar o cenário registra o resultado com `record_test_execution`.

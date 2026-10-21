---
type: playbook
id: PB-018
title: Cancelamento durante a emissão vai para revisão
status: active
kind: test
validates: [RULE-008]
environment: hml
targets: [hub-logistico/engine.js, hub-logistico/queueMonitor.js, Bling (webhook de pedido cancelado)]
ttl_hours: 168
---

## Cenário

- **Dado** um pedido com etiqueta J&T já obtida ou reaproveitada pelo motor (linha `success` ou `failed` com rastreio).
- **Quando** chega um webhook de cancelamento do Bling para o mesmo pedido durante a emissão, ou depois dela.
- **Então** a linha vai para `failed` com `REVIEW_REQUIRED`, o código de rastreio fica intacto, nenhuma chamada de cancelamento é feita na J&T e nenhuma gravação final sobrescreve o cancelamento.

## Resultado esperado

Uma linha `failed` com `REVIEW_REQUIRED` e o rastreio preservado; zero chamadas de cancelamento à J&T; nenhum novo `addOrder`. Código `cancelado` em qualquer linha do mesmo pedido bloqueia reaproveitamento.

## Procedimento

1. Preparar um pedido de teste em homologação com etiqueta mock, com `HUB_ENV=hml`.
2. Disparar o cancelamento durante a chamada mock de `addOrder`, e depois outro após a emissão.
3. Conferir o estado de `orders_queue` e de `jt_emissions`.
4. Confirmar que o mock da J&T não recebeu chamada de cancelamento.

## Registro

Ainda sem execuções registradas. Registrar com `record_test_execution` ou `cli.py evidence`, sem dados do pedido.

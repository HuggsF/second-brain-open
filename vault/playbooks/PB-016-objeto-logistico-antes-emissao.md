---
type: playbook
id: PB-016
title: Objeto logístico deve existir antes de emissão
status: active
kind: test
validates: [RULE-005]
environment: production
targets: [hub-logistico/logisticsPolicy.js, hub-logistico/engine.js]
ttl_hours: 168
---

## Objetivo

Verificar que a validação do objeto logístico é executada antes de qualquer emissão de etiqueta.

## Procedimento de Teste

### Cenário 1: Zero volumes → LOGISTICS_OBJECT_MISSING

1. Submeter um pedido com zero volumes ou sem ID de objeto logístico.
2. Verificar que o pedido é marcado como `REVIEW_REQUIRED` com motivo `LOGISTICS_OBJECT_MISSING`.
3. Confirmar que nenhum intent J&T é criado.

### Cenário 2: Múltiplos volumes → MULTIPLE_VOLUMES_UNDEFINED

1. Submeter um pedido com múltiplos volumes sem definição clara de divisão.
2. Verificar que o pedido é marcado como `REVIEW_REQUIRED` com motivo `MULTIPLE_VOLUMES_UNDEFINED`.
3. Confirmar que nenhum intent J&T é criado.

### Cenário 3: Objeto logístico válido → prosseguimento

1. Submeter um pedido com objeto logístico existente e válido (1 volume, ID presente).
2. Verificar que o sistema prossegue normalmente com a emissão.

## Referência

- Suite de testes: `tests/logistics_safety.test.js`

## Critério de Aceite

- Pedidos sem objeto logístico válido não devem gerar intent J&T.
- Pedidos com múltiplos volumes indefinidos devem ser retidos para revisão.
- Pedidos com objeto logístico válido devem prosseguir normalmente.

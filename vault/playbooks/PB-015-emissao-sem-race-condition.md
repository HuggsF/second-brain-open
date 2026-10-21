---
type: playbook
id: PB-015
title: Emissão protegida contra concorrência
status: active
kind: test
validates: [RULE-004]
environment: production
targets: [hub-logistico/engine.js]
ttl_hours: 168
---

## Objetivo

Verificar que a reserva atômica previne processamento duplo (double-processing) de pedidos.

## Procedimento de Teste

### Cenário 1: Chamadas concorrentes ao processQueue

1. Disparar duas chamadas simultâneas ao `processQueue` para a mesma conexão.
2. Verificar que apenas **uma** das chamadas reserva e processa o pedido.
3. A segunda chamada deve ser ignorada ou retornar sem processar.

### Cenário 2: Reserva atômica SQLite

1. Simular dois workers tentando reservar o mesmo pedido simultaneamente.
2. Verificar que o `UPDATE ... RETURNING` garante que apenas um worker efetue a reserva.
3. O segundo worker não deve obter nenhuma linha no `RETURNING`.

### Cenário 3: Sem transação aberta durante HTTP

1. Monitorar que nenhuma transação SQLite permanece aberta durante chamadas HTTP externas.
2. Confirmar que locks não são mantidos durante I/O de rede.

## Referência

- Suite de testes: `tests/suite_duplicidade.test.js`

## Critério de Aceite

- Nenhum pedido deve ser processado em duplicidade sob concorrência.
- Transações SQLite devem ser fechadas antes de chamadas HTTP.

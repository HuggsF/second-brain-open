---
type: playbook
id: PB-014
title: Conferência NF-e antes de despacho
status: active
kind: test
validates: [RULE-003]
environment: production
targets: [hub-logistico/invoiceEvents.js, hub-logistico/invoicePolicy.js]
ttl_hours: 168
---

## Objetivo

Verificar que as checagens de validação da NF-e são executadas antes de qualquer despacho automático.

## Procedimento de Teste

### Cenário 1: NF-e incompleta → bloqueio

1. Submeter um pedido com NF-e incompleta (chave de acesso ausente, número zero, série vazia, ou situação diferente de 5/6).
2. Verificar que o sistema **bloqueia** a emissão e não cria intent J&T.
3. Confirmar que o pedido é marcado com erro de validação NF-e.

### Cenário 2: NF-e válida → prosseguimento

1. Submeter um pedido com NF-e completa e válida (situação 5, número positivo, série válida, chave de 44 dígitos, data válida).
2. Verificar que o sistema **prossegue** com a criação do intent J&T.
3. Confirmar que o pedido avança para o próximo estágio do fluxo.

### Cenário 3: Falha na consulta NF-e → bloqueio

1. Simular falha na consulta da NF-e (timeout ou erro de API).
2. Verificar que o sistema **bloqueia** a emissão por precaução.

## Critério de Aceite

- Nenhum pedido com NF-e inválida ou incompleta deve gerar intent J&T.
- Pedidos com NF-e válida devem prosseguir normalmente.

---
type: playbook
id: PB-019
title: Gatilho por NF-e e vínculo pedido-NF em homologação
status: active
kind: test
validates: [RULE-009]
environment: hml
targets: [hub-logistico/invoiceEvents.js, hub-logistico/shippingPolicy.js, hub-logistico/queueAdmission.js]
ttl_hours: 168
---

## Cenário

- **Dado** eventos sintéticos `invoice.created` e `invoice.updated` com HMAC válido, cobrindo NF elegível, NF de situação diferente de 5 ou 6, NF sem chave válida, loja fora do escopo, pedido sem `notaFiscal.id` e pedido com dois candidatos.
- **Quando** o webhook é processado em homologação.
- **Então** só a NF elegível de loja no escopo entra em `orders_queue`; os demais ficam bloqueados ou ignorados com motivo, sem chamada ao Bling ou à J&T.

## Resultado esperado

- NF gravada em `invoice_events` antes do 200.
- Evento repetido com o mesmo `eventId` e NF não é reprocessado.
- Pedido sem vínculo confirmado ou com vínculo ambíguo: bloqueado.
- Loja fora do escopo: `ignorado_loja`.
- Pedido de outra transportadora: `ignorado_transporte`, que não conta como falha.
- NF de outro pedido que não o `invoice_id` disparador: `REVIEW_REQUIRED`.

## Procedimento

1. Usar `HUB_ENV=hml` com todas as lojas `gerar_automatico=0`, exceto a de teste.
2. Gerar os eventos sintéticos e enviar pelo webhook de homologação.
3. Conferir `invoice_events`, `orders_queue` e o `error_log` de cada caso.
4. Confirmar que o mock do Bling e o da J&T não receberam chamadas de emissão.

## Registro

Ainda sem execuções registradas. Registrar com `record_test_execution` ou `cli.py evidence`, sem chave de acesso nem dados de destinatário.

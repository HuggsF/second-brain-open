---
type: playbook
id: PB-017
title: Reconciliação de emissão uncertain (J&T)
status: active
kind: runbook
validates: [RULE-006, RULE-007]
environment: production
targets: [hub-logistico/jt_emissions, hub-logistico/orders_queue, J&T (consulta de pedido e PDF), Bling (GET pedido e NF)]
---

# PB-017: Reconciliação de emissão uncertain (J&T)

Runbook manual, somente leitura até a etapa de decisão. Usar quando houver linha `uncertain` em `jt_emissions` ou job `failed` com `REVIEW_REQUIRED` após timeout ou rejeição de `addOrder`. Skill de apoio: `hub-reconciliacao-emissao-jt`.

## Pré-condição

1. Consumidor da fila parado (worker pausado). Não reativar `processing` abandonado enquanto houver consumidor ativo.
2. Nenhum cancelamento ou reenvio manual feito sobre o pedido.

## Passos

1. **Estado local (SQLite, leitura).** Para o `erp_id`, anotar `txlogistic_id`, `state`, `tracking_number` de `jt_emissions` e todas as linhas de `orders_queue`, inclusive `failed` e `cancelado`.
2. **Estado no Bling.** `GET` do pedido e da NF: confirmar se há `transporte.volumes[0].codigoRastreamento` e qual rastreio o Bling registra.
3. **Estado na J&T.** Consultar o pedido pelo `txlogistic_id` e conferir o PDF da etiqueta, se existir. Registrar se há billCode e se ele coincide com o rastreio local.
4. **Decisão.**
   - Se a J&T confirma emissão com billCode: reconciliar `jt_emissions` para `confirmed` com o rastreio e corrigir `orders_queue` para `success` com o rastreio. Não criar nova intenção.
   - Se a J&T não tem registro e há evidência escrita do fornecedor de que não houve emissão: a liberação de nova intenção exige confirmação operacional registrada. Só então a linha pode sair de `uncertain`.
   - Se a evidência é inconclusiva: manter `uncertain` e escalar. Não apagar a linha para liberar fila.
5. **Registro.** Anotar a decisão no ticket sem incluir chave completa, endereço ou dados do destinatário.

## Resultado esperado

Nenhuma etiqueta duplicada, nenhuma linha `uncertain` apagada, cada pedido com um rastreio único ou com revisão pendente documentada.

## Critério de falha

Qualquer nova `addOrder` para um `erp_id` com intenção `uncertain` sem evidência do fornecedor, ou qualquer linha `uncertain` removida para liberar fila.

## Registro

Ainda sem execuções registradas. Cada execução registrada com `record_test_execution` ou `cli.py evidence`, sem dados do pedido.

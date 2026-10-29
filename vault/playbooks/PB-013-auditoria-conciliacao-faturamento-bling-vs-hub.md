---
id: PB-013
title: "Auditoria Analítica de Faturamento e SLA Logístico (Bling vs J&T)"
status: active
validates: [RULE-001, RULE-002]
environment: production
kind: runbook
targets: [Hub Logístico, Bling API v3, J&T Express]
params:
  - name: start_date
    label: "Data Inicial (AAAA-MM-DD)"
    type: string
    default: "2026-10-01"
  - name: end_date
    label: "Data Final (AAAA-MM-DD)"
    type: string
    default: "2026-10-13"
  - name: store_id
    label: "Loja / Canal Bling"
    type: select
    options: ["ALL", "206085936", "206084387", "206133846", "206288765"]
    default: "ALL"
  - name: min_fulfillment_target
    label: "Meta de SLA Fulfillment (%)"
    type: string
    default: "95.0"
---

# PB-013: Auditoria Analítica de Faturamento e SLA Logístico (Bling vs J&T)

## 1. Propósito e Métricas Auditadas

Valida o alinhamento financeiro e operacional entre os pedidos faturados no ERP Bling v3 e as etiquetas expedidas no Hub Logístico, garantindo que:
1. Todo pedido faturado em `{{ start_date }}` a `{{ end_date }}` tenha entrado na fila `orders_queue`.
2. A taxa de fulfillment atinja a meta mínima de `{{ min_fulfillment_target }}%`.
3. Nenhuma etiqueta duplicada ou cobrança indevida de frete tenha ocorrido.

---

## 2. Consulta de Faturamento no Bling v3

Execute a extração de métricas de vendas através do endpoint do Hub Analytics:

```bash
# Consultar métricas de vendas e GMV agregadas
curl -s "http://127.0.0.1:8847/api/analytics/sales?startDate={{ start_date }}&endDate={{ end_date }}{% if store_id != 'ALL' %}&storeId={{ store_id }}{% endif %}" \
  | jq '.data.summary'
```

---

## 3. Auditoria de SLA de Fulfillment na Fila SQLite

Examine a taxa de conversão entre admissão de pedido e geração de etiqueta J&T:

```bash
# Taxa de conversão da fila do Hub
sqlite3 hub.db "SELECT \
  COUNT(*) as total_admitidos, \
  SUM(CASE WHEN status = 'success' OR tracking_number IS NOT NULL THEN 1 ELSE 0 END) as etiquetas_emitidas, \
  ROUND(SUM(CASE WHEN status = 'success' OR tracking_number IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as taxa_fulfillment, \
  SUM(CASE WHEN status LIKE 'failed%' THEN 1 ELSE 0 END) as falhas_ativas \
FROM orders_queue \
WHERE created_at >= '{{ start_date }} 00:00:00' AND created_at <= '{{ end_date }} 23:59:59';"
```

---

## 4. Auditoria de Integridade Financeira (Risco de Duplicidade J&T)

Verifique se algum `erp_id` possui mais de uma ocorrência confirmada em `jt_emissions`:

```bash
# Detectar duplicidade de emissões
sqlite3 hub.db "SELECT erp_id, COUNT(*) as qtd, GROUP_CONCAT(tracking_number) as trackings \
FROM jt_emissions \
WHERE created_at >= '{{ start_date }} 00:00:00' \
GROUP BY erp_id HAVING qtd > 1;"
```

> **Critério de Sucesso:** Zero linhas retornadas. Qualquer linha retornada representa um risco de cobrança duplicada na fatura da J&T Express.

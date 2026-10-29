---
id: PB-011
title: "Conciliação e Reprocessamento Seguro de Pedidos na Fila do Hub"
status: active
validates: [RULE-001, RULE-002]
environment: hml
kind: runbook
targets: [Hub Logístico, J&T Express API, Bling API v3]
params:
  - name: erp_id
    label: "ID do Pedido (Bling)"
    type: string
    default: "27092088359"
    description: "ID do pedido de venda no Bling a conciliar"
    required: true
  - name: environment
    label: "Ambiente Alvo"
    type: select
    options: [local, hml, production]
    default: "hml"
  - name: new_status
    label: "Novo Status da Fila"
    type: select
    options: [pending, cancelled, failed_definitivo]
    default: "pending"
  - name: reset_retries
    label: "Zerar Contador de Retries"
    type: boolean
    default: true
---

# PB-011: Conciliação e Reprocessamento Seguro de Pedidos na Fila do Hub

## 1. Propósito e Cenário Operacional

Este playbook define o procedimento seguro para destravamento, conferência e reprocessamento de pedidos que falharam ou ficaram retidos na fila `orders_queue` do Hub Logístico, assegurando que nenhuma etiqueta duplicada seja emitida na J&T Express.

- **Dado** um pedido com falha ou inconsistência no processamento.
- **Quando** o analista ou operador executa os passos abaixo para o pedido `{{ erp_id }}` no ambiente `{{ environment }}`.
- **Então** o registro é auditado contra a tabela `jt_emissions`, o rastreio pré-existente é preservado e a fila é reativada de forma atômica.

---

## 2. Inspeção Inicial do Registro no Banco de Dados

Conecte ao servidor do Hub (`{% if environment == 'production' %}191.233.18.195{% else %}127.0.0.1{% endif %}`) e execute a consulta de diagnóstico:

```bash
# Inspecionar estado atual na fila orders_queue
sqlite3 hub.db "SELECT id, erp_id, status, retries, tracking_number, error_log, created_at FROM orders_queue WHERE erp_id = '{{ erp_id }}';"
```

Verifique se já houve emissão prévia registrada na tabela anti-duplicidade `jt_emissions`:

```bash
# Checar histórico de emissão na J&T
sqlite3 hub.db "SELECT erp_id, txlogistic_id, state, tracking_number, created_at FROM jt_emissions WHERE erp_id = '{{ erp_id }}';"
```

---

## 3. Verificação no ERP Bling v3

Consulte os dados atuais do pedido e objetos logísticos via cURL utilizando o conector Bling:

```bash
# Inspecionar se o Bling já possui rastreio gravado em transporte.volumes
curl -s -X GET "https://api.bling.com.br/Api/v3/pedidos/vendas/{{ erp_id }}" \
  -H "Authorization: Bearer {{ auth_token | default: '$BLING_ACCESS_TOKEN' }}" \
  -H "Accept: application/json" | jq '.data.transporte.volumes'
```

> **🛡️ Regra Anti-Duplicidade:** Se `codigoRastreamento` já estiver preenchido no Bling, **NÃO reemita etiqueta**! O conector reaproveitará o código automaticamente.

---

## 4. Reprocessamento Seguro com Atualização Atômica

Execute a atualização do status na fila aplicando os parâmetros selecionados:

```bash
# Atualização segura do status para reprocessamento
sqlite3 hub.db "UPDATE orders_queue SET \
  status = '{{ new_status }}', \
  {% if reset_retries %}retries = 0, error_log = NULL,{% endif %} \
  next_attempt_at = datetime('now') \
WHERE erp_id = '{{ erp_id }}';"
```

Force um ciclo de processamento imediato pelo motor:

```bash
# Disparar ciclo imediato do engine
curl -s -X POST "http://{% if environment == 'production' %}127.0.0.1:3000{% else %}127.0.0.1:8847{% endif %}/api/jobs/run" \
  -H "Content-Type: application/json" \
  -d '{"erp_id": "{{ erp_id }}"}'
```

---

## 5. Validação Pós-Execução

Confirme se o status avançou para `success`:

```bash
sqlite3 hub.db "SELECT id, erp_id, status, tracking_number FROM orders_queue WHERE erp_id = '{{ erp_id }}';"
```

Resultado esperado: `status = 'success'` e `tracking_number` devidamente preenchido.

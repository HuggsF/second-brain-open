---
id: PB-012
title: "Diagnóstico e Rotação a Quente de Tokens OAuth Bling v3"
status: active
validates: [RULE-001]
environment: production
kind: runbook
targets: [Hub Logístico, Bling API v3]
params:
  - name: environment
    label: "Ambiente Alvo"
    type: select
    options: [production, hml, local]
    default: "production"
  - name: client_id
    label: "Bling Client ID"
    type: string
    default: "baed4213c19c9bfe9804bfc2d0fa6146635bced5"
    description: "Client ID da aplicação OAuth cadastrada no Bling"
  - name: min_remaining_minutes
    label: "Minutos Mínimos Restantes"
    type: string
    default: "15"
---

# PB-012: Diagnóstico e Rotação a Quente de Tokens OAuth Bling v3

## 1. Propósito e Diagnóstico

Evita paralisações de pedidos causadas por expiração do access token do Bling v3 (validade de 6 horas) ou descompasso do refresh token no banco SQLite.

- **Ambiente:** `{{ environment }}`
- **Client ID Monitorado:** `{{ client_id }}`

---

## 2. Inspeção do Semáforo do Token Atual

Execute a verificação da data de expiração gravada no conector ERP:

```bash
# Consultar timestamp de expiração e tempo restante
sqlite3 hub.db "SELECT \
  json_extract(config, '$.clientId') as client_id, \
  datetime(json_extract(config, '$.expiresAt')/1000, 'unixepoch', 'localtime') as expira_em, \
  ROUND((json_extract(config, '$.expiresAt') - (strftime('%s','now') * 1000)) / 60000.0, 1) as minutos_restantes, \
  CASE WHEN json_extract(config, '$.expiresAt') > (strftime('%s','now') * 1000) THEN 'VÁLIDO' ELSE 'EXPIRADO' END as status \
FROM connectors WHERE type = 'erp';"
```

> **Critério de Alerta:** Se `minutos_restantes < {{ min_remaining_minutes }}`, proceda imediatamente com a renovação a quente.

---

## 3. Renovação de Emergência via cURL

Dispare a renovação usando o `refresh_token` atual:

```bash
# Obter refresh_token do banco
REFRESH_TOKEN=$(sqlite3 hub.db "SELECT json_extract(config, '$.refreshToken') FROM connectors WHERE type = 'erp';")
CLIENT_SECRET=$(sqlite3 hub.db "SELECT json_extract(config, '$.clientSecret') FROM connectors WHERE type = 'erp';")
BASIC_AUTH=$(echo -n "{{ client_id }}:$CLIENT_SECRET" | base64)

# Chamar endpoint oficial OAuth Bling v3
RESPONSE=$(curl -s -X POST "https://www.bling.com.br/Api/v3/oauth/token" \
  -H "Authorization: Basic $BASIC_AUTH" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=$REFRESH_TOKEN")

echo $RESPONSE | jq .
```

---

## 4. Injeção a Quente no `hub.db`

Atualize as credenciais no conector sem necessidade de reiniciar os processos do PM2:

```bash
NEW_ACCESS=$(echo $RESPONSE | jq -r .access_token)
NEW_REFRESH=$(echo $RESPONSE | jq -r .refresh_token)
EXPIRES_IN=$(echo $RESPONSE | jq -r .expires_in)
NEW_EXPIRES_AT=$(($(date +%s%N)/1000000 + ($EXPIRES_IN * 1000)))

sqlite3 hub.db "UPDATE connectors SET \
  config = json_set(config, \
    '$.accessToken', '$NEW_ACCESS', \
    '$.refreshToken', '$NEW_REFRESH', \
    '$.expiresAt', $NEW_EXPIRES_AT \
  ) \
WHERE type = 'erp';"
```

---

## 5. Teste de Conectividade Pós-Atualização

Envie uma requisição leve com limite 1 para certificar autorização HTTP 200:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X GET "https://api.bling.com.br/Api/v3/pedidos/vendas?limite=1" \
  -H "Authorization: Bearer $NEW_ACCESS"
```

Resultado esperado: `200`.

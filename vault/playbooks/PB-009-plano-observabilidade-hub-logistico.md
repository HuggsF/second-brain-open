---
title: "PB-009 — Plano de Observabilidade do Hub Logístico"
date: 2026-10-13
type: playbook
origin: "Post-mortem incidente OAuth 13/10/2026"
tags: [playbook, observabilidade, monitoramento, hub-logistico, alertas]
---

# PB-009: Plano de Observabilidade — Hub Logístico

## Motivação

O incidente de 08-13/10/2026 demorou **~4 dias** para ser detectado porque o Hub não tinha alertas automáticos. 140 pedidos falharam silenciosamente enquanto a equipe não percebia. Este plano define as métricas, alertas e dashboards necessários.

---

## 1. Métricas Críticas (L1 — Alertar imediatamente)

### M1: Taxa de Falha na Fila
```sql
-- Calcular a cada 15 minutos
SELECT 
  CAST(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS FLOAT) / 
  CAST(COUNT(*) AS FLOAT) * 100 AS taxa_falha_pct
FROM orders_queue 
WHERE created_at > datetime('now', '-1 hour');
```

| Condição | Alerta |
|---|---|
| taxa_falha > 20% (última hora) | 🔴 P1 — Possível falha sistêmica |
| taxa_falha > 5% (últimas 6h) | 🟡 P2 — Investigar |
| Pedidos `failed` > 10 consecutivos | 🔴 P1 — Motor com problema |

### M2: Token OAuth Expirado
```sql
-- Verificar a cada 30 minutos
SELECT 
  json_extract(config, '$.expiresAt') AS expires_at,
  CASE 
    WHEN json_extract(config, '$.expiresAt') < (strftime('%s','now') * 1000) THEN 'EXPIRADO'
    WHEN json_extract(config, '$.expiresAt') < (strftime('%s','now') * 1000 + 3600000) THEN 'EXPIRA_1H'
    ELSE 'OK'
  END AS estado
FROM connectors WHERE type='erp';
```

| Condição | Alerta |
|---|---|
| Token expirado | 🔴 P1 — Motor parado |
| Token expira em < 1h | 🟡 P2 — Verificar renovação |

### M3: Erros 404 no Bling
```sql
-- Últimas 24h
SELECT COUNT(*) FROM orders_queue 
WHERE status='failed' 
AND error_log LIKE '%404%' 
AND created_at > datetime('now', '-24 hours');
```

| Condição | Alerta |
|---|---|
| > 3 erros 404 em 1h | 🔴 P1 — App OAuth possivelmente trocado |

---

## 2. Métricas Operacionais (L2 — Dashboard diário)

### M4: Distribuição da Fila
```sql
SELECT status, COUNT(*) as qty, 
  ROUND(CAST(COUNT(*) AS FLOAT) / (SELECT COUNT(*) FROM orders_queue) * 100, 1) as pct
FROM orders_queue GROUP BY status ORDER BY qty DESC;
```

### M5: Throughput (pedidos processados/hora)
```sql
SELECT 
  strftime('%Y-%m-%d %H:00', created_at) as hora,
  COUNT(*) as processados
FROM orders_queue 
WHERE status='success' 
GROUP BY hora 
ORDER BY hora DESC LIMIT 24;
```

### M6: Tempo Médio de Processamento
```sql
-- Diferença entre created_at e quando virou success (aproximação)
SELECT 
  AVG(CAST((julianday(next_attempt_at) - julianday(created_at)) * 24 * 60 AS INT)) as avg_min
FROM orders_queue WHERE status='success';
```

### M7: Lojas com `ignorado_loja`
```sql
SELECT 
  json_extract(universal_payload, '$.loja.id') as loja_id,
  COUNT(*) as qty
FROM orders_queue 
WHERE status='ignorado_loja' 
AND created_at > datetime('now', '-7 days')
GROUP BY loja_id ORDER BY qty DESC;
```

---

## 3. Health Checks (a cada 5 minutos)

### HC1: Motor PM2 rodando
```bash
pm2 jlist | jq '.[0] | {name: .name, status: .pm2_env.status, uptime: .pm2_env.pm_uptime, restarts: .pm2_env.restart_time}'
```

| Condição | Alerta |
|---|---|
| status != "online" | 🔴 P1 |
| restarts > 5 (última hora) | 🟡 P2 — Crash loop |

### HC2: API Bling respondendo
```bash
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
  "https://api.bling.com.br/Api/v3/situacoes/modulos/98310"
```

### HC3: API J&T respondendo
```bash
# Verificar via getOrders com billCode fictício
node -e "// chamar getOrders com serialNumber vazio"
```

### HC4: Disco / Banco
```bash
du -sh /home/ti-kiosk/hub/hub.db
sqlite3 /home/ti-kiosk/hub/hub.db "PRAGMA integrity_check;"
```

---

## 4. Alertas Propostos

### Implementação Sugerida: Cron no Servidor

```bash
# /home/ti-kiosk/hub/health_check.sh — rodar a cada 15 min via crontab
#!/bin/bash
cd /home/ti-kiosk/hub

# 1. Verificar PM2
PM2_STATUS=$(sudo pm2 jlist | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['pm2_env']['status'])" 2>/dev/null)
if [ "$PM2_STATUS" != "online" ]; then
  echo "🔴 ALERTA: hub-logistico NÃO está online (status: $PM2_STATUS)"
  # TODO: enviar notificação (Slack, email, etc.)
fi

# 2. Verificar taxa de falha
FAILED_RATE=$(sqlite3 hub.db "SELECT COALESCE(CAST(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS FLOAT) / NULLIF(COUNT(*),0) * 100, 0) FROM orders_queue WHERE created_at > datetime('now', '-1 hour');")
if (( $(echo "$FAILED_RATE > 20" | bc -l) )); then
  echo "🔴 ALERTA: Taxa de falha ${FAILED_RATE}% na última hora"
fi

# 3. Verificar pending acumulados
PENDING=$(sqlite3 hub.db "SELECT COUNT(*) FROM orders_queue WHERE status='pending' AND created_at < datetime('now', '-30 minutes');")
if [ "$PENDING" -gt 5 ]; then
  echo "🟡 ALERTA: ${PENDING} pedidos pending há mais de 30 min"
fi

echo "$(date) | PM2=$PM2_STATUS | Failed%=$FAILED_RATE | PendingOld=$PENDING"
```

```bash
# Adicionar ao crontab
crontab -e
# */15 * * * * /home/ti-kiosk/hub/health_check.sh >> /home/ti-kiosk/hub/health.log 2>&1
```

---

## 5. Dashboard (implementação futura)

### Painel Web no Hub (rota `/admin/observability`)

| Widget | Fonte | Refresh |
|---|---|---|
| Semáforo Token OAuth | `connectors.config.expiresAt` | 1 min |
| Fila por status (donut chart) | `orders_queue GROUP BY status` | 30s |
| Pedidos/hora (line chart) | `orders_queue WHERE success` | 5 min |
| Top 5 erros (bar chart) | `orders_queue WHERE failed` | 5 min |
| PM2 status | `pm2 jlist` | 1 min |
| Lojas ignoradas | `orders_queue WHERE ignorado_loja` | 15 min |

---

## 6. Runbook de Resposta a Alertas

| Alerta | Ação | Playbook |
|---|---|---|
| Token expirado | Renovar via OAuth flow | [PB-008](./PB-008-diagnostico-recuperacao-oauth-hub.md) |
| Taxa de falha > 20% | Verificar logs PM2, categorizar erros | [PB-008](./PB-008-diagnostico-recuperacao-oauth-hub.md) Passo 5 |
| 404 em série | Verificar app OAuth | [PB-008](./PB-008-diagnostico-recuperacao-oauth-hub.md) Passo 4 |
| Motor crashed | `sudo pm2 restart hub-logistico` | — |
| Pending acumulados | Verificar rate limit e motor | [PB-008](./PB-008-diagnostico-recuperacao-oauth-hub.md) Passo 5 |

---

## 7. Critérios de Sucesso

Este plano será considerado eficaz quando:
- [ ] Health check rodando a cada 15 min via cron
- [ ] Incidentes detectados em < 30 min (vs 4 dias no incidente anterior)
- [ ] Dashboard funcional com métricas L1 e L2
- [ ] Runbook testado com simulação de falha de token
- [ ] Alertas via canal de comunicação (Slack/email) integrados

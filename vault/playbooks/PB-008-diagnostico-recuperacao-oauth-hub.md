---
id: PB-008
title: "Diagnóstico e Recuperação de Falhas OAuth no Hub Logístico"
status: active
validates: [RULE-001, RULE-002]
environment: production
kind: runbook
targets: [Hub Logístico, Bling OAuth, J&T Adapter]
severity: P1
trigger: "Pedidos entrando em 'failed' com erros 404/FORBIDDEN na API do Bling"
tags: [playbook, hub-logistico, bling, oauth, incidente]
---


# PB-008: Diagnóstico e Recuperação de Falhas OAuth no Hub

## Quando Usar

- Pedidos acumulando em `failed` com erros `404`, `FORBIDDEN` ou `invalid_grant`
- Token Bling expirando prematuramente ou não renovando
- Webhooks chegando mas pedidos não sendo processados
- Logs do PM2 mostrando `RESOURCE_NOT_FOUND` em série

---

## Passo 1: Verificar Status do Token

```bash
# No servidor (ssh ti-kiosk@191.233.18.195)
cd /home/ti-kiosk/hub

# Verificar token atual
sqlite3 hub.db "SELECT id, SUBSTR(config,1,200) FROM connectors WHERE type='erp';"

# Testar acesso à API
node -e "
const ba=require('./blingAuth'), s=require('sqlite3').verbose(), {open}=require('sqlite');
(async()=>{
  const d=await open({filename:'./hub.db',driver:s.Database});
  const e=await d.get(\"SELECT id,config FROM connectors WHERE type='erp' LIMIT 1\");
  const t=await ba.getValidAccessToken(d,e);
  console.log('Token:', t ? t.substring(0,20)+'...' : 'NULO');
  const ax=require('axios');
  const r=await ax.get('https://api.bling.com.br/Api/v3/pedidos/vendas?limite=1',{headers:{Authorization:'Bearer '+t}});
  console.log('API OK:', r.status, 'Pedidos:', r.data.data?.length);
  await d.close();
})().catch(e=>console.log('ERRO:',e.response?.status,e.response?.data?.error?.type||e.message));
"
```

### Diagnóstico:
| Resultado | Causa Provável | Ir para |
|---|---|---|
| Token NULO | Sem credenciais no banco | Passo 2 |
| `401 unauthorized` | Token expirado, refresh falhou | Passo 3 |
| `404 RESOURCE_NOT_FOUND` | App OAuth errado ou sem escopo | Passo 4 |
| `403 FORBIDDEN` | Sem permissão para o recurso | Passo 4 |
| `429 TOO_MANY_REQUESTS` | Rate limit | Aguardar 60s e repetir |
| `200 OK` | Token funcional | Passo 5 |

---

## Passo 2: Reconfigurar Credenciais

### Apps OAuth conhecidos:

| App | Client ID | Conta Bling Dev | Escopo |
|---|---|---|---|
| **Integração KioskBrands** (PRODUÇÃO) | `baed4213c19c9bfe9804bfc2d0fa6146635bced5` | Tadeu | Completo |
| J&T Express (NÃO USAR) | `cdd2d67baf432b6068f458e8c49602c45b5a1b62` | ecommerce@touti | Limitado |

```bash
# Atualizar clientId/clientSecret no banco
sqlite3 hub.db "UPDATE connectors SET config = json_set(config, '$.clientId', 'baed4213c19c9bfe9804bfc2d0fa6146635bced5', '$.clientSecret', '3da9fd0145a3ea62940eaf38894234e8a014452f6237f80893cc42c3e5c0') WHERE type='erp';"
```

---

## Passo 3: Renovar Token OAuth

1. Abrir URL de autorização (logado como **Tadeu** no Bling):
```
https://www.bling.com.br/Api/v3/oauth/authorize?response_type=code&client_id=baed4213c19c9bfe9804bfc2d0fa6146635bced5&state=hub-reauth
```

2. Copiar o `code` da URL de redirect

3. Trocar code por token:
```bash
node -e "
const ax=require('axios'),s=require('sqlite3').verbose(),{open}=require('sqlite');
const CODE='COLAR_CODE_AQUI';
const CID='baed4213c19c9bfe9804bfc2d0fa6146635bced5';
const CSC='3da9fd0145a3ea62940eaf38894234e8a014452f6237f80893cc42c3e5c0';
(async()=>{
  const auth=Buffer.from(CID+':'+CSC).toString('base64');
  const {data}=await ax.post('https://www.bling.com.br/Api/v3/oauth/token',
    'grant_type=authorization_code&code='+CODE,
    {headers:{'Content-Type':'application/x-www-form-urlencoded',Authorization:'Basic '+auth}});
  console.log('Token OK! Expires:', data.expires_in);
  const d=await open({filename:'./hub.db',driver:s.Database});
  const e=await d.get(\"SELECT id,config FROM connectors WHERE type='erp' LIMIT 1\");
  const cfg=JSON.parse(e.config);
  cfg.accessToken=data.access_token; cfg.refreshToken=data.refresh_token;
  cfg.expiresAt=Date.now()+(data.expires_in*1000);
  await d.run('UPDATE connectors SET config=? WHERE id=?',[JSON.stringify(cfg),e.id]);
  console.log('Banco atualizado!');
  await d.close();
})().catch(e=>console.log('ERRO:',e.response?.status,JSON.stringify(e.response?.data)));
"
```

4. Reiniciar motor:
```bash
sudo pm2 restart hub-logistico
```

---

## Passo 4: Verificar App OAuth Correto

```bash
# Qual clientId está configurado?
sqlite3 hub.db "SELECT json_extract(config,'$.clientId') FROM connectors WHERE type='erp';"
```

| Se retornar | Ação |
|---|---|
| `baed4213...` | Correto (Integração KioskBrands) |
| `cdd2d67...` | **ERRADO** — restaurar app antigo (Passo 2) |
| Outro | Verificar no Bling Developer Portal |

---

## Passo 5: Verificar Fila e Motor

```bash
# Status da fila
sqlite3 hub.db 'SELECT status, COUNT(*) FROM orders_queue GROUP BY status;'

# Pedidos failed recentes
sqlite3 hub.db "SELECT erp_id, SUBSTR(error_log,1,100), created_at FROM orders_queue WHERE status='failed' ORDER BY rowid DESC LIMIT 10;"

# Logs do motor
sudo pm2 logs hub-logistico --lines 20 --nostream

# Motor rodando?
sudo pm2 status
```

---

## Passo 6: Recuperação em Massa

### 6a. Pedidos com etiqueta J&T mas sem rastreio no Bling
```bash
# Listar
sqlite3 hub.db "SELECT erp_id, tracking_number FROM orders_queue WHERE status='failed' AND tracking_number IS NOT NULL;"

# Resetar para pending (motor reprocessa e reusa etiqueta existente)
sqlite3 hub.db "UPDATE orders_queue SET status='pending', error_log=NULL WHERE status='failed' AND tracking_number IS NOT NULL;"
```

### 6b. Pedidos sem etiqueta
```bash
# Resetar para pending (motor gera nova etiqueta)
sqlite3 hub.db "UPDATE orders_queue SET status='pending', error_log=NULL, tracking_number=NULL WHERE status='failed' AND tracking_number IS NULL;"
```

### 6c. Monitorar recuperação
```bash
watch -n 5 "sqlite3 /home/ti-kiosk/hub/hub.db 'SELECT status, COUNT(*) FROM orders_queue GROUP BY status;'"
```

---

## Checklist Pós-Recuperação

- [ ] Token válido e acessando API
- [ ] Fila sem pedidos `pending` acumulados
- [ ] `failed` <= 10 (edge cases conhecidos)
- [ ] Webhooks chegando (verificar `system_logs`)
- [ ] Motor processando novos pedidos automaticamente

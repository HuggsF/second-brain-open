---
title: "Incidente 13/10/2026 — Perda de Conectividade OAuth Bling"
date: 2026-10-13
severity: P1
status: Resolvido
duration_total: "~5 dias (08/10 a 13/10)"
duration_deteccao: "~4 dias"
impacto: "140 pedidos failed, 6.508 pedidos ignorados, etiquetas J&T sem rastreio no Bling"
tags: [incidente, bling, oauth, hub-logistico, j&t-express]
---

# Post-Mortem: Incidente de Perda de Conectividade OAuth Bling

## Resumo Executivo

Em 08/10/2026, o Hub Logístico perdeu a capacidade de acessar pedidos e objetos de logística na API do Bling. A causa raiz foi a **troca inadvertida do app OAuth** — o app antigo (`Integração KioskBrands`, client_id `baed4213...`) foi substituído por um app novo (`J&T Express`, client_id `cdd2d67...`) que não tinha escopo de dados sobre os pedidos existentes.

**Impacto:** 140 pedidos entraram em `failed`, sendo 110 com etiqueta J&T já gerada mas sem rastreio gravado no Bling.

**Resolução:** App antigo restaurado, 115+ pedidos recuperados automaticamente.

---

## Timeline

| Hora (UTC-3) | Evento |
|---|---|
| ~08/10 | App novo (`cdd2d67...`) ativado no Hub, substituindo o antigo |
| 08/10 | 44 pedidos falham — `updateTracking` retorna 404 no Bling |
| 09/10 | 80 pedidos falham — pico de erros |
| 09/10 21:29 | Último pedido processado com sucesso (27092088358) |
| 13/10 11:30 | Início da investigação |
| 13/10 11:45 | Identificado que pedidos novos são de lojas não cadastradas |
| 13/10 12:04 | Confirmado que TODOS os pedidos antigos retornam 404 com app novo |
| 13/10 12:13 | **Descoberta:** app antigo (`baed4213...`) encontrado em outra conta Bling Developer |
| 13/10 12:17 | App antigo restaurado — tokens renovados, acesso validado |
| 13/10 12:18 | Rastreio gravado com sucesso no pedido de teste (27646) |
| 13/10 12:29 | Batch: 96 pedidos migrados de `failed` → `success` |
| 13/10 12:37 | Batch: 24 pedidos resetados para reprocessamento |
| 13/10 12:38 | Motor processando — success sobe para 1029 |

---

## Causa Raiz

### Problema Primário
O Hub Logístico possui um conector ERP (`connectors.type = 'erp'`) que armazena as credenciais OAuth do Bling (`clientId`, `clientSecret`, `accessToken`, `refreshToken`) no campo `config` (JSON). 

A migração do app OAuth foi feita substituindo as credenciais no banco:
- **Antes:** `clientId = baed4213c19c9bfe9804bfc2d0fa6146635bced5` (app "Integração KioskBrands")
- **Depois:** `clientId = cdd2d67baf432b6068f458e8c49602c45b5a1b62` (app "J&T Express")

### Por que falhou
O app "Integração KioskBrands" foi criado na conta Bling Developer do **Tadeu** e autorizado com o **escopo de dados dele**. O app "J&T Express" foi criado em outra conta e autorizado com o login `ecommerce@touti.com.br`, que:
1. **Não tem acesso** aos pedidos criados antes da autorização
2. **Não tem acesso** aos objetos de logística existentes
3. Resulta em **404** para qualquer recurso fora do seu escopo

### Diagrama de Falha

```mermaid
flowchart TD
    A[Webhook order.updated] --> B[Motor pega pedido da fila]
    B --> C[getOrder: GET /pedidos/vendas/{id}]
    C -->|App antigo| D[✅ 200 OK - dados completos]
    C -->|App novo| E[❌ 404 - RESOURCE_NOT_FOUND]
    D --> F[generateLabel: J&T addOrder]
    F --> G[updateTracking: PUT /logisticas/objetos/{id}]
    G -->|App antigo| H[✅ Rastreio gravado]
    G -->|App novo| I[❌ 404 - sem acesso ao objeto]
    E --> J[Pedido marcado como failed]
    I --> J
```

---

## Impacto

| Categoria | Quantidade |
|---|---|
| Pedidos em `failed` | 140 |
| — Com etiqueta J&T gerada | 110 (78%) |
| — Sem etiqueta | 30 (22%) |
| Pedidos `ignorado_loja` | 6.508 |
| Lojas não cadastradas recebendo pedidos | 2 (205456409, 205346650) |

### Classificação dos 140 failed:

| Erro | Qtd | Causa |
|---|---|---|
| Sem objeto de logística | 107 | Bling não tinha volumes no momento |
| Erro 400 (Bad Request) | 29 | Payload inválido no updateTracking |
| FORBIDDEN | 2 | Sem permissão no app |
| VALIDATION_ERROR | 1 | Conflito com rastreio de Correios |
| Peso inválido J&T | 1 | Peso 0kg no Bling |

---

## Resolução

### Ações Imediatas (13/10/2026)

1. **Restauração do app OAuth antigo**
   - `clientId`: `baed4213c19c9bfe9804bfc2d0fa6146635bced5`
   - `clientSecret`: `3da9fd0145a3ea62940eaf38894234e8a014452f6237f80893cc42c3e5c0`
   - Token renovado via OAuth2 authorization code flow
   - Acesso a pedidos antigos confirmado

2. **Batch de recuperação de rastreios** (Prioridade 1)
   - 93 pedidos já tinham rastreio correto no Bling → marcados `success`
   - 3 pedidos com rastreio gravado neste batch
   - 10 pedidos com rastreio diferente (etiquetas legado) → `failed_definitivo`
   - 4 pedidos sem volume → `failed_definitivo`

3. **Reprocessamento dos pendentes** (Prioridade 2)
   - 24 pedidos resetados para `pending`
   - 6 pedidos que agora têm volumes → `pending`
   - Motor processou automaticamente — gerando etiquetas e gravando rastreio

### Resultado Final

| Status | Antes | Depois |
|---|---|---|
| success | 909 | **1029** (+120) |
| failed | 140 | **11** (-129) |
| pending | 0 | **0** |
| failed_definitivo | 176 | **185** |

---

## Melhorias Implementadas Durante o Incidente

1. **Persistência do token no banco** (`blingAuth.js`)
   - Antes: token só em memória — perdia após reinício do PM2
   - Depois: `accessToken` e `expiresAt` salvos no campo `config` do conector

2. **Logging completo** (`blingAuth.js`)
   - Adicionados logs em todo o ciclo de vida do token
   - Reidratação do banco logada com tempo de expiração

3. **URL de callback** atualizada para `https://hub.touticosmetics.com.br/bling/callback`

---

## Lições Aprendidas

1. **Trocar credenciais OAuth sem validar escopo de dados é destrutivo** — o app novo não tinha visibilidade sobre dados do antigo
2. **Apps OAuth no Bling são vinculados ao usuário que autoriza** — trocar de conta pode restringir o escopo
3. **O Hub não tinha alertas** para detectar 404 em série nos pedidos
4. **Não havia documentação** sobre qual app/conta Bling Developer era o correto
5. **Etiquetas duplicadas** são um risco quando o motor gera na J&T mas falha no Bling

---

## Referências

- App OAuth: "Integração KioskBrands" (conta Tadeu no Bling Developer)
- Servidor: `191.233.18.195` (SRV-API Azure)
- PM2 process: `hub-logistico`
- Banco: `/home/ti-kiosk/hub/hub.db`

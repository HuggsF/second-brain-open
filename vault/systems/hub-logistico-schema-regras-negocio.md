---
title: "Hub Logístico — Schema do Banco, Regras de Negócio e Fluxos"
date: 2026-10-13
type: reference
tags: [hub-logistico, banco-de-dados, regras-negocio, schema]
---

# Hub Logístico — Schema do Banco e Regras de Negócio

## Schema SQLite (`hub.db`)

### Tabela: `connectors`
Armazena as integrações (ERP + transportadoras).

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `type` | TEXT | `erp` (Bling) ou `carrier` (J&T) |
| `name` | TEXT | Nome do conector |
| `label` | TEXT | Rótulo de exibição (ex: "ESPIRITO SANTO - J&T") |
| `config` | TEXT (JSON) | Credenciais e configuração |
| `active` | INTEGER | 1 = ativo, 0 = inativo |

#### Estrutura do `config` (type = 'erp'):
```json
{
  "clientId": "baed4213...",
  "clientSecret": "3da9fd01...",
  "accessToken": "jwt...",
  "refreshToken": "rt...",
  "expiresAt": 1728835200000
}
```

#### Estrutura do `config` (type = 'carrier'):
```json
{
  "code": "J0086038727",
  "acc": "899296264686898176",
  "pwd": "C847Fx66",
  "key": "25c57a91af41424e9b0e0204a1cb3955",
  "remetente": {
    "nome": "COSMETIC LOG LTDA",
    "cnpj": "61769169000103",
    "ie": "084591730",
    "cep": "29135008",
    "uf": "ES",
    "cidade": "Viana",
    "endereco": "AVENIDA ALCACIBAS FURTADO",
    "numero": "800",
    "complemento": "GALPÃO G02",
    "email": "ecommerce@kioskbrands.com",
    "telefone": "81984203388"
  }
}
```

#### Conectores configurados (produção):

| ID | Tipo | Nome | Label |
|---|---|---|---|
| 1 | erp | Bling v3 | — |
| 2 | carrier | J&T Express | ESPIRITO SANTO - J&T |
| 3 | carrier | J&T Express | RECIFE - J&T |

---

### Tabela: `orders_queue`
Fila principal de processamento.

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `erp_id` | TEXT | ID do pedido no Bling (ex: "27069630582") |
| `universal_payload` | TEXT (JSON) | Dados do pedido em formato universal |
| `status` | TEXT | Status do processamento (ver abaixo) |
| `error_log` | TEXT | Mensagem de erro (quando failed) |
| `retries` | INTEGER | Número de tentativas (default 0) |
| `tracking_number` | TEXT | Código de rastreio J&T (billCode) |
| `next_attempt_at` | DATETIME | Próxima tentativa agendada |
| `created_at` | DATETIME | Data de inserção na fila |

#### Status da fila:

| Status | Significado | Transições |
|---|---|---|
| `pending` | Aguardando processamento | → `processing` |
| `processing` | Motor processando agora | → `success` / `failed` |
| `success` | Etiqueta gerada e rastreio gravado | Terminal |
| `failed` | Erro recuperável, pode retentar | → `pending` (retry) |
| `failed_definitivo` | Erro irrecuperável | Terminal |
| `cancelado` | Pedido cancelado no Bling | Terminal |
| `ignorado_loja` | Loja sem geração automática | Terminal |

#### Índices:
- `idx_orders_erp_status` em `(erp_id, status)` — usado pelo `findAutomaticQueueBlock`

---

### Tabela: `lojas`
Configuração de lojas Bling para geração automática.

| Campo | Tipo | Descrição |
|---|---|---|
| `id_bling` | INTEGER PK | ID da loja no Bling |
| `nome` | TEXT | Nome da loja |
| `tipo` | TEXT | Tipo (LojaFisica, Shopify, TikTok, etc.) |
| `gerar_automatico` | INTEGER | 1 = gerar etiqueta automaticamente |
| `remetente` | TEXT (JSON) | Dados do remetente específico |
| `connector_id` | INTEGER | FK → connectors.id (transportadora) |

#### Lojas configuradas:

| ID Bling | Nome | Tipo | Auto | Conector |
|---|---|---|---|---|
| 206084387 | KIOSK RECIFE | LojaFisica | ✅ 1 | 3 (Recife) |
| 206085936 | KIOSK ESPIRITO SANTO | LojaFisica | ✅ 1 | 2 (ES) |
| 206133846 | Shopify 15:31:15 | Shopify | ❌ 0 | — |
| 206171604 | Essência Mariana - TikTok | TikTok | ❌ 0 | — |
| 206236677 | Mercado Livre - 01 | MercadoLivre | ❌ 0 | — |
| 206264482 | YAMPI-ESSENCIA-MARIANA | Yampi | ❌ 0 | — |
| 206271368 | API-TRANSPORT | Api | ❌ 0 | — |
| 206281888 | Shopify 14:12:34 | Shopify | ❌ 0 | — |
| 206288765 | Yes cosmetics | LojaFisica | ❌ 0 | — |
| 206293377 | Bonificado Recife | LojaFisica | ❌ 0 | — |

> **⚠️ ATENÇÃO:** Lojas `205456409` e `205346650` recebem pedidos mas **não estão cadastradas** — pedidos dessas lojas são marcados `ignorado_loja`.

---

### Tabela: `jt_emissions`
Controle de emissões na J&T (evita duplicidade).

| Campo | Tipo | Descrição |
|---|---|---|
| `erp_id` | TEXT PK | ID do pedido no Bling |
| `txlogistic_id` | TEXT NOT NULL | ID do pedido no Hub (`HUB-{erpId}-{timestamp}`) |
| `state` | TEXT | `uncertain` ou `confirmed` |
| `tracking_number` | TEXT | billCode da J&T |
| `created_at` | DATETIME | Quando foi emitido |

---

### Tabela: `system_logs`
Log de eventos do sistema.

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `type` | TEXT | `info`, `error`, `warn` |
| `message` | TEXT | Mensagem do log |
| `created_at` | DATETIME | Timestamp |

---

### Tabela: `users`
Autenticação do painel web.

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Auto-incremento |
| `username` | TEXT UNIQUE | Login |
| `password` | TEXT | Hash da senha |
| `role` | TEXT | `operador` ou `admin` |

---

## Regras de Negócio

### RN-001: Admissão na Fila
- **Trigger:** Webhook `order.updated` do Bling
- **Filtro 1:** Situação deve ser `9` (Atendido) — senão ignora
- **Filtro 2:** `findAutomaticQueueBlock` verifica se já existe na fila com status `pending`, `processing`, `success`, ou `failed` com erro de revisão
- **Filtro 3:** Loja do pedido deve estar em `lojas` com `gerar_automatico = 1` — senão marca `ignorado_loja`

### RN-002: Fluxo de Processamento
```
1. getOrder(erpId, token)     → Busca pedido no Bling
2. Verifica loja              → gerar_automatico = 1?
3. Verifica NF                → notaFiscal.id existe?
4. GET /nfe/{id}              → Busca chave de acesso (44 dígitos)
5. assertValidInvoice()       → Valida NF
6. generateLabel()            → J&T addOrder → retorna billCode
7. updateTracking()           → PUT /logisticas/objetos/{id}
8. Confirma gravação          → GET /logisticas/objetos/{id}
9. Marca success              → orders_queue.status = 'success'
```

### RN-003: Reaproveitamento de Etiqueta
- Se o pedido **já tem** `tracking_number` na fila E a J&T já tem o billCode → **não gera nova etiqueta**
- Se o Bling **já tem** o rastreio correto → **não faz PUT** no objeto

### RN-004: Rastreio Pré-existente
- Se `transporte.volumes[0].codigoRastreamento` já existe no Bling (ex: Correios) → **não sobrescreve**
- O motor marca como `REVIEW_REQUIRED`

### RN-005: Renovação de Token OAuth
- Token expira em 6h (21600s)
- `blingAuth.js` renova automaticamente com `refresh_token`
- **⚠️ O Bling rotaciona o refresh_token** — o antigo deixa de funcionar
- Token e `expiresAt` são persistidos no campo `config` do conector

### RN-006: Rate Limiting Bling
- Limite: 3 requests/segundo
- `aguardarSlotBling()` controla o intervalo entre chamadas
- `chamarBlingComRetry()` faz retry automático em caso de 429

### RN-007: Formato txlogisticId
- Hub gera: `HUB-{erpId}-{timestamp}` (ex: `HUB-27092088358-1791581195035`)
- Único por emissão — permite rastrear no J&T qual pedido do Hub gerou

### RN-008: Mapeamento Loja → Conector
- Cada loja pode ter um `connector_id` apontando para um conector `carrier` específico
- Se a loja tem `remetente` próprio → usa o endereço da loja (não o padrão do conector)
- Se não tem `connector_id` → usa o conector padrão

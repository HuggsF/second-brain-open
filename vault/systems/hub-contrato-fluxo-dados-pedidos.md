---
type: system
status: active
date: 2026-10-21
related: [hub-regras-operacionais-codex, hub-logistico-schema-regras-negocio]
source: hub-logistico/docs/contratos/fluxo-dados-pedidos.md
source_branch: codex/detailed-integration-logs
---

# Contrato de Dados — Fluxo de Pedidos (Bling → Hub → J&T/Corpem)

Referência de código: branch `feature/invoice-webhook-trigger`, baseada na `main` (`81eb116`).
Descreve o que o Hub recebe, grava e expõe sobre pedidos. Documento descritivo (sem propostas
de mudança). Alterações no fluxo devem atualizar este doc no mesmo PR.

## Identificadores

| Campo | Origem Bling | Uso no Hub |
|-------|-------------|------------|
| `orders_queue.erp_id` | `pedido.id` (id interno venda API v3) | Chave do pedido em toda a fila, `jt_emissions` e GET vendas |
| `orders_queue.invoice_id` | `pedido.notaFiscal.id` / evento fiscal | ID interno da NF, separado do ID pedido |
| `universal_payload.orderId` | `pedido.id` (string) | Igual ao `erp_id` |
| `universal_payload.orderNumber` | `pedido.numero` (visível no painel) | Exibição. **Não** é o `erp_id` |

## Entrada na Fila

Toda entrada cria `orders_queue` com `erp_id` e (na admissão fiscal) `invoice_id`:
`status='pending'`, `universal_payload=NULL`, `created_at` em UTC.

| Via | Condição | Código |
|-----|----------|--------|
| Evento `invoice.created/updated` em `POST /webhook/bling` | HMAC válido; NF situação 5/6, chave válida, vínculo pedido sit. 6/9/748644, loja autorizada e habilitada; admissão atômica sem duplicidade | `server.js`, `invoiceEvents.js` |
| Envio manual `POST /api/enviar` | Perfil admin/operador; sem emissão ativa | `server.js:728-815` |

**Novas entradas automáticas dependem de NF elegível, não da situação Atendido.**

Lojas autorizadas: Essência Mariana (206264482), Kiosk Recife (206084387),
Kiosk Espírito Santo (206085936), Yes Cosmetics (206288765).

## Ciclo de Vida de `orders_queue.status`

| Status | Quem Grava | `universal_payload` |
|--------|-----------|---------------------|
| `pending` | entrada; retry com `next_attempt_at` | `NULL` na entrada; mantém anterior em retry |
| `processing` | motor ao reservar job | sem alteração |
| `ignorado_loja` | motor, loja fora das autorizadas | **completo** |
| `success` | motor, após etiqueta J&T + rastreio Bling + WMS | **completo** |
| `failed` | motor, erro definitivo ou tentativas esgotadas | completo se `getOrder` respondeu; senão `NULL` |
| `cancelado` | cancelamento Bling antes de processar ou manual após `success` | `NULL` se antes; mantém payload se após `success` |

Um mesmo `erp_id` pode ter várias linhas. Estado atual = linha de maior `id`.

## `universal_payload` (JSON do Motor)

Montado por `adapters/bling.js#getOrder` a partir de `GET /pedidos/vendas/{id}`,
`GET /contatos/{id}` e `GET /nfe/{id}`. É um retrato do momento do processamento
(não se atualiza se o pedido mudar depois).

| Campo | Fonte Bling | Observação |
|-------|-------------|------------|
| `orderId`, `orderNumber` | `id`, `numero` | — |
| `trackingNumber` | rastreio existente ou emitido J&T | também em `orders_queue.tracking_number` |
| `store.id/nome` | `loja.id/nome` | `nome` costuma vir vazio; confiável em `lojas.nome` |
| `situacao.id/nome` | `situacao.id`, traduzido | momento do processamento |
| `invoiceMoney` | `pedido.total` | **Total do pedido de venda**, não o valor da NF |
| `customer.*` | `contato.*` | contém dados pessoais |
| `address.*` | `transporte.etiqueta` ou endereço contato | `state` = UF entrega |
| `package.weight/qty` | `transporte.pesoBruto/volumes.length` | peso padrão `"1.00"` se zero |
| `invoice.*` | `GET /nfe/{id}` | `null` sem NF; **não inclui valor da nota** |
| `invoiceError` | falha ao buscar NF | texto; bloqueia nova emissão |

## Tabelas Complementares

- `invoice_events`: eventos fiscais duráveis (ID nota, reserva, estado, diagnóstico, retentativas)
- `jt_emissions(erp_id PK, txlogistic_id, state, tracking_number, created_at)`: intenção/confirmação emissão J&T
- `lojas(id_bling PK, nome, tipo, gerar_automatico, remetente, connector_id)`: cadastro local
- `system_logs(type, message, created_at)`: texto livre, sem estrutura

## Capacidades de Analytics

| Métrica | Viável | Limitação |
|---------|--------|-----------|
| Pedidos/dia por loja, UF, transportadora | Sim | loja/UF só para processados |
| Status de processamento | Sim | estado da linha mais recente |
| Valor dos pedidos | Sim (ressalva) | `invoiceMoney` (total pedido) dos `success` |
| **Valor faturado (NF)** | **Não** | Hub não grava `valorNota` de `GET /nfe/{id}` |
| Motivos de falha | Sim | `error_log` texto livre, agrupado |
| Tempo/SLA de processamento | Não | sem timestamp de conclusão |
| Vendas totais Bling | Não | fila não é universo de vendas |

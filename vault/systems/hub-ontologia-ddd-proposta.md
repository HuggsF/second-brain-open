---
type: system
status: active
date: 2026-10-21
related: [hub-arquitetura-ddd-typescript, hub-mapa-entidades-dominios]
---
# Proposta de Ontologia DDD e Nomenclatura do Hub Logístico

Síntese do documento-fonte `hub-logistico/docs/contratos/proposta-nomenclatura-acoplamento.md`
(217 linhas, 21/10/2026). Status: **proposta para revisão, não aplicada ao runtime**.

> A abordagem recomendada é renomear e separar contratos por capacidade em etapas, preservando
> bancos e contratos externos, com mappers e aliases temporários.

## Entidades e Modelos Propostos

| Nome Atual (código) | Nome Proposto | Natureza |
|---|---|---|
| `Order` (ligado a `orders_queue`) | `DispatchJob` | Modelo operacional: reserva, estado e tentativas. Não é a venda. |
| `OrderStatus` (fila) | `DispatchJobStatus` | Estado operacional, separado da situação comercial e fiscal. |
| Pedido obtido do ERP | `SalesOrderSnapshot` | Visão imutável da venda observada no ERP. |
| `UniversalPayload` | `DispatchRequest` (composto por snapshots) | DTO de aplicação para despacho; não deve ser entidade universal. |
| `ValidatedInvoice` | `NfeSnapshot` + resultado de `NfeDispatchPolicy` | Snapshot fiscal e decisão explícita de aptidão. |
| Volume / objeto Bling | `LogisticsVolume` / `LogisticsVolumeSnapshot` | Volume identificado, separado de pacote, serviço e rastreio. |
| Serviço logístico | `LogisticsServiceRef` | Identidade do serviço na conta de origem. |
| `Store` | `StoreDispatchSettings` | Habilitação, remetente e vínculo de transportadora. Não é toda a loja. |
| `Connector` | `IntegrationConnection` | Configuração técnica de conexão externa, na camada de integração. |
| Conta de transportadora | `CarrierAccountRef` | Referência lógica à conta; diferente do cadastro `dtransportadora`. |
| `EmissionIntent` | `ShipmentEmissionIntent` | Intenção durável de criar envio; não é emissão de NF. |
| `ShippingLabel` | `ShipmentReference` + `ShippingLabelDocument` | Separar referência de envio/rastreio do conteúdo imprimível. |
| `SenderAddress` / endereço | `SenderAddress` + `DeliveryAddress` | Papéis distintos, sem aliases de fornecedor. |
| Cliente no payload | `RecipientSnapshot` / `CustomerSnapshot` | Destinatário ≠ comprador ≠ contato cadastral. |
| `order_bling_status` | `SalesOrderObservation` | Última informação observada, com fonte e horário. |

## Campos e Identidades

| Campo Atual | Nome Interno Proposto | Compatibilidade |
|---|---|---|
| `erp_id`, `erpId` | `salesOrderId` | Manter coluna legada via mapper. |
| `invoice_id`, `invoiceId` | `nfeId` | Não traduzir para número ou chave. |
| `orderId` (payload) | `salesOrderId` | Não confundir com `dispatchJobId`. |
| `orderNumber` | `salesOrderNumber` | Referência comercial para exibição. |
| `id_volume` / `id_obj_logistica` | `logisticsVolumeId` | Objeto Bling, não serviço. |
| `txlogisticId` | `shipmentRequestId` | Identidade estável da intenção. |
| `invoiceMoney` | `nfeAmount` | Renomear não corrige origem (hoje vem de `pedido.total`). |

## Portas por Capacidade

| Contrato Amplo Atual | Contratos Candidatos |
|---|---|
| `ErpPort` | `SalesOrderReaderPort`, `NfeReaderPort`, `TrackingWriterPort`, `DanfeReaderPort` |
| `CarrierPort` | `CreateShipmentPort`, `ShipmentReaderPort`, `CancelShipmentPort`, `ShippingLabelReaderPort` |
| `StoreRepositoryPort` | `StoreDispatchSettingsReaderPort`, `CarrierAccountResolverPort` |
| `InvoiceRepositoryPort` | `NfeEventInboxPort`, `AdmitDispatchJobPort` |
| `OrderRepositoryPort` | `DispatchJobRepositoryPort` |
| `WmsPort` | `WarehouseDispatchNotifierPort` |

## Use Cases

| Nome Existente | Nome Canônico Proposto |
|---|---|
| `ReceiveInvoiceEventUseCase` | `ReceiveNfeEventUseCase` |
| `AdmitFiscalNoteUseCase` / `QualifyOrderByInvoiceUseCase` | `QualifyDispatchFromNfeUseCase` |
| `ProcessOrderUseCase` / `DispatchOrderUseCase` | `ExecuteDispatchJobUseCase` |
| `HandleBlingWebhookUseCase` | `BlingWebhookHandler` (handler de borda) |
| `PrintLabelUseCase` | `PrintShippingLabelUseCase` |
| `InvoiceEventProcessor` | Worker chamando `QualifyDispatchFromNfeUseCase` |

## Regras de Dependência

- **Domínio** não importa aplicação, adapters, runtime, HTTP, ORM, fila, OAuth, SDK, `process.env`.
- **Aplicação** não importa adapter concreto.
- **CompositionRoot** conhece implementações e as injeta.

## Estrutura-Alvo

```
src/
  domain/
    sales/             snapshots e valores comerciais
    fiscal/            valores fiscais e políticas de aptidão
    shipping/          intenção de emissão e decisões de segurança
  application/
    dispatch/          DispatchJob e casos de uso de coordenação
    invoice-events/    recebimento e qualificação por evento
    queries/           leituras do painel
    ports/             contratos de saída por capacidade
  adapters/
    bling/ jt/ corpem/ sqlite/ http/ messaging/
  bootstrap/           composição e configuração
```

## Plano de Adoção (6 Etapas)

1. Aprovar vocabulário e convenções; registrar ADR por repositório.
2. Criar nomes canônicos e mappers, mantendo contratos públicos, IDs, colunas e status.
3. Separar portas por capacidade com adapters delegando à implementação existente.
4. Separar tarefa (`DispatchJob`), snapshots e intenção de emissão. Preservar admissão atômica.
5. Centralizar regras duplicadas e substituir decisões por mensagens por códigos tipados.
6. Ativar checks de dependência e contratos para módulos migrados.

> Em cada etapa: demonstrar que o sistema continua bloqueando emissão incerta/conflitante,
> reaproveitando rastreio confirmado, confirmando gravação no Bling e preservando cancelamentos.

Relacionado: [[hub-arquitetura-ddd-typescript]], [[hub-mapa-entidades-dominios]],
[[hub-gatilho-nfe-e-politicas-de-emissao]].

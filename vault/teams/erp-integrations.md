# Time: ERP & Integrações Core

## Escopo
SAP (ERP da holding KIOSK Brands), dados fiscais, notas fiscais, catálogo centralizado de produtos e integrações core entre os sistemas da holding.

## Sistemas sob responsabilidade
- [[sap]] — ERP SAP da holding
- [[discovery-gaps-bling-yampi]] — Gaps de integração e conciliação de catálogo

## Comunicação com outros times

| Protocolo | Time destino | Descrição |
|-----------|-------------|-----------|
| `demand` | Desenvolvimento (Dev) | Implementação de novos conectores e rotinas de conciliação |
| `adr` | Logística & Fulfillment | Decisões fiscais e de catálogo que afetam emissão de frete |
| `webhook-contract` | CRM & Salesforce | Dados de franqueado e financeiro para visão 360 no CRM |

## Demandas Ativas
{Consulte `vault/demands/` filtrando por `owner_team: erp-integrations`.}

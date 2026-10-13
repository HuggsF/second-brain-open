# Time: CRM & Salesforce

## Escopo
Gestão do relacionamento com franqueados, atendimento (Service Cloud), vendas (Sales Cloud) e migração dos sistemas legados SULTS e Holmes para Salesforce.

## Sistemas sob responsabilidade
- [[salesforce]] — Plataforma Salesforce (CRM)
- [[sults]] — Sistema legado de franquias (em migração)
- [[holmes]] — Sistema legado de atendimento (em migração)

## Comunicação com outros times

| Protocolo | Time destino | Descrição |
|-----------|-------------|-----------|
| `demand` | Desenvolvimento (Dev) | Webhooks e rotinas de ingestão de dados para visão 360 do franqueado |
| `webhook-contract` | ERP & Integrações | Contratos de integração com SAP para dados cadastrais e financeiros |
| `adr` | Arquitetura & Tech Lead | Alinhamento do plano de migração SULTS/Holmes para Salesforce |

## Demandas Ativas
{Consulte `vault/demands/` filtrando por `owner_team: crm-salesforce`.}

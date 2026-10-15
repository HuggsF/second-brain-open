---
type: domain
status: active
date: 2026-10-13
---
# Domínio: Logística & Fulfillment

## Escopo
Operação do Hub Logístico, emissão de etiquetas J&T, rastreamento de pedidos, integração com Bling API v3 e gestão de transportadoras para as marcas Touti, Amavia e Yes! Cosméticos.

## Sistemas sob responsabilidade
- [[hub-producao]] — Instância de produção do Hub Logístico
- [[hub-homologacao]] — Instância de homologação
- [[bling-api-v3-especificacao-pedidos]] — Especificação de pedidos Bling
- [[hub-bling-logistics-diagnosis]] — Diagnósticos de gargalos na esteira de despacho

## Regras de Negócio
- [[RULE-001-emissao-exige-nf-real]] — Toda emissão exige NF real
- [[RULE-002-homologacao-sem-chamadas-externas]] — Homologação sem chamadas externas

## Referências
- [[backlog-analise-hub-logistico]]
- [[deploy-validacao-hub-2026-10-08]]
- [[investigacao-duplicidade-etiquetas]]
- [[hub-logistics-preflight]]

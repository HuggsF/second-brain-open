---
type: rule
id: RULE-005
title: Objeto logístico Bling deve existir antes de emissão
status: active
source: vault/systems/hub-regras-operacionais-codex.md:47
domain: logistica
---

## Descrição

O objeto logístico do Bling deve existir e ser válido antes de qualquer emissão de etiqueta:

- **Zero volumes ou ID ausente:** se o pedido tem zero volumes ou o ID do objeto logístico está ausente, o pedido deve ser marcado como `REVIEW_REQUIRED` com motivo `LOGISTICS_OBJECT_MISSING` antes de criar intent J&T.
- **Múltiplos volumes:** se o pedido possui múltiplos volumes sem definição clara de divisão, deve ser marcado como `REVIEW_REQUIRED` com motivo `MULTIPLE_VOLUMES_UNDEFINED`.
- **Sem contrato presumido:** o sistema não deve presumir a existência de contrato para criação automática de objeto logístico. A criação deve ser explícita.

## Invariantes

Baseado nos invariantes PREFLIGHT-01 a PREFLIGHT-07 definidos no sistema fonte.

## Referências

- PR #38
- Source: [hub-regras-operacionais-codex.md](vault/systems/hub-regras-operacionais-codex.md)

## Playbooks

- PB-001
- PB-016

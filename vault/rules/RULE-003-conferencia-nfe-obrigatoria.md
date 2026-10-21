---
type: rule
id: RULE-003
title: Conferência NF-e obrigatória antes de despacho automático
status: active
source: vault/systems/hub-gatilho-nfe-e-politicas-de-emissao.md:67
domain: logistica
---

## Descrição

A NF-e deve ser validada antes de qualquer despacho automático. Os seguintes critérios são obrigatórios:

- **Situação fiscal:** NF deve estar com situação 5 (autorizada) ou 6 (denegada com restrição conhecida).
- **Número:** deve ser positivo (> 0).
- **Série:** deve ser válida (não vazia, não nula).
- **Chave de acesso:** deve conter exatamente 44 dígitos e não pode ser composta apenas por zeros.
- **Data de emissão:** deve ser uma data válida e não futura.

Caso a consulta da NF-e falhe (timeout, erro de API, resposta incompleta) ou qualquer um dos campos acima esteja ausente ou inválido, a emissão deve ser **bloqueada** antes de criar o intent J&T.

## Invariantes

Baseado nos invariantes NFE-01 a NFE-13 definidos no sistema fonte.

## Referências

- PR #50 (conferencia-nf)
- Source: [hub-gatilho-nfe-e-politicas-de-emissao.md](vault/systems/hub-gatilho-nfe-e-politicas-de-emissao.md)

## Playbooks

- PB-001
- PB-014

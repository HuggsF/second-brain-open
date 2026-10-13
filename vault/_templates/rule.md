---
id: RULE-{NNN}
title: {Título curto e descritivo da regra}
status: {active | draft | deprecated}
source: {vault/systems/documento-fonte.md:linha}
domain: {logistica | fiscal | ecommerce | atendimento | infra}
team: {logistics | erp-integrations | crm-salesforce | platform | ecommerce}
---

# RULE-{NNN}: {Título curto e descritivo da regra}

## Enunciado

{Descreva a regra de forma precisa e verificável. Evite ambiguidade. A regra deve ser validável por um playbook automatizado ou manual.}

## Origem

[[{documento-fonte}]], seção {nome-da-seção} (linha {N}). {Contexto adicional sobre como a regra foi identificada.}

## Playbooks que a validam

{PB-NNN} ({descrição curta}). As execuções ficam no registro local e se consultam com `cli.py evidence RULE-{NNN}` ou pela ferramenta MCP `get_rule_evidence`.

## Impacto

- **Time principal:** {time responsável}
- **Times dependentes:** {times afetados se a regra mudar}
- **Sistemas:** [[{sistema-1}]], [[{sistema-2}]]

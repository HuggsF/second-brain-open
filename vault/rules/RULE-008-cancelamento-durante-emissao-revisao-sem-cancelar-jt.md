---
id: RULE-008
title: Cancelamento recebido durante a emissão vai para revisão e não cancela na J&T
status: active
source: vault/systems/hub-gatilho-nfe-e-politicas-de-emissao.md:60
domain: logistica
---

# RULE-008: Cancelamento recebido durante a emissão vai para revisão e não cancela na J&T

## Enunciado

Se o Bling notificar cancelamento depois que o motor obteve ou reaproveitou uma etiqueta J&T, a linha vai para `failed` com erro `REVIEW_REQUIRED`, preservando o código de rastreio intacto. O Hub não cancela nada na J&T. Gravações finais e retentativas não sobrescrevem um cancelamento recebido durante a chamada HTTP. Cancelamento no meio de uma chamada externa já enviada exige conferência manual, porque não há cancelamento transacional entre SQLite e transportadora. Código marcado `cancelado` em qualquer linha do mesmo pedido bloqueia reaproveitamento.

## Origem

[[hub-gatilho-nfe-e-politicas-de-emissao]], seção Race conditions no cancelamento (linhas 60 a 65), e [[protecoes-processamento-emissao-hub]], linhas 18 a 21. Invariantes INV-09, INV-10, INV-11 e WEIGHT-04 em [[hub-regras-operacionais-codex]]. O cancelamento `cancelado` é sinal conservador: não confirma cancelamento externo.

## Playbooks que a validam

PB-018 (cancelamento durante a emissão em homologação). As execuções ficam no registro local e se consultam com `cli.py evidence RULE-008` ou pela ferramenta MCP `get_rule_evidence`.

## Impacto

- **Time principal:** Logística (Hub).
- **Times dependentes:** Expedição (revisão manual) e Atendimento (cancelamento de pedido).
- **Sistemas:** [[hub-producao]], [[hub-homologacao]], Bling (webhook de pedido), J&T (adapter).

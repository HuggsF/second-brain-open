---
id: RULE-006
title: Intenção J&T uncertain não é reemitida automaticamente
status: active
source: vault/systems/protecoes-processamento-emissao-hub.md:27
domain: logistica
---

# RULE-006: Intenção J&T uncertain não é reemitida automaticamente

## Enunciado

Cada `erp_id` tem no máximo uma intenção em `jt_emissions`, gravada com `txlogistic_id` **antes** da chamada à J&T. Se o estado for `uncertain` (timeout, rejeição ou falha após a intenção), o motor não cria nova intenção nem chama `addOrder` de novo para esse pedido, nem no retry automático nem após reinício do processo. Reenvio manual do job não limpa a intenção. Não há idempotência presumida da J&T, portanto a repetição pode duplicar frete.

## Origem

[[protecoes-processamento-emissao-hub]], seção Registro de emissão (linhas 25 a 28). Confirmado pelos invariantes INV-03 a INV-07 e NFE-13 do [[hub-regras-operacionais-codex]]. Motivo registrado: a duplicidade de etiquetas e cobrança dupla de frete de 2026-10-08 ([[investigacao-duplicidade-etiquetas]]).

## Playbooks que a validam

PB-017 (reconciliação de emissão uncertain, procedimento manual de produção). As execuções ficam no registro local e se consultam com `cli.py evidence RULE-006` ou pela ferramenta MCP `get_rule_evidence`.

## Impacto

- **Time principal:** Logística (Hub).
- **Times dependentes:** Expedição (fila de revisão) e Financeiro (cobrança de frete).
- **Sistemas:** [[hub-producao]], [[hub-homologacao]], J&T (adapter).

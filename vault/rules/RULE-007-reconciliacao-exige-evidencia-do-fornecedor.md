---
id: RULE-007
title: Reconciliação de emissão incerta exige evidência do fornecedor
status: active
source: vault/systems/protecoes-processamento-emissao-hub.md:32
domain: logistica
---

# RULE-007: Reconciliação de emissão incerta exige evidência do fornecedor

## Enunciado

Uma linha `uncertain` não é apagada para liberar a fila, e uma nova intenção só é liberada depois de confirmação operacional e evidência do fornecedor (J&T) de que não houve emissão. Antes disso, o consumidor da fila deve estar parado e a conferência é feita em `erp_id`, `txlogistic_id`, estado, rastreio e linhas da fila. Processing abandonado não é reativado enquanto houver consumidor ativo ou emissão externa não verificada. Rastreio já confirmado é reaproveitado, nunca reemitido.

## Origem

[[protecoes-processamento-emissao-hub]], seção Procedimento de recuperação (linhas 32 e 33), e DEM-03 e DEM-15 em [[hub-regras-operacionais-codex]] e [[backlog-analise-hub-logistico]]. A resolução automática de `uncertain` ainda não foi validada; por isso a regra é manual.

## Playbooks que a validam

PB-017 (reconciliação de emissão uncertain). As execuções ficam no registro local e se consultam com `cli.py evidence RULE-007` ou pela ferramenta MCP `get_rule_evidence`.

## Impacto

- **Time principal:** Logística (Hub).
- **Times dependentes:** Expedição e Financeiro.
- **Sistemas:** [[hub-producao]], [[protecoes-processamento-emissao-hub]].

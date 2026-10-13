---
id: PB-{NNN}
title: {Nome descritivo do cenário de teste}
status: {active | draft | deprecated}
validates: [{RULE-NNN}]
environment: {local | hml | production}
targets: [{Sistema alvo}]
team: {logistics | erp-integrations | crm-salesforce | platform | ecommerce}
---

# PB-{NNN}: {Nome descritivo do cenário de teste}

## Cenário

- **Dado** {pré-condição do ambiente ou estado do sistema}.
- **Quando** {ação executada ou evento disparado}.
- **Então** {resultado esperado e verificável}.

## Resultado esperado

{Descreva o critério de aprovação ou reprovação. Seja específico: qual saída, qual estado, qual comportamento.}

## Pré-requisitos

- {Pré-requisito 1: ex. "Node 18+ instalado"}
- {Pré-requisito 2: ex. "Banco de homologação acessível"}

## Como executar

```bash
{Comando ou passos para executar o playbook}
```

## Registro

{Descreva como o resultado é registrado. Exemplo: "Quem roda registra com `record_test_execution` via MCP ou `cli.py evidence record`."}

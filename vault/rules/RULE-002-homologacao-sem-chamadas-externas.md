---
type: rule
id: RULE-002
title: Em homologação nenhum job chama ERP, J&T ou WMS
status: active
source: vault/systems/protecoes-processamento-emissao-hub.md:39
domain: logistica
---

# RULE-002: Em homologação nenhum job chama ERP, J&T ou WMS

## Enunciado

Em homologação o motor mantém os jobs pendentes sem chamar ERP, J&T ou WMS, e `generateLabel` também rejeita chamadas diretas. Não existe bypass por envio manual nem por ligar uma loja.

## Origem

[[protecoes-processamento-emissao-hub]], seção Homologação (linha 34). O ambiente é identificado por `HUB_ENV=hml` (ou, em instalações anteriores, por `NODE_ENV` ou pelo nome do banco). Teste financeiro real ou sandbox não foi habilitado.

## Playbooks que a validam

PB-001 (suíte automatizada do Hub) e PB-003 (homologação sem chamada externa). PB-007 (disaster recovery) também declara validá-la. PB-004 foi aposentado e PB-005 voltou a rascunho em 29/10/2026 ([[ADR-043-modelo-de-governanca-tipos-e-relacoes]]). As execuções se consultam com `cli.py evidence RULE-002` ou pela ferramenta MCP `get_rule_evidence`.

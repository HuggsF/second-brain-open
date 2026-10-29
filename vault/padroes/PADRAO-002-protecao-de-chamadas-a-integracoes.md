---
type: padrao
id: PADRAO-002
title: "Proteção de chamadas a integrações: disjuntor, retry com jitter e isolamento"
status: active
date: 2026-10-29
dono: ["Hugo Melo (TI)", "Gustavo Bastos (E-commerce)"]
problema: "integracao-degradada-derruba-o-fluxo"
adocao: proposto
aplicado_em: []
---
# PADRAO-002: Proteção de chamadas a integrações

## Problema
Uma integração lenta ou fora do ar (ERP, transportadora, SEFAZ) prende workers e conexões e
espalha a falha para o resto do fluxo. Retry sem limite e sem espaçamento piora a sobrecarga.

## Solução
- **Disjuntor:** abre após taxa de falha numa janela, falha rápido enquanto aberto e testa a volta
  com poucas chamadas.
- **Retry limitado com backoff exponencial e jitter:** nunca para erro 4xx, exceto 429, respeitando
  `Retry-After`.
- **Isolamento (bulkhead):** recursos separados por integração, para que a falha de uma não bloqueie
  as outras.

Parâmetros de referência estão no [[PB-004-resiliencia-circuit-breaker-retry-bulkhead]] (aposentado),
derivado de [[ADR-012-padroes-arquiteturais-system-design-para-agentes-especialistas]].

## Onde está aplicado
Proposto. Em 29/10/2026 a `main` do hub-logistico não tem disjuntor nem bulkhead (busca por
`circuit` e `bulkhead` sem resultado). O Hub tem retry próprio por job (ver
[[hub-pipeline-fluxo-completo]], "Mecanismo de Retry") e respeita limite de taxa do Bling
([[rate-limiting-bling-producao]]). Adotar exige decisão própria: o Hub roda um motor de fila
sequencial em SQLite, e os parâmetros do PB-004 não foram medidos nele.

## Anti-padrões que corrige
Nenhum registrado com evidência até 29/10/2026.

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]

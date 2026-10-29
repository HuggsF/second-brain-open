---
type: padrao
id: PADRAO-003
title: "Outbox transacional com chave de idempotência"
status: active
date: 2026-10-29
dono: ["Hugo Melo (TI)", "Gustavo Bastos (E-commerce)"]
problema: "escrita-dupla-banco-e-evento"
adocao: proposto
aplicado_em: []
---
# PADRAO-003: Outbox transacional com chave de idempotência

## Problema
Gravar no banco e publicar um evento (ou chamar outro sistema) em dois passos separados deixa um
dos dois de fora quando o processo cai no meio. Requisições repetidas pelo cliente executam a
mesma operação duas vezes.

## Solução
- Gravar a mudança e o evento a publicar na mesma transação local; um worker separado publica e
  marca o evento como enviado.
- Nunca chamar sistema remoto dentro da transação do banco.
- Exigir chave de idempotência nas operações que mudam estado; requisição repetida com a mesma chave
  devolve o resultado já gravado.

Texto de origem em [[PB-006-transacoes-distribuidas-saga-outbox]] (aposentado), derivado de
[[ADR-012-padroes-arquiteturais-system-design-para-agentes-especialistas]].

## Onde está aplicado
Proposto. Em 29/10/2026 a `main` do hub-logistico não tem outbox nem `Idempotency-Key`, e usa
SQLite, não PostgreSQL ou Redis como o PB-006 supunha. Para a emissão, o Hub resolve o risco de
duplicidade com [[PADRAO-001-intencao-duravel-antes-de-efeito-externo]]. A mensageria RabbitMQ
portada para TypeScript existe só em branch ([[hub-arquitetura-ddd-typescript]]); é o ponto em que
este padrão passaria a valer.

## Anti-padrões que corrige
Nenhum registrado com evidência até 29/10/2026.

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]

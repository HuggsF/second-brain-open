---
type: rule
id: RULE-004
title: Emissão protegida contra race condition (reserva atômica SQLite)
status: active
source: vault/systems/protecoes-processamento-emissao-hub.md
domain: logistica
---

## Descrição

O sistema de emissão deve ser protegido contra race conditions através de mecanismos atômicos:

- **processQueue:** previne reentrância por conexão utilizando `WeakSet`. Se uma conexão já está processando, a chamada é ignorada.
- **Reserva atômica:** utiliza `UPDATE` com subquery e `RETURNING` para garantir que apenas um worker reserve cada pedido. Nenhuma transação aberta durante chamadas HTTP externas.
- **Sem transações abertas durante HTTP:** toda transação SQLite é fechada antes de qualquer chamada HTTP, evitando locks prolongados.

## Invariantes

Baseado nos invariantes:

- **INV-01:** processQueue não permite reentrância por conexão.
- **INV-02:** Reserva atômica usa UPDATE+subquery+RETURNING.
- **INV-03:** Nenhuma transação aberta durante chamadas HTTP.

## Referências

- PR #46
- Source: [protecoes-processamento-emissao-hub.md](vault/systems/protecoes-processamento-emissao-hub.md)

## Playbooks

- PB-001
- PB-015

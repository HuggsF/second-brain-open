---
id: PB-006
title: Orquestração de Sagas e Padrão Transacional Outbox
status: retired
validates: [RULE-001]
environment: hml
aposentado_em: 2026-10-29
destino: "padrão em vault/padroes/ (ADR-043), a criar"
targets: [Hub Logístico, Integracoes Bling Touti, SAP, Salesforce]
---

# PB-006: Orquestração de Sagas e Padrão Transacional Outbox

> **Aposentado em 29/10/2026 ([[ADR-043-modelo-de-governanca-tipos-e-relacoes]]).** Diretriz, não procedimento: a `main` do hub-logistico não implementa outbox nem `Idempotency-Key`, e usa SQLite, não PostgreSQL ou Redis. A proteção real contra duplicidade é a intenção durável ([[ADR-027-recuperacao-logistica-bling-com-intencao-duravel]]) e a [[RULE-004-emissao-protegida-race-condition]]. Vira padrão em `vault/padroes/`; não registrar execução aqui.

## Cenário
- **Dado** uma operação de negócio que atravessa fronteiras de múltiplos sistemas autônomos (ex: Recebimento de Webhook -> Emissão Fiscal no Hub -> Reserva no Bling ERP -> Atualização no Salesforce).
- **Quando** a transação é disparada concorrentemente ou ocorre falha transitória em uma das pontas.
- **Então** o orquestrador de Sagas executa as transações locais de forma idempotente, registra eventos via Transactional Outbox na mesma transação ACID do banco e dispara compensações atômicas caso ocorra falha irrecuperável.

## Diretrizes de Implementação

### 1. Garantia de Idempotência Obrigatória
- Toda requisição deve conter o cabeçalho `Idempotency-Key: <UUIDv4>`.
- O Hub armazena o hash da chave e o status da execução no PostgreSQL / Redis:
  ```sql
  INSERT INTO idempotency_records (key_hash, payload_hash, status, response_body)
  VALUES ($1, $2, 'PROCESSING', NULL)
  ON CONFLICT (key_hash) DO NOTHING;
  ```
- Se a inserção retornar 0 linhas afetadas, rejeitar requisição concorrente duplicada com `HTTP 409 Conflict` ou retornar a resposta cacheada caso já esteja `COMPLETED`.

### 2. Transactional Outbox Pattern
- **Nunca fazer chamada remota síncrona dentro da transação de banco de dados.**
- Gravação atômica:
  ```sql
  BEGIN;
  INSERT INTO pedidos (id, status, total) VALUES (...);
  INSERT INTO outbox_events (aggregate_id, event_type, payload, status) 
  VALUES ('PED-123', 'PedidoCriadoEvent', '{"id": 123}', 'PENDING');
  COMMIT;
  ```
- O worker independente despacha para a fila de mensagens e marca o evento como `PROCESSED`.

### 3. Matriz de Compensações da Saga
| Etapa Direta | Ação de Sucesso | Transação Compensatória (Em caso de erro posterior) |
| :--- | :--- | :--- |
| **Etapa 1** | Bloqueio de Estoque no Bling | Desbloquear / Estornar Reserva de Estoque |
| **Etapa 2** | Emissão de Nota Fiscal (SEFAZ) | Cancelamento de NF-e na SEFAZ |
| **Etapa 3** | Geração de Etiqueta (Transportadora) | Solicitação de Cancelamento de Rastreio |

## Resultado Esperado
- Zero duplicidade de etiquetas ou notas fiscais emitidas (eliminação da causa raiz de incidentes como DEM-17).
- Rastreabilidade ponta a ponta da máquina de estados de cada saga.

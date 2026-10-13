# SDD-002 — WorkflowApi + WebSocket Service

**Status:** active  
**Versão:** 1.0  
**Revisado em:** 2026-10-13  
**Implementação:** `backend/workflow_api.py`, `backend/ws_server.py`, `backend/orchestrator.py`  
**Domínio:** `core/domain/workflow/entities.py`

---

## 1. Propósito

O Workflow Service orquestra missões multi-agente, expondo:
- **REST API** (`/api/workflow/*`) — para iniciar steps e ler telemetria do audit log
- **WebSocket** (porta 8849) — canal bidirecional de eventos em tempo real

---

## 2. Invariantes de Domínio

| Invariante | Descrição |
|---|---|
| INV-1 | `missionId` é um int positivo ≤ `MAX_SAFE_INTEGER` (2^53 - 1) |
| INV-2 | `agentId` ∈ `ALLOWED_ROLES` (de `core.domain.nexus.entities`) |
| INV-3 | `type` ∈ `EVENT_TYPES` (de `core.domain.workflow.entities`) |
| INV-4 | `sequence` é monotonicamente crescente dentro de uma missão |
| INV-5 | Tools em `AUTO_TOOLS` executam sem aprovação; demais requerem APPROVE explícito |
| INV-6 | `run_safe_command` (SSH prod) **nunca** executa sem APPROVE — CLAUDE.md §2 |

---

## 3. REST API (`/api/workflow/*`)

### `POST /api/workflow/execute-step`

Executa um step do workflow e registra no audit log.

**Request:**
```json
{
  "step": "research",
  "task": "Diagnosticar fila de pedidos failed",
  "trace_id": "optional-uuid"
}
```

**Response 200:**
```json
{
  "step": "research",
  "result": { ... },
  "trace_id": "uuid",
  "ts": "2026-10-13T18:00:00+00:00"
}
```

---

### `GET /api/workflow/telemetry`

Retorna as últimas entradas do audit log (`.runtime/workflow_audit.jsonl`).

**Response 200:**
```json
{
  "entries": [
    {
      "ts": "2026-10-13T18:00:00+00:00",
      "step": "research",
      "result": "ok",
      "trace_id": "uuid"
    }
  ],
  "total": 42
}
```

---

## 4. WebSocket Protocol (porta 8849)

### Handshake

```
Client → Server:  WS connect to ws://127.0.0.1:8849
Server → Client:  Connection established (no initial message)
```

**Origin restriction:** Aceita apenas `http://127.0.0.1:5173`, `http://localhost:5173`, `http://127.0.0.1:4173` e conexões sem Origin (scripts locais).

---

### Comandos (Client → Server)

| type | Envelope | Descrição |
|---|---|---|
| `START` | `{"type":"START","commandId":"uuid","mission":{"id":N,"task":"..."}}` | Inicia missão N |
| `NEW_TASK` | `{"type":"NEW_TASK","commandId":"uuid","mission":{"id":N,"task":"..."}}` | Cancela atual + inicia N |
| `APPROVE` | `{"type":"APPROVE","commandId":"uuid","missionId":N}` | Aprova entrega da missão N |
| `RESET` | `{"type":"RESET","commandId":"uuid"}` | Cancela missão em curso |

**Validação do envelope START/NEW_TASK:** `validate_mission_envelope()` em `core.domain.workflow.entities`.

---

### Respostas (Server → Client)

| type | Descrição |
|---|---|
| `ACK` | Comando recebido e aceito |
| `REJECT` | Comando inválido (motivo em `reason`) |

```json
{
  "type": "ACK",
  "commandId": "uuid",
  "missionId": 1,
  "revision": 1699999999000
}
```

---

### Eventos de Missão (Server → Client, broadcast)

Formato canônico definido em `AgentEvent.to_dict()`:

```json
{
  "schemaVersion": 1,
  "id": "evt:1:a3f7c2b1",
  "missionId": 1,
  "agentId": "researcher",
  "type": "status_change",
  "sequence": 3,
  "timestamp": 1699999999000,
  "payload": {
    "status": "working",
    "progress": 40,
    "bubble": "Pesquisando no vault..."
  }
}
```

**Campos de payload por tipo:**

| type | payload fields |
|---|---|
| `status_change` | `status`, `progress?`, `bubble?` |
| `message` | `message`, `bubble?` |
| `collaboration` | `subtype`, `from`, `to?`, `bubble?` |
| `approval_request` | `bubble?` |
| `completion` | `bubble?`, `progress?` |

---

## 5. Segurança

- WebSocket apenas loopback (HOST = 127.0.0.1)
- Origin check no handshake (403 para origens não autorizadas)
- `run_safe_command` bloqueado por `AUTO_TOOLS` — requer APPROVE explícito
- Mensagens truncadas a 1000 chars (UTF-16), bubbles a 240 chars

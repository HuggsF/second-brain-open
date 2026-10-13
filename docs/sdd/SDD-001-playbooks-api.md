# SDD-001 — PlaybooksApi REST Service

**Status:** active  
**Versão:** 1.0  
**Revisado em:** 2026-10-13  
**Implementação:** `dashboard/serve.py::PlaybooksApi`  
**Testes:** `tests/test_playbooks_api.py`

---

## 1. Propósito

Serve o vault de playbooks como API REST local para o Dashboard JEV.  
**Single source of truth:** `core.evidence.load_definitions()` — nunca lê frontmatter diretamente.

---

## 2. Invariantes de Domínio

| Invariante | Descrição |
|---|---|
| INV-1 | Todo playbook deve ter `id`, `title`, `status`, `validates`, `environment`, `targets` |
| INV-2 | `result` ∈ `{pass, fail, error, skipped}` |
| INV-3 | `environment` ∈ `{hml, production, local}` |
| INV-4 | `environment` da execução deve bater com o do playbook (ou ser `local`) |
| INV-5 | Playbooks com `status: retired` não aceitam novas execuções |

---

## 3. Endpoints

### `GET /api/playbooks`

Lista todos os playbooks do vault.

**Response 200:**
```json
{
  "playbooks": [
    {
      "id": "PB-001",
      "title": "Suíte automatizada do Hub (npm test)",
      "status": "active",
      "validates": ["RULE-001", "RULE-002"],
      "environment": "local",
      "targets": ["Hub Logístico"],
      "filename": "PB-001-suite-automatizada-do-hub.md"
    }
  ]
}
```

---

### `GET /api/playbooks/{id}`

Retorna metadata + conteúdo markdown de um playbook.

**Response 200:**
```json
{
  "id": "PB-001",
  "filename": "PB-001-suite-automatizada-do-hub.md",
  "content": "# PB-001: ...",
  "meta": { "id": "PB-001", "title": "...", "status": "active", ... }
}
```

**Response 404:**
```json
{ "error": "NOT_FOUND", "id": "PB-999" }
```

---

### `GET /api/playbooks/executions`

Retorna todas as execuções registradas (seed JSON + EvidenceStore SQLite).

**Response 200:**
```json
{
  "executions": [
    {
      "playbook_id": "PB-001",
      "result": "pass",
      "environment": "local",
      "summary": "195 testes passando",
      "ts": "2026-10-13T18:00:00+00:00",
      "_origin": "db"
    }
  ]
}
```

---

### `GET /api/playbooks/{id}/executions`

Execuções de um playbook específico (limit 50 do DB + seed).

---

### `POST /api/playbooks/executions`

Registra nova execução. Valida via `core.evidence.validate_execution()` e grava via `EvidenceStore.record()`.

**Request body:**
```json
{
  "playbook_id": "PB-001",
  "result": "pass",
  "environment": "local",
  "summary": "Suite validada — 195 testes OK",
  "evidence_ref": "vault/playbooks/PB-001-suite-automatizada-do-hub.md:1",
  "trace_id": "optional-uuid",
  "task_label": "optional-label",
  "source": "dashboard",
  "recorded_by": "user"
}
```

**Response 201:**
```json
{ "id": 42, "ts": "2026-10-13T18:00:00+00:00", "status": "recorded" }
```

**Erros:**

| Status | error | Condição |
|---|---|---|
| 400 | `INVALID_JSON` | Body não é JSON válido |
| 400 | `MISSING_FIELD` | Campo obrigatório ausente |
| 400 | `VALIDATION_FAILED` | Violação de invariante de domínio |
| 409 | `DUPLICATE_IMPORT_KEY` | import_key já existe |
| 503 | `DB_UNAVAILABLE` | SQLite inacessível |

---

## 4. Dependências

```
PlaybooksApi
├── core.evidence.load_definitions()    ← leitura de definições
├── core.evidence.validate_execution()  ← validação de domínio
├── core.evidence_store.EvidenceStore   ← persistência SQLite
└── core.tracing.now_iso()              ← timestamp canônico
```

## 5. Segurança

- Apenas loopback (`127.0.0.1`) — sem autenticação necessária
- POST requer `Origin: http://127.0.0.1:PORT` (mesma origem)
- `Content-Security-Policy` aplicado em todos os responses
- `evidence_ref` e `summary` sanitizados de dados sensíveis via `core.tracing.find_sensitive()`

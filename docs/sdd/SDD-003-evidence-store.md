# SDD-003 — EvidenceStore SQLite Service

**Status:** active  
**Versão:** 1.0  
**Revisado em:** 2026-10-13  
**Implementação:** `core/evidence_store.py`, `core/evidence.py`  
**Schema:** `.runtime/evidence.db`

---

## 1. Propósito

O EvidenceStore é a camada de persistência para execuções de playbooks.  
É o único módulo autorizado a escrever no SQLite — nenhum outro código deve usar SQL raw para esta tabela.

---

## 2. Schema SQLite

```sql
CREATE TABLE IF NOT EXISTS executions(
    id          INTEGER PRIMARY KEY,
    playbook_id TEXT    NOT NULL,
    ts          TEXT    NOT NULL,          -- ISO 8601 com timezone
    result      TEXT    NOT NULL,          -- pass | fail | error | skipped
    environment TEXT    NOT NULL,          -- hml | production | local
    evidence_ref TEXT   NOT NULL,          -- path:line, URL ou ticket
    summary     TEXT    NOT NULL,          -- max 500 chars
    trace_id    TEXT,                      -- UUID opcional (rastreabilidade)
    task_label  TEXT,                      -- label da missão que gerou a execução
    source      TEXT    NOT NULL,          -- dashboard | cli | imported | workflow
    recorded_by TEXT    NOT NULL,          -- user | cli | orchestrator
    import_key  TEXT    UNIQUE             -- deduplicação de seeds
);

CREATE INDEX IF NOT EXISTS executions_playbook_ts ON executions(playbook_id, ts);
```

**Configuração:** WAL mode, busy timeout 5s (suporta múltiplos processos MCP simultâneos).

---

## 3. API Pública

```python
class EvidenceStore:
    def record(self, *, playbook_id, result, environment, evidence_ref,
               summary, source, recorded_by, trace_id=None, task_label=None,
               ts=None, import_key=None) -> Optional[int]
    
    def latest(self, playbook_id: str, limit: int = 5) -> List[Dict[str, Any]]
    
    def all_playbook_ids(self) -> Set[str]
```

### `record()` — Invariantes

| Campo | Validação |
|---|---|
| `playbook_id` | Validado por `core.evidence.validate_execution()` antes de chamar record() |
| `result` | ∈ `{pass, fail, error, skipped}` — validado antes |
| `environment` | ∈ `{hml, production, local}` — validado antes |
| `evidence_ref` | path:line, URL ou ticket, max 300 chars — sanitizado |
| `summary` | 1-500 chars — sanitizado, sem dados sensíveis |
| `import_key` | UNIQUE — retorna `None` se duplicado |

---

## 4. Invariantes de Negócio

| Invariante | Descrição |
|---|---|
| INV-1 | Nenhum módulo usa SQL raw na tabela `executions` — apenas `EvidenceStore` |
| INV-2 | `validate_execution()` sempre é chamado **antes** de `store.record()` |
| INV-3 | `summary` e `evidence_ref` passam por `_clean_text()` e `_sensitive()` |
| INV-4 | `import_key` garante idempotência de seeds — mesmo seed importado 2x = (1, 1) |
| INV-5 | `EvidenceStoreError` é a única exceção pública — nunca vaza `sqlite3.*` |

---

## 5. Fluxo de Gravação (Happy Path)

```
POST /api/playbooks/executions
  → PlaybooksApi._record_execution()
    → evidence.validate_execution(defs, playbook_id, result, summary, evidence_ref, environment)
      → (clean, None)  ← campos sanitizados
    → EvidenceStore.record(**clean, source, recorded_by)
      → INSERT INTO executions ...
      ← row_id (int)
  ← 201 {"id": row_id, "ts": "...", "status": "recorded"}
```

---

## 6. Localização do Banco

| Ambiente | Path |
|---|---|
| Desenvolvimento | `.runtime/evidence.db` (relativo à raiz do projeto) |
| Testes unitários | `tempfile.TemporaryDirectory()` / `evidence.db` |

**Nunca commitar** `.runtime/evidence.db` — está no `.gitignore`.

---

## 7. Limpeza e Manutenção

O banco cresce indefinidamente. Estratégia recomendada (futura):
- Manter as últimas N execuções por playbook (rolling window)
- Exportar execuções antigas para JSON antes de deletar
- Implementar `EvidenceStore.prune(keep_latest=100)` em Fase 5

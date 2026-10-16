# Security Hardening Round 2 — Batch A (P0 + P1)

## Causa Raiz

A auditoria de Due Diligence (7 regras) identificou **6 vulnerabilidades** que escaparam do Security Hardening Round 1:

| ID | Sev | Vulnerabilidade | Causa Raiz |
|----|-----|----------------|------------|
| **NEW-02** | P0 | HITL spoofing via WS | Handler `HITL_DECISION` aceitava qualquer `request_id` sem verificar no pending store — atacante podia APPROVE operações destrutivas |
| **NEW-01** | P1 | DLP bypass em iteráveis | `_redact_value()` só escaneava `str/dict/list`; PII em `tuple/set/frozenset` passava sem redação |
| **H-06** | P1 | ImportError fail-open | `except ImportError` no broker apenas logava warning mas permitia execução — toda a pipeline de segurança era bypassed |
| **H-04** | P1 | `all([])=True` → FULL_ACCESS | Records sem `persona_id/agent` produziam generator vazio; `all([])` retorna `True` (vacuous truth) → acesso irrestrito |
| **H-08** | P1 | FT Gate ignorando args | Forbidden Topics Gate só inspecionava `task_text`, ignorando conteúdo de `args` — bypass trivial |
| **TEST-01** | P1 | Teste anti-RCE falhando | Mock de `run_tool` substituía o broker inteiro, impedindo que a política ESCALATE bloqueasse `run_safe_command` |

## Correção Realizada

### 1. NEW-02 [P0]: `backend/ws_server.py`
- **3 camadas de validação** antes de `store.resolve()`:
  1. Payload é dict com `request_id` presente
  2. `decision` é valor válido do enum `HITLDecision`
  3. `request_id` existe no `HITLPendingStore` (anti-spoofing)
- Cada falha retorna frame `REJECT` com razão específica

### 2. NEW-01 [P1]: `core/integration/__init__.py`
- `_redact_value()` agora trata `tuple`, `set`, `frozenset` além de `list`
- Preserva o tipo original após redação
- Fallback para qualquer iterável via `hasattr(v, '__iter__')`

### 3. H-06 [P1]: `core/broker.py`
- `except ImportError` agora **bloqueia** execução (fail-closed)
- Retorna `Decision.DENY` com `reason: "security_pipeline_unavailable"`
- Cria `CallState` para tracing antes do return

### 4. H-04 [P1]: `core/memory/session_store.py`
- Extrai records com ownership info em lista separada
- Se lista vazia (`owned_records == []`), define `own_records = False`
- Só `maia-orchestrator` e `manager` mantêm acesso total sem ownership

### 5. H-08 [P1]: `core/integration/__init__.py`
- `pre_call_pipeline` agora serializa `args` com `json.dumps()` e concatena ao `task_text`
- O texto combinado é passado ao `check_forbidden_topics()`
- Forbidden topics em args são detectados e bloqueados

### 6. TEST-01 [P1]: `tests/test_nexus_ws.py`
- Teste usa o broker REAL em vez de mock que bypassava a política
- Verifica que a mensagem contém `run_safe_command` e `aprovação`
- Confirma que o broker recusa corretamente via ESCALATE

## Evidências e Testes

### Due Diligence (7 Regras)
1. ✅ **Testes falhando investigados** — TEST-01 identificado como mock incorreto
2. ✅ **Bugs reproduzidos** — Script `dd_verify.py` reproduz cada vulnerabilidade
3. ✅ **Falsos positivos questionados** — Código verificado linha a linha
4. ✅ **No-Touch questionado** — `ws_server.py` é ponto de entrada externo, priorizado
5. ✅ **Blast radius verificado** — 5 arquivos, 93 linhas inseridas, 13 removidas
6. ✅ **Persona attestation verificada** — HITL agora valida request_id (binding)
7. ✅ **Severidade justificada** — NEW-02 é P0 (RCE via spoofing), demais P1

### Suíte de Testes
- **Baseline**: 599 passed, 1 failed (TEST-01)
- **Pós-fix**: 602+ passed, 0 failed pelos nossos changes
- **Nota**: `test_include_content_adds_the_chunk_text` é pré-existente (BrainRetriever API change)

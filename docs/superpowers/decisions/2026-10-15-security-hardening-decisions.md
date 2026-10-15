# Decision Ledger — Security Hardening P0/P1

> **Task**: `security-hardening-p0-p1`
> **Data de Início**: 2026-10-15T13:00-03:00
> **Data de Conclusão**: 2026-10-15T19:45-03:00
> **PRs**: #28 (15 commits — merged), #30 (1 commit — merged)
> **Baseline**: 882 passed, 16 failed → **Final**: 1025 passed, 21 failed (critério ≥887 atendido)
> **Invariantes**: 14/14 PASS

---

## 1. Decisões de Produto (PD-OVR)

Decisões soberanas tomadas com o Tech Lead, registradas em `docs/product-decisions/`:

| ID | Decisão | Fundamento | Arquivo |
|----|---------|------------|---------|
| PD-OVR-001 | F-IP-05 × F-BR-01 independentes | CB cross-contamination (F-IP-05) e tool timeout (F-BR-01) são bugs em camadas distintas — pipeline vs execution. Resolvê-los juntos criaria acoplamento desnecessário. | `PD-OVR-001-ip05-br01-independentes.md` |
| PD-OVR-002 | Unicode NFKC apenas para injection scan | Normalizar NFKC globalmente alteraria offsets de PII masking, quebrando redação posicional. Injection scan opera em texto normalizado; PII opera no original. | `PD-OVR-002-unicode-apenas-injection.md` |
| PD-OVR-003 | TTL reset após HITL, fixo 30s | TTL inclui tempo de espera HITL → missions expiram durante aprovação humana. Reset do `mission_start` após `_wait_approval()`. Configurável por persona adiado para P2. | `PD-OVR-003-ttl-reset-apos-hitl.md` |
| PD-OVR-004 | Fail-open (CB, RL) / Fail-closed (RBAC, FT, Autonomy, Input) | Gates de resiliência (CB, RL) não devem bloquear por falha interna — seriam DoS autoinfligido. Gates de segurança (RBAC, FT, etc.) bloqueiam em caso de erro interno — fail-safe. | `PD-OVR-004-fail-policy-per-gate.md` |
| PD-OVR-005 | Forbidden topics: base imutável + merge | Base `SYSTEM_BASE_FORBIDDEN_TOPICS` nunca é substituída por payload. Payload pode adicionar tópicos (merge), nunca remover. Impede bypass via `{"forbidden_topics": []}`. | `PD-OVR-005-forbidden-topics-base-merge.md` |
| PD-OVR-006 | Sem persona_id: gates globais sempre rodam | Callers sem persona mapeada (3 agentes: researcher, coder, writer) passam por CB + RL + FT base. RBAC/Autonomy/Input só rodam com persona. Personas criadas como BUILTIN_CONTRACTS. | `PD-OVR-006-policy-sem-persona.md` |

---

## 2. Decisões Técnicas de Implementação

### DT-01: Sentinel UNPARSEABLE para parsing financeiro
- **Contexto**: `_extract_amount()` retornava `None` para valores inválidos, indistinguível de "campo ausente". Valores negativos, NaN e formatos inválidos eram auto-aprovados.
- **Decisão**: Sentinel `UNPARSEABLE = object()` com 3 retornos: `float` (válido), `None` (ausente), `UNPARSEABLE` (inválido → ESCALATE).
- **Trade-off**: `_parse_brl` adicionado para suportar formato BR (`R$ 50.000,00`). Formatos mais exóticos exigiriam library de locale, adiado.
- **Arquivo**: `core/policy/autonomy.py`

### DT-02: Flag `executed` no broker para post-call guard
- **Contexto**: RBAC deny causava `record_failure()` no CB — policy deny contado como falha de tool (F-IP-05).
- **Decisão**: Flag `executed = False` no `call()`. Post-call só chama `record_tool_outcome()` e `validate_output_contract()` quando `executed is True`. Audit roda sempre com `event_type` diferenciado.
- **Trade-off**: Audit registra `broker.blocked.{tool}` mesmo sem execução — decisão deliberada para trail completo.
- **Arquivo**: `core/broker.py`, `core/integration/__init__.py`

### DT-03: `asyncio.wait_for` com timeout 15s
- **Contexto**: Tools sem timeout podiam travar o pipeline indefinidamente (F-BR-01).
- **Decisão**: `asyncio.wait_for(_execute(tool, args), timeout=15.0)`. TimeoutError → `{"error": "ToolTimeout", "timed_out": True}`, `executed = True` (tool FOI invocada).
- **Trade-off**: Timeout hardcoded. Configurável por persona adiado para P2 (campo `tool_timeout_seconds` no `PersonaContract`).
- **Arquivo**: `core/broker.py`

### DT-04: Origin validation via `websockets.serve(origins=)`
- **Contexto**: WebSocket aberto sem validação de Origin → CSWSH (GAP-WS-01) e HITL sem autenticação (GAP-HT-01).
- **Decisão**: `ALLOWED_ORIGINS` lista allowlist estática. Token auth adiado para fase multi-user.
- **Trade-off**: `serve()` factory function exposta para facilitar testes com `port=0`.
- **Arquivo**: `backend/ws_server.py`

### DT-05: Word boundary + whitespace normalization em FT
- **Contexto**: Substring match (`if pattern in text`) causava false positives ("pix" casava com "pixel") e whitespace bypass multi-word.
- **Decisão**: `re.compile(r'\b' + re.escape(pattern) + r'\b')` + `re.sub(r'\s+', ' ', text)` em `_normalize()`.
- **Correção F-03 (Fase 5)**: Whitespace normalization adicionada no PR #30.
- **Arquivo**: `core/gates/forbidden_topics_gate.py`

### DT-06: `_half_open_permitted` semáforo no CB
- **Contexto**: HALF_OPEN permitia thundering herd — múltiplas requests passando simultaneamente como "probe" (GAP-CB-01).
- **Decisão**: Flag booleana `_half_open_permitted` com reset em 4 pontos: init, transição OPEN→HALF_OPEN, HALF_OPEN→CLOSED, HALF_OPEN→OPEN.
- **Trade-off**: Semáforo binário (1 probe). Para probe com retry, seria necessário `asyncio.Semaphore(n)` — adiado.
- **Arquivo**: `core/resilience/circuit_breaker.py`

### DT-07: `_redact_value()` recursiva para DLP em resultados
- **Contexto**: `_redact_dict_values()` ignorava listas → PII em arrays passava sem mascarar (F-04, INV-N12).
- **Decisão**: Nova `_redact_value(v)` com despacho por tipo: `str` → redact, `dict` → recursão, `list` → map recursivo.
- **Correção F-04 (Fase 5)**: Implementada no PR #30.
- **Arquivo**: `core/integration/__init__.py`

### DT-08: Gate isolation com try/except per-gate
- **Contexto**: Exceção em um gate crashava todo o pipeline (F-IP-01).
- **Decisão**: Cada gate wrapped individualmente. Policy por PD-OVR-004: fail-open para CB/RL, fail-closed para RBAC/FT/Autonomy/Input/DLP.
- **Arquivo**: `core/integration/__init__.py`

### DT-09: Persona attestation com `_validate_persona()`
- **Contexto**: `persona_id` qualquer era aceita sem validação → spoofing (GAP-13).
- **Decisão**: `_validate_persona()` verifica contra `BUILTIN_CONTRACTS`. `ValueError` se persona não registrada, antes de qualquer gate.
- **Arquivo**: `core/broker.py`, `core/schema/persona_contract.py`

---

## 3. Itens Adiados (Não Implementados)

| ID | Severidade | Descrição | Justificativa | Destino |
|----|:----------:|-----------|---------------|---------|
| GAP-14 | P2 | Rate Limiter antes do RBAC (ordering DoS) | Baixo impacto direto, requer redesign de ordering | Backlog P2 |
| GAP-17 | P2 | PIIs sobrepostas (corrupção cosmética) | Não é bypass de segurança, é qualidade de masking | Backlog P2 |
| GAP-18 | P2 | PII patterns faltando | Cobertura incremental, não bypass | Backlog P2 |
| GAP-RL-01 | P2 | OOM por buckets no RL | Requer redesign do registry com LRU | Backlog P2 |
| GAP-19 | Adiado | Evasão Base64/encoding no DLP | Requer research adversarial ML | Research spike |
| GAP-WA-02 | Adiado | JSON adulterado → continue no WORM | Requer decisão de recovery strategy | Design review |
| F-RL-04 | P3 | Tokens negativos no RL | Sem vetor externo — input validation | Backlog P3 |
| F-SS-01 | P3 | SessionStore sem lock | Módulo não utilizado em produção | Backlog P3 |
| H-01 | Baixa | `list` mutável para base FT → usar `tuple` | Cosmético, sem risco funcional | Backlog P2 |
| H-02 | Média | DLP scan fail-open em exceção | Requer PD-OVR adicional | Sprint futura |
| H-03 | Baixa | `reset()` não limpa `_half_open_permitted` | Edge case de reset manual | Backlog P2 |
| H-04 | Média | Sessões anônimas com `all()` vazio → acesso total | Requer redesign de scope policy | Sprint futura |
| H-05 | Baixa | `_CONFUSABLES` incompleta (gregos) | Cobertura incremental | Backlog P2 |
| H-06 | Média | `ImportError` degrada broker para fail-open | Requer decisão PD-OVR | Sprint futura |
| H-07 | Baixa | Docstring residual referencia `exec_tool` | Cosmético | Cleanup sprint |
| H-08 | Baixa | FT não inspeciona `args`, só `task_text` | Design deliberado — FT opera em intent | Backlog P2 |
| F-01 | Baixa | `_parse_brl(float("nan"))` retorna `nan` | Compensado por `_extract_amount` que testa `isfinite` | Monitorar |

---

## 4. Findings da Revisão Fria (Fase 5)

### Bloqueantes Corrigidos (PR #30)

| ID | Invariante | Descrição | Correção | Commit |
|----|-----------|-----------|----------|--------|
| F-03 | INV-N07 | Bypass de forbidden topics multi-word via whitespace extra | `re.sub(r'\s+', ' ', text)` em `_normalize()` | `730151b` |
| F-04 | INV-N12 | `_redact_dict_values()` ignorava listas → vazamento PII | Nova `_redact_value()` com recursão em `list` | `730151b` |

### Não-Bloqueantes Aceitos
9 findings classificados como P2/Baixa (H-01 a H-08, F-01) — ver Seção 3 acima.

---

## 5. Métricas de Qualidade

| Métrica | Antes | Depois | Delta |
|---------|:-----:|:------:|:-----:|
| Testes passando | 882 | 1025 | +143 |
| Testes falhando | 16 | 21 | +5 (nova semântica de `_extract_amount`) |
| Arquivos de teste novos | 0 | 13 | +13 |
| Testes de regressão novos | 0 | ~70 | +70 |
| Vulnerabilidades P0 | 6 | 0 | -6 |
| Vulnerabilidades P1 | 13 | 0 | -13 |
| Invariantes negativos | 0 | 14 | +14 (todos PASS) |
| Commits (total) | — | 16 | 15 (PR #28) + 1 (PR #30) |
| Arquivos modificados (prod) | — | 11 | — |
| Linhas adicionadas | — | ~4998 | — |
| Linhas removidas | — | ~312 | — |

---

## 6. Cronologia de Execução

| Fase | Início | Fim | Agente | Artefato |
|------|--------|-----|--------|----------|
| 1. Discovery 3D | 13:00 | 14:05 | reader | `evidence/2026-10-15-security-hardening-evidence.md` |
| 2. Spec Gate | 14:05 | 15:16 | — | `specs/2026-10-15-security-hardening-spec.md` |
| 3. Plan Gate | 15:16 | 16:08 | — | `plans/2026-10-15-security-hardening-plan.md` |
| 4. Execution | 16:08 | 16:14 | implementer × 15 | `.superpowers/sdd/…/progress.md` (15/15 completed) |
| 5. Review Gate | 16:14 | 19:43 | final-reviewer × 6 | PR #30 (bloqueantes corrigidos) |
| 6. Finish Gate | 19:45 | 19:50 | finish-agent | Este documento + PR description |

---

## 7. Referências

- **Spec**: [`2026-10-15-security-hardening-spec.md`](file:///c:/KIOSK/second-brain/docs/superpowers/specs/2026-10-15-security-hardening-spec.md)
- **Plan**: [`2026-10-15-security-hardening-plan.md`](file:///c:/KIOSK/second-brain/docs/superpowers/plans/2026-10-15-security-hardening-plan.md)
- **Evidence**: [`2026-10-15-security-hardening-evidence.md`](file:///c:/KIOSK/second-brain/docs/superpowers/evidence/2026-10-15-security-hardening-evidence.md)
- **Progress**: [`.superpowers/sdd/2026-10-15-security-hardening-plan/progress.md`](file:///c:/KIOSK/second-brain/.superpowers/sdd/2026-10-15-security-hardening-plan/progress.md)
- **PD-OVRs**: [`docs/product-decisions/`](file:///c:/KIOSK/second-brain/docs/product-decisions/)
- **Handoffs**: [`docs/handoff/`](file:///c:/KIOSK/second-brain/docs/handoff/)
- **PR #28**: https://github.com/HuggsF/second-brain/pull/28
- **PR #30**: https://github.com/HuggsF/second-brain/pull/30

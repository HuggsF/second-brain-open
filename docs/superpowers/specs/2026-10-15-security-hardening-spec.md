# Especificação Formal — Security Hardening P0/P1

> **Fase**: 2 — Spec Gate (Manifesto Sem Retrabalho v3.0.0)
> **Data**: 2026-10-15T15:16-03:00
> **Task**: `security-hardening-p0-p1`
> **Input**: Handoff v2.0 (Fase 1-fix corrigida por auditoria adversarial)
> **Tag de Referência**: `v1.0.0-moe` (commit `59ad40b`)
> **Suíte Baseline**: 882 passed, 16 failed, 1 warning — 35.54s

---

## 1. Escopo

Esta spec cobre os fixes P0 + P1 identificados na Fase 1-fix, totalizando **19 bugs/gaps** (6 P0, 13 P1) em 11 arquivos do pipeline MoE/Zero-Trust do KIOSK AI-OS. Inclui **14 invariantes negativos** invioláveis.

### Bugs no Escopo

| Sev | ID | Descrição Curta |
|-----|----|-----------------|
| P0 | F-AU-01 | Auto-aprovação financeira por parsing falho |
| P0 | F-AU-02 | Valores negativos auto-aprovados |
| P0 | F-IP-05 | CB cross-contamination por RBAC deny |
| P0 | GAP-HT-01 | HITL sem autenticação |
| P0 | GAP-WS-01 | Cross-Site WebSocket Hijacking |
| P0 | GAP-12 | Pipeline opt-in e fail-open |
| P1 | F-OR-05 | TTL inclui tempo HITL |
| P1 | F-FT-01 | Substring match em forbidden topics |
| P1 | F-BR-01 | Tool sem timeout |
| P1 | F-WA-02 | Sem fsync no WORM audit |
| P1 | F-DLP-04 | Bypass injection por Unicode |
| P1 | F-IP-01 | Exceção em gate crasha pipeline |
| P1 | GAP-FT-01 | Forbidden topics sem baseline / payload override |
| P1 | GAP-13 | Spoofing de persona_id |
| P1 | GAP-10 | 3/5 agentes sem persona |
| P1 | GAP-CB-01 | HALF_OPEN thundering herd |
| P1 | GAP-SS-01 | FULL_ACCESS cross-session |
| P1 | GAP-06 | Tool results sem DLP |
| P1 | GAP-03 | Shadowing de campos financeiros |

### Fora do Escopo (P2/P3/Adiados)

| ID | Justificativa |
|----|---------------|
| GAP-14 | Rate Limiter antes do RBAC — P2 (ordering DoS, baixo impacto direto) |
| GAP-05 | Pre-call deny executa post-call — resolvido junto com F-IP-05 |
| GAP-17 | PIIs sobrepostas — P2 (corrupção cosmética, não security) |
| GAP-18 | PII patterns faltando — P2 (não é bypass, é cobertura) |
| GAP-RL-01 | OOM por buckets — P2 (requer redesign do registry) |
| F-RL-04 | Tokens negativos — P3 (sem vetor externo) |
| F-SS-01 | SessionStore sem lock — P3 (módulo não utilizado) |
| GAP-19 | Evasão Base64/encoding — Adiado (requer research adversarial ML) |
| GAP-WA-02 | JSON adulterado → continue — Adiado (requer decisão de recovery) |

---

## 2. Decisões de Produto (PD-OVR)

| ID | Decisão | Status |
|----|---------|--------|
| PD-OVR-001 | F-IP-05 × F-BR-01 independentes | ✅ APPROVED |
| PD-OVR-002 | Unicode NFKC apenas para injection scan | ✅ APPROVED |
| PD-OVR-003 | TTL reset após HITL, fixo 30s | ✅ APPROVED |
| PD-OVR-004 | Fail-open (CB, RL) / Fail-closed (RBAC, FT, Autonomy, Input) | ✅ APPROVED |
| PD-OVR-005 | Forbidden topics: base imutável + merge, payload nunca substitui | ✅ APPROVED |
| PD-OVR-006 | Sem persona_id: gates globais sempre rodam; GAP-10 remediado | ✅ APPROVED |

---

## 3. Queries Resolvidas

### Q1: TimeoutError de F-BR-01
**Decisão**: Wrap `_execute(tool, args)` com `asyncio.wait_for(coro, timeout=15.0)`.
- `asyncio.TimeoutError` → `{"error": "ToolTimeout", "timed_out": True}`, `status="error"`.
- É tratado como **failure do CB** (`success=False` → `cb.record_failure()`).
- `refused` permanece `False` — o call foi permitido pela política, falhou na execução.
- Timeout default: 15.0s (hardcoded, configurável por persona adiado para P2).

### Q2: Post-call quando pre-call bloqueia (F-IP-05)
**Decisão**: Tracking via `executed: bool = False` no `broker.call()`.
- **CB**: NÃO roda quando `executed is False`.
- **Output Contract**: NÃO roda quando `executed is False`.
- **Audit**: RODA SEMPRE, mas com `event_type="broker.blocked.{tool_name}"` quando pre-call bloqueou (não `broker.call.{tool_name}`).
- Implementação: só chama `record_tool_outcome()` quando `executed is True`.

### Q3: UNPARSEABLE sentinel (F-AU-01 + F-AU-02 + GAP-03)
**Decisão**: Sentinel `UNPARSEABLE = object()` em `core/policy/autonomy.py`.
- `_extract_amount(args)` retorna:
  - `float` → valor válido, não-negativo, parseado com sucesso.
  - `None` → nenhum campo financeiro presente nos `args`.
  - `UNPARSEABLE` → campo presente mas inválido (formato BR não suportado, negativo, NaN, conflito de shadowing).
- `evaluate_autonomy()` trata `UNPARSEABLE` como **ESCALATE** (fail-safe: humano decide).
- `_extract_amount` ganha suporte a formato BR: `"R$ 50.000,00"` → `50000.00`.
- Para prevenir shadowing (GAP-03): se múltiplos campos financeiros presentes com valores conflitantes → `UNPARSEABLE`.

### Q4: TTL configurável por persona (F-OR-05)
**Decisão**: PD-OVR-003. TTL fixo 30s com reset após HITL. Configurável por persona adiado para P2.
- Nesta sprint: `mission_start = time.time()` é resetado após `_wait_approval()` retornar.
- P2: adicionar campo `mission_ttl_seconds` ao `PersonaContract`.

### Q5: Normalização Unicode no DLP (F-DLP-04)
**Decisão**: PD-OVR-002. ~~Resolvido~~: NFKC apenas para injection scan, PII opera no texto original.

### Q6: Fail-open vs fail-closed por gate
**Decisão**: PD-OVR-004.
- Fail-open: CB, RL.
- Fail-closed: RBAC, ForbiddenTopics, Autonomy, InputContract, DLP.
- Cada gate wrapped em `try/except` individual.

### Q7: 5 testes de segurança falhando
**Decisão**: Corrigir mocks nesta sprint.
- Atualizar `exec_tool` → `tool_executor.run_tool` nos mocks.
- Atualizar import de `AUTO_TOOLS` de `core.domain.nexus.entities`.
- Expor `serve(port, origins)` em `ws_server.py` para testes.
- Esforço estimado: 1-2 horas.

### Q8: Forbidden topics base vs merge
**Decisão**: PD-OVR-005. Base imutável + merge, payload nunca substitui.

### Q9: Callers sem persona_id
**Decisão**: PD-OVR-006. Gates globais sempre rodam. Mapear 3 agentes faltantes.

### Q10: WS auth — Origin vs token
**Decisão**: Origin validation nesta sprint; token auth adiado para fase multi-user.
- `ALLOWED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8847"]`.
- `websockets.serve(handler, HOST, PORT, origins=ALLOWED_ORIGINS)`.

---

## 4. Invariantes Negativos (O que é PROIBIDO fazer)

> [!CAUTION]
> Estes invariantes são **invioláveis**. Qualquer implementação que viole um invariante negativo deve acionar Circuit Breaker de Spec (rollback à Fase 2).

### INV-N01: Nunca auto-aprovar valor financeiro não-parseável
```
PARA TODO args COM campo financeiro presente:
  SE _extract_amount(args) retorna UNPARSEABLE:
    evaluate_autonomy() DEVE retornar Decision.ESCALATE
  NUNCA Decision.APPROVE
```

### INV-N02: Nunca contar policy deny como failure de tool no CB
```
PARA TODA chamada onde pre_call_pipeline retorna allowed=False:
  post_call_pipeline NÃO DEVE chamar record_tool_outcome()
  Circuit Breaker NÃO DEVE incrementar failure_count
```

### INV-N03: Nunca aceitar HITL_DECISION sem validação de Origin
```
PARA TODA conexão WebSocket:
  SE Origin ∉ ALLOWED_ORIGINS:
    conexão DEVE ser rejeitada com HTTP 403
  NUNCA processar HITL_DECISION de Origin não-autorizado
```

### INV-N04: Nunca permitir payload esvaziar forbidden topics
```
PARA TODA chamada a ForbiddenTopicsGate.evaluate():
  SYSTEM_BASE_FORBIDDEN_TOPICS DEVE estar ativo
  payload["forbidden_topics"] NÃO PODE remover ou substituir a base
  NUNCA patterns = [] quando SYSTEM_BASE existe
```

### INV-N05: Nunca executar pipeline completo sem gates globais
```
PARA TODA chamada a broker.call():
  INDEPENDENTE de persona_id ser None ou não:
    Circuit Breaker DEVE ser verificado
    Rate Limiter DEVE ser verificado  
    Forbidden Topics (base) DEVE ser verificado
    WORM Audit DEVE registrar a chamada
  NUNCA ignorar gates globais por falta de persona_id
```

### INV-N06: Nunca permitir tool travar indefinidamente
```
PARA TODA execução de tool via broker._execute():
  DEVE existir asyncio.wait_for() com timeout finito
  NUNCA await sem timeout
```

### INV-N07: Nunca permitir substring match em forbidden topics
```
PARA TODA avaliação de ForbiddenTopicsGate:
  O matching DEVE usar word boundary (\b ou equivalente)
  NUNCA pattern in text (substring match direto)
  "pix" NÃO PODE casar com "pixel" ou "pixelado"
```

### INV-N08: Nunca falhar silenciosamente em gate de segurança
```
PARA TODO gate de segurança (RBAC, FT, Autonomy, InputContract, DLP):
  SE gate levanta exceção interna:
    DEVE retornar allowed=False (fail-closed)
  NUNCA permitir execução quando gate de segurança falha
```

### INV-N09: Nunca permitir HALF_OPEN servir múltiplas requisições
```
PARA TODA transição do CB para HALF_OPEN:
  Apenas 1 requisição DEVE passar (probe)
  As demais DEVEM aguardar ou ser rejeitadas
  NUNCA allow_request() = True para N>1 simultâneas em HALF_OPEN
```

### INV-N10: Nunca perder registro de audit por crash de SO
```
PARA TODA escrita no WORM audit log:
  DEVE chamar os.fsync() após f.write()
  NUNCA atualizar _last_hash sem garantir persistência em disco
```

### INV-N11: Nunca aprovar valor financeiro negativo
```
PARA TODO amount extraído por _extract_amount():
  SE amount < 0:
    DEVE retornar UNPARSEABLE (que resulta em ESCALATE)
  NUNCA amount < 0 → APPROVE
```

### INV-N12: Nunca executar DLP apenas no input
```
PARA TODA chamada de tool com resultado:
  post_call_pipeline DEVE executar DLP/PII scan no resultado
  NUNCA retornar resultado com PII não-mascarada ao agente
```

### INV-N13: Nunca permitir acesso cross-persona sem filtro
```
PARA TODA chamada a get_scoped_view() com FULL_ACCESS:
  SE persona_id ≠ dono dos records E persona_id ≠ "maia-orchestrator":
    DEVE filtrar campos sensíveis (tool_args, tool_result, raw_input, raw_output)
  NUNCA retornar list(history) sem filtro para persona diferente
```

### INV-N14: Nunca aceitar persona_id desconhecida
```
PARA TODA chamada a broker.call() com persona_id ≠ None:
  persona_id DEVE corresponder a um contrato builtin registrado
  SE get_builtin_contract(persona_id) retorna None:
    DEVE levantar ValueError antes de executar qualquer gate
  NUNCA executar pipeline com persona_id não-registrada
```

---

## 5. Especificação por Bug/GAP

### 5.1. F-AU-01 + F-AU-02 + GAP-03: Autonomy Amount Parsing

**Arquivo**: `core/policy/autonomy.py`

**Estado atual**:
```python
# L147-161
def _extract_amount(args):
    for field in ("amount", "valor", ...):
        val = args.get(field)
        if val is not None:
            try: return float(val)
            except: continue
    return None
```

**Estado desejado**:
```python
UNPARSEABLE = object()

def _extract_amount(args):
    found_fields = []
    for field in ("amount", "valor", "value", "total", "amount_brl"):
        val = args.get(field)
        if val is not None:
            parsed = _parse_brl(val)  # suporta "R$ 50.000,00"
            if parsed is None or parsed < 0 or not math.isfinite(parsed):
                return UNPARSEABLE
            found_fields.append(parsed)
    if not found_fields:
        return None
    # GAP-03: se valores conflitantes, UNPARSEABLE
    if len(set(found_fields)) > 1:
        return UNPARSEABLE
    return found_fields[0]

def _parse_brl(val):
    # ver implementação completa abaixo em "edge cases obrigatórios"
    ...
```

**Em `evaluate_autonomy()`** (L110-128):
```python
amount = _extract_amount(args)
if amount is UNPARSEABLE:
    return AutonomyVerdict(
        decision=Decision.ESCALATE,
        level=level,  # argumento obrigatório da dataclass
        reason=AutonomyReason.hitl_above_threshold,
        detail="campo financeiro inválido — requer aprovação humana",
        requires_hitl=True,
    )
# ... resto do fluxo normal com amount=None ou amount=float
```

**`_parse_brl` — edge cases obrigatórios**:
```python
def _parse_brl(val):
    """Parseia formato BR: 'R$ 50.000,00' → 50000.00"""
    if isinstance(val, bool):  # bool herda de int no Python!
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace("R$", "").replace(" ", "").strip()
        # Formato BR: pontos como separador de milhar, vírgula como decimal
        # Ex: "50.000,00" → "50000.00"
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            result = float(cleaned)
            return result if math.isfinite(result) else None
        except (ValueError, TypeError):
            return None
    return None
```

> [!NOTE]
> Requer `import math` no topo do arquivo.

**Testes obrigatórios**:
- `_extract_amount({"amount": "R$ 50.000,00"})` → `50000.0`
- `_extract_amount({"amount": "not_a_number"})` → `UNPARSEABLE`
- `_extract_amount({"amount": -1000})` → `UNPARSEABLE`
- `_extract_amount({"amount": 0, "valor": 90000})` → `UNPARSEABLE` (shadowing)
- `_extract_amount({})` → `None`
- `evaluate_autonomy("conditional_hitl", "transfer", {"amount": "R$ 50.000,00"}, 500)` → `ESCALATE`
- `evaluate_autonomy("conditional_hitl", "transfer", {"amount": -1000}, 500)` → `ESCALATE`

---

### 5.2. F-IP-05 + GAP-05: Post-call Pipeline Guard

**Arquivo**: `core/broker.py`

**Estado desejado**: Adicionar flag `executed = False` no `call()`.

```python
async def call(...):
    executed = False
    ...
    try:
        # pre_call_pipeline (agora roda sempre — PD-OVR-006)
        ...
        # tool execution
        outcome, raised = await asyncio.wait_for(
            _execute(tool, args), timeout=15.0
        )
        executed = True
        ...
    finally:
        # PD-OVR-006: post_call SEMPRE roda (CB, Audit), não só com persona_id
        if state is not None:
            post_call_pipeline(
                ...,
                success=(status == "ok"),
                executed=executed,  # NOVO
                persona_id=persona_id,  # pode ser None — gates globais ainda rodam
            )
```

**Em `post_call_pipeline()`** (`core/integration/__init__.py`):
```python
def post_call_pipeline(..., executed: bool = True):
    if executed:
        record_tool_outcome(tool_name, success)
        validate_output_contract(persona_id, result)
    # Audit SEMPRE, com event_type correto
    event_type = f"broker.call.{tool_name}" if executed else f"broker.blocked.{tool_name}"
    audit_call(event_type, identity, trace_id, result)
```

**Testes obrigatórios**:
- RBAC deny → `cb.failure_count` NÃO incrementa
- RBAC deny → audit trail registra `broker.blocked.{tool}`
- Tool executada com sucesso → `cb.record_success()` chamado
- Tool executada com erro → `cb.record_failure()` chamado

---

### 5.3. F-BR-01: Tool Timeout

**Arquivo**: `core/broker.py:115`

**Estado desejado**:
```python
try:
    outcome, raised = await asyncio.wait_for(
        _execute(tool, args), timeout=15.0
    )
    executed = True
except asyncio.TimeoutError:
    outcome = {"error": "ToolTimeout", "timed_out": True}
    raised = "ToolTimeout"
    executed = True  # tool FOI invocada, apenas não respondeu
```

**Testes obrigatórios**:
- Tool que demora 20s → `asyncio.TimeoutError` → `{"error": "ToolTimeout"}`
- CB registra failure após timeout
- Resultado tem `timed_out: True`

---

### 5.4. GAP-WS-01 + GAP-HT-01: WS Origin Validation

**Arquivo**: `backend/ws_server.py:220`

**Estado desejado**:
```python
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8847",
]

async with websockets.serve(
    handler, HOST, PORT,
    origins=ALLOWED_ORIGINS,
):
```

**Testes obrigatórios**:
- `Origin: https://evil.example` → HTTP 403
- `Origin: http://127.0.0.1:5173` → conexão aceita
- Sem Origin header → HTTP 403
- HITL_DECISION de Origin não-autorizado → rejeitado

---

### 5.5. GAP-12 + GAP-10: Pipeline Global + Persona Mapping

**Arquivo**: `core/broker.py:79` + `backend/orchestrator.py:41-45`

**Estado desejado em `broker.py`**:
```python
# ANTES: if persona_id: pre_call_pipeline(...)
# DEPOIS: pre_call_pipeline SEMPRE roda (PD-OVR-006)
# A separação entre gates globais e persona-specific ocorre DENTRO de pre_call_pipeline

pre_result = pre_call_pipeline(persona_id, tool_name, args, task_text)
# persona_id pode ser None — pre_call_pipeline roda gates globais de qualquer forma
```

**Estado desejado em `core/integration/__init__.py:pre_call_pipeline()`**:
```python
def pre_call_pipeline(persona_id, tool_name, args, task_text):
    # Gates globais — SEMPRE (fail-open para resiliência)
    try:
        cb_result = check_circuit_breaker(tool_name)
        if not cb_result.allowed:
            return cb_result
    except Exception:
        print("warn: CB check failed, allowing", file=sys.stderr)
    
    try:
        rl_result = check_rate_limit(tool_name)
        if not rl_result.allowed:
            return rl_result
    except Exception:
        print("warn: RL check failed, allowing", file=sys.stderr)

    # Forbidden topics com base imutável — SEMPRE (fail-closed)
    try:
        ft_result = check_forbidden_topics(task_text, persona_id=persona_id)
        if not ft_result.allowed:
            return ft_result
    except Exception:
        return PreCallResult(False, "forbidden_topics_internal_error")

    # Gates persona-specific — só com persona_id
    if persona_id:
        try:
            rbac_result = check_rbac(persona_id, tool_name)
            if not rbac_result.allowed:
                return rbac_result
        except Exception:
            return PreCallResult(False, "rbac_internal_error")
        # ... autonomy, input contract
    
    return PreCallResult(True, "allowed")
```

**Estado desejado em `orchestrator.py`**:
```python
AGENT_PERSONA_MAP = {
    "manager": "maia-orchestrator",
    "reviewer": "eva-supervisor",
    "researcher": "persona-researcher",   # NOVO
    "coder": "persona-devops",            # EXISTENTE (reuse)
    "writer": "persona-writer",           # NOVO
}
```

> [!IMPORTANT]
> **Override de No-Touch**: O handoff listava `core/schema/persona_contract.py` como No-Touch. Este override é necessário para criar `persona-researcher` e `persona-writer` como BUILTIN_CONTRACTS. A justificativa é que GAP-10 e PD-OVR-006 exigem que todos os agentes tenham persona mapeada.

**Nota**: Criação de `persona-researcher` e `persona-writer` como BUILTIN_CONTRACTS é necessária em `core/schema/persona_contract.py`.

**Testes obrigatórios**:
- `broker.call("agent:researcher", ...)` sem persona_id → CB + RL + FT base verificados
- `broker.call("agent:researcher", ..., persona_id="persona-researcher")` → pipeline completo
- 882 testes existentes continuam passando

---

### 5.6. F-OR-05: TTL Reset após HITL

**Arquivo**: `backend/orchestrator.py:224,258,297`

**Estado desejado** (PD-OVR-003):
```python
# Após _wait_approval() retornar:
mission_start = time.time()  # RESET do TTL
```

**Teste obrigatório**:
- Aprovar após 60s → TTL de 30s conta a partir da aprovação → primeiro step executa normalmente

---

### 5.7. F-FT-01: Word Boundary em Forbidden Topics

**Arquivo**: `core/gates/forbidden_topics_gate.py:87`

**Estado desejado**:
```python
# ANTES: if pattern in normalized_input:
# DEPOIS: word boundary
import re
pattern_re = re.compile(r'\b' + re.escape(pattern) + r'\b')
if pattern_re.search(normalized_input):
```

**Testes obrigatórios**:
- `"pix"` NÃO casa com `"pixel art"` (false positive eliminado)
- `"pix"` CASA com `"usar pix para pagar"` (true positive preservado)
- `"senhas de produção"` CASA com `"aqui estão as senhas de produção"` (multi-word)

---

### 5.8. GAP-FT-01: Forbidden Topics Base + Merge

**Arquivo**: `core/gates/forbidden_topics_gate.py:67-72` + `core/integration/__init__.py:85-90`

**Estado desejado** (PD-OVR-005):
```python
SYSTEM_BASE_FORBIDDEN_TOPICS = [
    "senhas de produção",
    "chaves de api",
    "credenciais de deploy",
    "tokens de acesso",
    "injection de prompt",
]

class ForbiddenTopicsGate:
    def __init__(self, forbidden_topics=None):
        base = list(SYSTEM_BASE_FORBIDDEN_TOPICS)
        extra = forbidden_topics or []
        self._patterns = [_normalize(t) for t in set(base + extra)]

    def evaluate(self, payload):
        # payload["forbidden_topics"] pode ADICIONAR, nunca substituir
        supplemental = payload.get("forbidden_topics", None)
        if supplemental and isinstance(supplemental, list):
            merged = self._patterns + [_normalize(t) for t in supplemental]
            patterns = list(set(merged))
        else:
            patterns = self._patterns
        # ... matching com word boundary
```

**Testes obrigatórios**:
- `ForbiddenTopicsGate([]).evaluate({"input_text": "chaves de api"})` → RED (base ativa)
- `ForbiddenTopicsGate(["pix"]).evaluate({"forbidden_topics": [], "input_text": "chaves de api"})` → RED (base imutável)
- `ForbiddenTopicsGate([]).evaluate({"forbidden_topics": ["pix"], "input_text": "pagar com pix"})` → RED (suplemento funciona)

---

### 5.9. F-WA-02: fsync no WORM Audit

**Arquivo**: `core/audit/worm_audit.py:188-191`

**Estado desejado**:
```python
with open(self.path, "a", encoding="utf-8") as f:
    f.write(line)
    f.flush()
    os.fsync(f.fileno())  # NOVO
self._last_hash = record.record_hash
```

> [!NOTE]
> Requer `import os` no topo do arquivo — atualmente **não importado** em `worm_audit.py`.

**Teste obrigatório**:
- Mock de `os.fsync` chamado após cada `f.write()`

---

### 5.10. F-DLP-04: Unicode NFKC para Injection

**Arquivo**: `core/security/dlp_guardrail.py:178-188`

**Estado desejado** (PD-OVR-002):
```python
import re
import unicodedata

_ZERO_WIDTH_RE = re.compile(r'[\u200b-\u200d\u200e\u200f\uFEFF\u00AD]')

def _strip_zero_width(text: str) -> str:
    """Remove zero-width characters que podem ser usados para evasão."""
    return _ZERO_WIDTH_RE.sub('', text)

def _detect_injection(text):
    # Normalizar para injection scan
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _strip_zero_width(normalized)
    # ... rodar regex no normalized
    # PII scan roda no texto ORIGINAL (não normalizado) — PD-OVR-002
```

> [!NOTE]
> `import re` e `import unicodedata` já existem no módulo.
> `_strip_zero_width` é uma função NOVA que deve ser adicionada.

**Testes obrigatórios**:
- Cyrillic `"а"` (U+0430) em `"ignore аll previous"` → detectado
- Zero-width chars entre `"ig\u200bnore"` → detectado
- `_strip_zero_width("ig\u200bnore")` → `"ignore"` (zero-width removido)
- PII masking no texto original (não normalizado) → preservado

---

### 5.11. F-IP-01: Isolamento de Gates (PD-OVR-004)

**Arquivo**: `core/integration/__init__.py:312-364`

**Estado desejado**: Cada gate wrapped em `try/except` com política diferenciada. **Early return** no primeiro gate que bloqueia.

```python
def pre_call_pipeline(persona_id, tool_name, args, task_text):
    # Resilience gates — fail-open (PD-OVR-004)
    try:
        cb_result = check_circuit_breaker(tool_name)
        if not cb_result.allowed:
            return cb_result  # early return: CB aberto
    except Exception:
        print("warn: CB check failed, allowing", file=sys.stderr)

    try:
        rl_result = check_rate_limit(tool_name)
        if not rl_result.allowed:
            return rl_result  # early return: rate limited
    except Exception:
        print("warn: RL check failed, allowing", file=sys.stderr)

    # Forbidden topics com base imutável — SEMPRE (fail-closed)
    try:
        ft_result = check_forbidden_topics(task_text, persona_id=persona_id)
        if not ft_result.allowed:
            return ft_result  # early return: topic proibido
    except Exception:
        return PreCallResult(False, "forbidden_topics_internal_error")

    # Security gates — fail-closed, só com persona_id
    if persona_id:
        try:
            rbac_result = check_rbac(persona_id, tool_name)
            if not rbac_result.allowed:
                return rbac_result  # early return: RBAC deny
        except Exception:
            return PreCallResult(False, "rbac_internal_error")

        try:
            autonomy_result = check_autonomy(persona_id, tool_name, args)
            if not autonomy_result.allowed:
                return autonomy_result
        except Exception:
            return PreCallResult(False, "autonomy_internal_error")

        try:
            input_result = validate_input_contract(persona_id, args)  # 2 args: real signature
            if not input_result.allowed:
                return input_result
        except Exception:
            return PreCallResult(False, "input_contract_internal_error")

    return PreCallResult(True, "allowed")
```

> [!IMPORTANT]
> O padrão é **early return** no primeiro gate que falha — NÃO acumular resultados
> em lista. Isto garante que uma exceção em gate N não impede a decisão do gate N-1.

**Testes obrigatórios**:
- Gate RBAC levanta `RuntimeError` → pipeline retorna `PreCallResult(False, "rbac_internal_error")`
- Gate CB levanta `RuntimeError` → pipeline **permite** (fail-open) e gates seguintes rodam
- Gate FT levanta `RuntimeError` → pipeline retorna `PreCallResult(False, "forbidden_topics_internal_error")`
- Pipeline sem persona_id → CB + RL + FT rodam, RBAC/Autonomy/Input **não** rodam

### 5.12. GAP-CB-01: HALF_OPEN Semáforo

**Arquivo**: `core/resilience/circuit_breaker.py:72,90-97,99-109,111-145`

**Estado desejado**:
```python
def __init__(self, ...):
    ...
    self._half_open_permitted = False  # NOVO

def _resolve_state(self) -> CircuitState:
    """Resolve estado real (OPEN pode virar HALF_OPEN por timeout)."""
    if self._stats.state == CircuitState.OPEN and self._stats.opened_at:
        elapsed = time.monotonic() - self._stats.opened_at
        if elapsed >= self.recovery_timeout:
            self._stats.state = CircuitState.HALF_OPEN
            self._consecutive_successes_half_open = 0
            self._half_open_permitted = False  # RESET: novo HALF_OPEN permite 1 probe
    return self._stats.state

def allow_request(self) -> bool:
    with self._lock:
        state = self._resolve_state()
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            if not self._half_open_permitted:
                self._half_open_permitted = True
                return True  # apenas 1 probe
            return False  # demais requisições bloqueadas
        # OPEN
        self._stats.total_rejected += 1
        return False

def record_success(self) -> None:
    with self._lock:
        ...  # (contagem existente)
        state = self._resolve_state()
        if state == CircuitState.HALF_OPEN:
            self._consecutive_successes_half_open += 1
            if self._consecutive_successes_half_open >= self.success_threshold:
                self._stats.state = CircuitState.CLOSED
                self._stats.opened_at = None
                self._consecutive_successes_half_open = 0
                self._half_open_permitted = False  # RESET: limpo para próximo ciclo

def record_failure(self) -> None:
    with self._lock:
        ...  # (contagem existente)
        state = self._resolve_state()
        if state == CircuitState.HALF_OPEN:
            # Falha em HALF_OPEN → reabre
            self._stats.state = CircuitState.OPEN
            self._stats.opened_at = time.monotonic()
            self._consecutive_successes_half_open = 0
            self._half_open_permitted = False  # RESET: reabertura limpa flag
        elif state == CircuitState.CLOSED:
            if self._consecutive_failures >= self.failure_threshold:
                self._stats.state = CircuitState.OPEN
                self._stats.opened_at = time.monotonic()
```

> [!WARNING]
> Sem os resets, `_half_open_permitted` fica `True` permanentemente após o primeiro
> probe. Na próxima transição OPEN→HALF_OPEN, `allow_request()` retornaria `False`
> para TODAS as requisições — deadlock permanente (INV-N09 violado).

**Testes obrigatórios**:
- Em HALF_OPEN: 1ª requisição → `True`, 2ª e 3ª → `False`
- Probe com sucesso (HALF_OPEN→CLOSED) → novo ciclo OPEN→HALF_OPEN permite novo probe
- Probe com falha (HALF_OPEN→OPEN) → timeout → novo HALF_OPEN permite novo probe
- Ciclo completo: CLOSED→OPEN→HALF_OPEN→(probe success)→CLOSED→OPEN→HALF_OPEN → probe permitido

---

### 5.13. GAP-SS-01: Scope Policy Enforcement

**Arquivo**: `core/memory/session_store.py:74-114`

**API real verificada**:
- Método: `get_scoped_view(session_id, persona_id, scope_policy) → List[Dict[str, Any]]`
- Sessions são `Dict[str, List[Dict[str, Any]]]` — records são dicts, **NÃO** objetos
- `_SCOPE_ALLOWED_FIELDS[ScopePolicy.FULL_ACCESS] = None` → retorna `list(history)` sem filtro
- **Não** existe `.owner` nem `_filter_pii()`

**Estado atual** (L103-105):
```python
# FULL_ACCESS: retorna tudo sem filtro
if allowed_fields is None:
    return list(history)
```

**Estado desejado**: `FULL_ACCESS` deve filtrar campos sensíveis em sessões cross-persona.
```python
# Constante para campos seguros em acesso cross-persona
_CROSS_PERSONA_SAFE_FIELDS: FrozenSet[str] = frozenset({
    "agent", "role", "event", "status", "summary", "bubble",
    "recorded_at", "type", "step_index",
    # Exclui: tool_args, tool_result, raw_input, raw_output (podem conter PII)
})

def get_scoped_view(
    self,
    session_id: str,
    persona_id: str,
    scope_policy: Optional[ScopePolicy] = None,
) -> List[Dict[str, Any]]:
    ...
    history = self._sessions.get(session_id, [])
    allowed_fields = _SCOPE_ALLOWED_FIELDS.get(scope_policy)

    # FULL_ACCESS com verificação cross-persona
    if allowed_fields is None:
        # Verificar se o persona_id que pede é o mesmo que gerou os records
        own_records = all(
            r.get("persona_id") == persona_id or r.get("agent") == persona_id
            for r in history if r.get("persona_id") or r.get("agent")
        )
        if own_records or persona_id in ("maia-orchestrator", "manager"):
            return list(history)  # própria sessão ou supervisor: acesso total
        # Cross-persona: filtrar campos sensíveis
        return [
            {k: v for k, v in record.items() if k in _CROSS_PERSONA_SAFE_FIELDS}
            for record in history
        ]
    # Demais policies: filtro por allowed_fields (existente)
    ...
```

> [!NOTE]
> A verificação de ownership usa campos existentes nos records (`persona_id` ou `agent`)
> em vez de um atributo `.owner` que não existe. O orchestrator (`maia-orchestrator`)
> e seu alias `manager` mantêm acesso total para supervisão.

**Testes obrigatórios**:
- Persona A pede `FULL_ACCESS` à sua própria sessão → todos os campos retornados
- Persona B pede `FULL_ACCESS` à sessão de Persona A → apenas `_CROSS_PERSONA_SAFE_FIELDS`
- `maia-orchestrator` pede `FULL_ACCESS` a qualquer sessão → acesso total (supervisor)
- `manager` pede `FULL_ACCESS` a qualquer sessão → acesso total (alias do orchestrator)
- `SCOPED_SUMMARY` → funciona como antes (inalterado)

### 5.14. GAP-06: DLP no Resultado da Tool

**Arquivo**: `core/integration/__init__.py:367-408`

**API real verificada**:
- `inspect_text(text) → DLPResult` — função module-level que existe em `core/security/dlp_guardrail.py:216-218`
- `DLPResult` tem: `.has_pii` (property bool), `.redacted_text` (str), `.pii_matches` (List[PIIMatch])
- **NÃO** existe `mask_pii()` como função separada — a máscara já está em `DLPResult.redacted_text`
- **NÃO** existe `.pii_found` — o atributo correto é `.has_pii`

**Estado desejado**: Adicionar DLP scan no `post_call_pipeline`.

> [!CAUTION]
> `post_call_pipeline` DEVE retornar `result` (possivelmente redacted). O chamador
> em `broker.call()` DEVE usar o valor retornado. Reatribuição local sem retorno
> causa vazamento de PII (violação de INV-N12).

```python
def post_call_pipeline(..., executed=True) -> Any:
    if executed:
        record_tool_outcome(tool_name, success)

        # NOVO: DLP scan no resultado (INV-N12)
        if success and result:
            from core.security.dlp_guardrail import inspect_text
            # Se result é dict, serializar para scan; se str, usar direto
            text_to_scan = (
                json.dumps(result, ensure_ascii=False, default=str)
                if isinstance(result, dict) else str(result)
            )
            dlp_result = inspect_text(text_to_scan)
            if dlp_result.has_pii:
                if isinstance(result, dict):
                    # Mutar in-place para garantir propagação ao chamador
                    redacted = _redact_dict_values(result)
                    result.clear()
                    result.update(redacted)
                else:
                    result = dlp_result.redacted_text

        validate_output_contract(persona_id, result)
    # Audit SEMPRE
    event_type = f"broker.call.{tool_name}" if executed else f"broker.blocked.{tool_name}"
    audit_call(event_type, identity, trace_id, result)
    return result  # OBRIGATÓRIO: chamador deve usar o retorno

def _redact_dict_values(d: dict) -> dict:
    """Aplica DLP em cada valor string do dict, preservando estrutura."""
    from core.security.dlp_guardrail import inspect_text
    redacted = {}
    for k, v in d.items():
        if isinstance(v, str):
            r = inspect_text(v)
            redacted[k] = r.redacted_text if r.has_pii else v
        elif isinstance(v, dict):
            redacted[k] = _redact_dict_values(v)
        else:
            redacted[k] = v
    return redacted
```

**Integração em `broker.call()`**:
```python
    finally:
        if state is not None:
            result = post_call_pipeline(  # REATRIBUIR do retorno
                ..., executed=executed,
            )
```

**Testes obrigatórios**:
- Tool retorna `{"cpf": "123.456.789-00", "status": "ok"}` → `cpf` mascarado, `status` preservado
- Tool retorna string com CPF → `redacted_text` retornado
- Tool retorna resultado sem PII → resultado inalterado
- `executed=False` → DLP NÃO roda (tool não executada)
- **Regressão INV-N12**: verificar que o dict retornado por `broker.call()` NÃO contém PII em plaintext

---

### 5.15. GAP-13: Persona ID Attestation (Mitigação)

**Arquivo**: `core/broker.py:64` + `core/integration/__init__.py:101-107`

**Mitigação nesta sprint** (atestação criptográfica completa é P2):
```python
# Validar que persona_id corresponde a um contrato builtin
def _validate_persona(persona_id):
    from core.schema.persona_contract import get_builtin_contract
    contract = get_builtin_contract(persona_id)
    if contract is None:
        raise ValueError(f"Unknown persona: {persona_id}")
    return contract
```

**Integração em `broker.call()`**:
```python
async def call(self, persona_id=None, ...):
    if persona_id:
        contract = _validate_persona(persona_id)  # ValueError se desconhecida
    ...
```

**Testes obrigatórios**:
- `_validate_persona("maia-orchestrator")` → retorna contrato válido
- `_validate_persona("persona-inexistente")` → `ValueError`
- `_validate_persona("persona-researcher")` → retorna contrato (NOVO builtin)
- `broker.call(persona_id="attacker-fake")` → rejeita antes do pipeline

---

### 5.16. Q7: Correção dos 5 Testes de Segurança

**Arquivo**: `tests/test_nexus_ws.py` + `backend/ws_server.py`

**Mudanças necessárias**:
1. Mock target: `exec_tool` → `backend.tool_executor.run_tool`
2. `AUTO_TOOLS` import: `backend.orchestrator` → `core.domain.nexus.entities`
3. Expor `serve(port, origins)` em `ws_server.py`
4. Adicionar `validate_mission_envelope` no handler `START`

**Testes que devem passar após correção**:
- `test_cross_origin_pages_cannot_connect` — Origin malicioso → HTTP 403 (valida GAP-WS-01)
- `test_start_without_a_valid_mission_is_rejected` — Envelope inválido → erro (valida integridade)
- `test_empty_new_task_is_rejected` — Task vazia → rejeitada
- `test_no_mission_pattern_runs_a_host_command` — Pattern desconhecido → RCE bloqueado
- `test_a_host_command_step_is_refused_without_calling_the_executor` — Step host → executor NÃO chamado

---

## 6. Arquivos Envolvidos (Resumo)

| # | Arquivo | Mudanças |
|---|---------|----------|
| 1 | `core/policy/autonomy.py` | UNPARSEABLE sentinel, _parse_brl, shadowing check |
| 2 | `core/broker.py` | executed flag, asyncio.wait_for, global gates |
| 3 | `core/integration/__init__.py` | gate isolation, post_call guard, DLP no result |
| 4 | `core/gates/forbidden_topics_gate.py` | word boundary, base topics, merge-only |
| 5 | `core/audit/worm_audit.py` | os.fsync() |
| 6 | `core/security/dlp_guardrail.py` | NFKC normalization |
| 7 | `core/resilience/circuit_breaker.py` | HALF_OPEN semaphore |
| 8 | `core/memory/session_store.py` | FULL_ACCESS ownership check |
| 9 | `backend/orchestrator.py` | TTL reset, AGENT_PERSONA_MAP completo |
| 10 | `backend/ws_server.py` | origins=, serve() factory |
| 11 | `tests/test_nexus_ws.py` | Mock updates (5 testes) |
| 12 | `core/schema/persona_contract.py` | persona-researcher, persona-writer builtin |

---

## 7. Invariantes a Preservar (Positivos)

1. **882 testes passando** — nenhum pode quebrar.
2. **Backward compatibility** — `broker.call()` sem `persona_id` continua funcionando.
3. **API pública** — assinaturas de funções não mudam (apenas adição de params com defaults).
4. **WORM hash-chain** — `verify_chain()` continua válida.
5. **Conventional Commits** — em português: `fix: F-XX-NN — descrição`.
6. **Git workflow** — branch `fix/security-hardening-p0-p1`, PR para `main`.

---

## 8. Riscos

| # | Risco | Sev | Mitigação |
|---|-------|-----|-----------|
| R1 | `_parse_brl` pode não cobrir todos os formatos de moeda | Baixo | Testar com corpus de formatos BR reais |
| R2 | Word boundary pode falhar com caracteres Unicode | Baixo | Usar `\b` de re com UNICODE flag |
| R3 | Novas BUILTIN_CONTRACTS (researcher, writer) podem ter permissões incorretas | Médio | Copiar padrão de persona-devops com allowlist restrita |
| R4 | DLP no resultado pode afetar performance | Baixo | Medir latência; skip se resultado < 100 chars |
| R5 | `os.fsync()` pode afetar throughput do audit | Baixo | Single-process, volume baixo (~10 calls/missão) |

---

## 9. Critério de Conclusão da Fase 3

A Fase 3 (Plan Gate) estará completa quando:
1. [ ] Plano mestre em `docs/superpowers/plans/2026-10-15-security-hardening-plan.md`
2. [ ] Briefs SDD atômicos em `.superpowers/sdd/2026-10-15-security-hardening-plan/`
3. [ ] `progress.md` com tabela de status `pending`
4. [ ] Aprovação formal humana para execução
5. [ ] Handoff para Fase 4

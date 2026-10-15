# Relatório de Evidências 3D — Security Hardening v1.0.0-moe

> **Fase**: 1 — Discovery & Investigação (Tríade 3D)
> **Data**: 2026-10-15
> **Escopo**: 18 módulos do pipeline MoE/Zero-Trust
> **Saldo de Código**: `+0 / -0` (somente leitura)
> **Tag de Referência**: `v1.0.0-moe` (commit `59ad40b`)

---

## 1. Eixo Vertical — Ingress Trace (Call Graph Real)

### Ponto de Entrada Externo

```
WebSocket (ws://127.0.0.1:8848)
  └── ws_server.py:handler()  (L54)
      └── json.loads(raw)  →  message.get("action")
          ├── "NEW_TASK"  →  Orchestrator().run_mission(task_text)
          ├── "APPROVE"   →  orchestrator.approve()
          └── "HITL_DECISION"  →  HITLPendingStore.resolve()
```

### Call Graph: NEW_TASK → Execução Completa

```
ws_server.handler() [L75]
  └── orchestrator.run_mission(task, mission_id) [L215]
      ├── mission_start = time.time()  ← ⚡ F-OR-05: TTL começa AQUI
      ├── _match_pattern(task) → steps [L232]
      ├── get_persona_contract("maia-orchestrator") → max_hops [L236-L246]
      ├── check_mission(steps, mission_id) → guard [L249]
      │   └── CompoundGatePipeline().run_all(payload) [mission_guard.py:L69]
      │       └── except Exception: semaphore="RED" ← ⚡ F-MG-01: silent swallow
      ├── IF guard=="approval": _wait_approval(timeout=300s) [L258]
      │   └── ⚡ F-OR-05: Se operador leva >30s, TTL já expirou!
      ├── MoE routing: _route_agent_for_step() [L264-L268]
      │   └── MoERouter.route(context) → RoutingDecision
      │       └── ⚡ F-MOE-01: Pode retornar persona inexistente em AGENT_IDS
      ├── unbind_open_circuit_tools(steps) [L271]
      ├── FOR step in steps: [L296]
      │   ├── TTL check: time.time() - mission_start > 30 ← ⚡ F-OR-05
      │   ├── tool_executor.run_tool(tool, args, persona_id=AGENT_PERSONA_MAP.get(agent)) [L340]
      │   │   └── ⚡ F-OR-06: researcher/coder/writer → persona_id=None
      │   │       → pipeline inteiro IGNORADO
      │   └── broker.call(identity, tool, args, persona_id=...) [broker.py:L62]
      │       ├── pre_call_pipeline(persona_id, tool, args, task_text) [L82]
      │       │   ├── 1. check_circuit_breaker(tool)
      │       │   ├── 2. check_rate_limit(tool)
      │       │   │   └── ⚡ F-RL-04: tokens<0 bypassa
      │       │   ├── 3. check_rbac(persona_id, tool)
      │       │   ├── 4. check_forbidden_topics(task_text, persona_id)
      │       │   │   └── ForbiddenTopicsGate.evaluate()
      │       │   │       └── ⚡ F-FT-01: substring match sem word boundary
      │       │   ├── 5. check_autonomy(persona_id, tool, args)
      │       │   │   └── evaluate_autonomy()
      │       │   │       └── _extract_amount(args)
      │       │   │           └── ⚡ F-AU-01: float("R$ 50.000") → ValueError → None
      │       │   │               → auto-APPROVE indevido
      │       │   └── 6. validate_input_contract(persona_id, args)
      │       ├── IF pre_call blocks: status="refused" → return [L84]
      │       │   └── finally: post_call_pipeline(success=False) [L148]
      │       │       └── record_tool_outcome(tool, success=False)
      │       │           └── cb.record_failure()
      │       │               └── ⚡ F-IP-05: RBAC deny → CB abre!
      │       ├── decide(identity, tool, args) → Verdict [L104]
      │       ├── _execute(tool, args) → await IMPLEMENTATIONS[tool](**args) [L56]
      │       │   └── ⚡ F-BR-01: SEM asyncio.wait_for → trava se tool travar
      │       └── finally: post_call_pipeline(success=(status=="ok")) [L148]
      │           ├── record_tool_outcome(tool, success)
      │           ├── audit_call(...) → WORMAuditLog.append()
      │           │   └── ⚡ F-WA-01: sem file lock multi-process
      │           │   └── ⚡ F-WA-02: sem os.fsync() após f.write() — crash perde registros
      │           └── validate_output_contract(persona_id, result) [L404]
      └── run_post_mission_gates(persona, results) [L371]
```

---

## 2. Eixo Histórico — ADR Drift & Código Zumbi

### ADRs Vigentes vs Código Atual

| ADR | Expectativa | Estado Atual | Drift? |
|-----|-------------|--------------|--------|
| ADR-022 (Quality Gates) | 5 gates pré-missão | ✅ Implementado (Sprint 0) | Nenhum |
| Plano de Convergência MoE | 11 requisitos (R1-R11) | R4-R11 implementados. R1-R3 infra. | R1-R3 aceito como gap |
| Simulador MoE (TSX) | confidence_threshold 0.82-0.88 | Calibrado em 0.10-0.15 (keyword) | Aceito: keyword ≠ vector |
| Simulador MoE (TSX) | auto_approve_up_to_brl = R$10.000 | Configurado R$500 (mais conservador) | Intencional |
| WORM Audit | Imutabilidade criptográfica | API-only (sem filesystem lock) | ⚠️ Gap em produção |

### Código Zumbi Detectado

| Arquivo | Problema |
|---------|----------|
| `tests/test_nexus_ws.py` | 16 testes falhando — referências a `exec_tool`, `AUTO_TOOLS`, `BrainRetriever`, porta 8849 (legado pré-MoE) |
| `simulador_de_governan_a_e_orquestra_o_multi_agentes_moe.tsx` | Referência (TSX) não integrada — arquivo avulso |

---

## 3. Eixo Horizontal — Blast Radius & Status da Suíte

### Suíte de Testes (Baseline)

```
882 passed, 16 failed, 1 warning — 35.54s
```

- **882 passando**: Todo o código MoE (Sprints 0-9) + código legado
- **16 falhando**: Todos em `test_nexus_ws.py` — pré-existentes, não relacionados ao MoE
- **Cobertura MoE**: 13 arquivos de teste dedicados (`test_dlp_*.py`, `test_resilience.py`, `test_scoped_context_*.py`, `test_schema_audit.py`, `test_autonomy_*.py`, `test_governance.py`, `test_integration.py`, `test_sprint8_*.py`, `test_sprint9_*.py`)

### Consumidores Colaterais

| Módulo | Consumidores Diretos | Impacto de Mudança |
|--------|---------------------|-------------------|
| `broker.py` | `tool_executor.py`, `mission_guard.py` | ALTO — ponto central |
| `integration/__init__.py` | `broker.py`, `orchestrator.py`, `ws_server.py` | ALTO — pipeline completo |
| `autonomy.py` | `integration/__init__.py` via `check_autonomy()` | MÉDIO — 1 caller |
| `rate_limiter.py` | `integration/__init__.py` via `check_rate_limit()` | MÉDIO — 1 caller |
| `forbidden_topics_gate.py` | `integration/__init__.py` via `_get_forbidden_gate()` | MÉDIO — 1 caller |
| `orchestrator.py` | `ws_server.py` | ALTO — async generator |
| `worm_audit.py` | `integration/__init__.py` via `_get_audit_log()` | MÉDIO — 1 caller |
| `session_store.py` | Não utilizado diretamente pelo pipeline! | BAIXO — futuro |

---

## 4. Investigação Causal (Método de 6 Passos)

### Causa 1: F-AU-01 — Auto-aprovação financeira indevida

| Passo | Resultado |
|-------|-----------|
| 1. Regra na norma | Simulador MoE: `conditional_hitl` deve escalar se valor > limiar |
| 2. Código atual | `autonomy.py:147-161` — `_extract_amount()` retorna `None` se `float()` falha |
| 3. Mecanismo | `amount=None` + `auto_approve_up_to_brl >= 0` → `APPROVE`. Não distingue "campo ausente" de "campo presente mas não-parseável" |
| 4. Cobertura de teste | **Ausente** — nenhum teste com formato `"R$ 50.000,00"` |
| 5. ADR | Nenhuma ADR define formatos de moeda aceitos |
| 6. Classificação | **(a) Violou regra** — conditional_hitl deve escalar em dúvida, não aprovar |

### Causa 2: F-IP-05 — Contaminação cruzada do Circuit Breaker

| Passo | Resultado |
|-------|-----------|
| 1. Regra | CB deve registrar apenas falhas reais de tool/serviço |
| 2. Código | `broker.py:148-158` — `finally:` chama `post_call_pipeline(success=False)` mesmo quando `pre_call` bloqueou |
| 3. Mecanismo | RBAC deny → `status="refused"` → `success=(status=="ok")=False` → `cb.record_failure()` |
| 4. Cobertura | **Ausente** — nenhum teste valida que deny de RBAC NÃO abre CB |
| 5. ADR | Nenhuma |
| 6. Classificação | **(b) Regra omissa** — não havia especificação sobre o que é "falha" para o CB |

### Causa 3: F-OR-05 — TTL inclui tempo de espera HITL

| Passo | Resultado |
|-------|-----------|
| 1. Regra | TTL anti-loop de 30s deve proteger contra execução excessiva |
| 2. Código | `orchestrator.py:224` — `mission_start = time.time()` no início da missão |
| 3. Mecanismo | Tempo de `_wait_approval(300s)` conta contra o TTL de 30s |
| 4. Cobertura | **Ausente** — nenhum teste exercita TTL com aprovação lenta |
| 5. ADR | Nenhuma |
| 6. Classificação | **(a) Violou regra** — TTL deveria contar tempo de EXECUÇÃO, não tempo total |

### Causa 4: F-RL-04 — Bypass por tokens negativos

| Passo | Resultado |
|-------|-----------|
| 1. Regra | Rate limiter deve impedir chamadas acima do limite |
| 2. Código | `rate_limiter.py:72-81` — `try_acquire(tokens)` aceita qualquer int |
| 3. Mecanismo | `tokens=-5` → `self._tokens >= -5` = True → `self._tokens -= (-5)` = **adiciona 5** |
| 4. Cobertura | **Ausente** — nenhum teste com tokens negativos |
| 5. ADR | Nenhuma |
| 6. Classificação | **(b) Regra omissa** — API não valida parâmetros de entrada |

### Causa 5: F-FT-01 — Falsos positivos em forbidden topics

| Passo | Resultado |
|-------|-----------|
| 1. Regra | Gate deve bloquear apenas tópicos proibidos exatos |
| 2. Código | `forbidden_topics_gate.py:87` — `if pattern in normalized_input:` |
| 3. Mecanismo | `"pix"` casa com `"pixel"`, `"pixelado"` (substring match) |
| 4. Cobertura | **Parcial** — testes existem mas com tópicos longos que não revelam o bug |
| 5. ADR | Nenhuma |
| 6. Classificação | **(a) Violou regra** — matching deveria ser por word boundary |

---

## 5. Tabela de Hipóteses Descartadas

| # | Hipótese | Evidência de Descarte |
|---|----------|----------------------|
| H1 | "O problema de TTL é cosmético — o Orchestrator nunca pede aprovação HITL na prática" | **Descartada**: L254-260 do orchestrator.py mostra que `guard["action"] == "approval"` dispara `_wait_approval()`. O cenário é real. |
| H2 | "O CB cross-contamination só acontece com persona_id" | **Descartada**: `broker.py:148` — o `finally` roda SEMPRE, inclusive sem `persona_id`. Porém, sem persona_id, `pre_call_pipeline` não bloqueia (não entra no if L79). O bug só ocorre COM persona_id. |
| H3 | "O rate limiter com tokens negativos requer acesso interno ao código" | **Confirmada como baixo risco**: `try_acquire()` não é exposto diretamente via WS. Mas se um gate ou módulo interno chamar com valor calculado negativo (ex: `tokens = remaining_budget`), o bypass acontece. |
| H4 | "A vulnerabilidade F-AU-01 requer persona com conditional_hitl" | **Confirmada**: Apenas `persona-finops` tem `conditional_hitl`. Os demais são `auto_execute` ou `supervisor_approval`. Risco limitado a 1 persona. |
| H5 | "O Session Store sem lock é seguro porque asyncio é single-threaded" | **Parcialmente descartada**: asyncio é single-threaded no event loop, mas `threading.Lock` é usado em TODOS os outros módulos (CB, RL, HITL, WORM). Se um background thread acessar SessionStore, há race condition. |

---

## 6. Inventário de Arquivos Afetados (Blast Radius da Sprint)

| Arquivo | Linhas | Tipo de Mudança Prevista |
|---------|--------|--------------------------|
| `core/policy/autonomy.py` | 162 | Fix: `_extract_amount()` + validação de negativos |
| `core/broker.py` | 164 | Fix: não chamar `post_call_pipeline` quando `pre_call` bloqueou |
| `core/broker.py` | 164 | Fix: `asyncio.wait_for()` em `_execute()` |
| `backend/orchestrator.py` | 507 | Fix: resetar `mission_start` após aprovação HITL |
| `core/resilience/rate_limiter.py` | 156 | Fix: rejeitar `tokens <= 0` |
| `core/gates/forbidden_topics_gate.py` | 115 | Fix: word boundary matching |
| `core/memory/session_store.py` | 128 | Fix: adicionar `threading.Lock` |
| `core/audit/worm_audit.py` | 301 | Fix: adicionar `os.fsync()` após `f.write()` |
| `core/security/dlp_guardrail.py` | 219 | Fix: normalização Unicode pré-scan |
| `core/integration/__init__.py` | 524 | Fix: try/except individual por check |
| **Total** | ~2.500 | 10 arquivos de produção |

> **No-Touch Files** (não devem ser modificados):
> - `core/schema/persona_contract.py` — nenhuma mudança necessária
> - `core/routing/moe_router.py` — mudanças são P2 (sprint seguinte)
> - `core/governance/*.py` — mudanças são P2/P3
> - `backend/tool_executor.py` — passthrough, sem mudança
>
> ⚠️ **ws_server.py REMOVIDO do No-Touch** (2026-10-15 — auditoria adversarial):
> É ponto de entrada externo sem autenticação. Inclui GAP-WS-01 (CSWSH) e GAP-HT-01 (HITL sem auth).

---

## 7. Addendum: Lacunas Descobertas por Auditoria Adversarial (2026-10-15)

> Seção adicionada após revisão por 3 agentes independentes que identificaram
> falsos positivos, inversões de severidade e 19+ lacunas não detectadas.

### 7.1 Falsos Positivos Removidos

| ID | Afirmação Original | Evidência de Descarte |
|----|--------------------|-----------------------|
| FP-1 | F-WA-02: "_last_hash atualizado ANTES do disco" | L189 escreve, L191 atualiza. Bug real = falta de `os.fsync()`. |
| FP-2 | ReDoS no DLP | Regex testada com 50k chars, <4ms. Complexidade O(N). |
| FP-3 | Step Name Injection no orchestrator | Steps vêm de `MISSION_PATTERNS` (lista estática hardcoded, não injetável pelo usuário). |

### 7.2 Inversões de Severidade

| Bug | Antes | Depois | Justificativa |
|-----|-------|--------|---------------|
| F-AU-02 | P1 | **P0** | Mesmo impacto de F-AU-01 (APPROVE indevido) |
| WS Zero-Auth + CSWSH | No-Touch | **P0** | Ponto de entrada sem auth (Due Diligence §4) |
| GAP-FT-01 | — | **P1** | Gate desligável pelo payload (via pipeline normal não é explorável — L195 bloqueia lista vazia) |
| GAP-HT-01 | — | **P0** | HITL aprovável por qualquer frame WS |
| GAP-12 | — | **P0** | Pipeline fail-open por design |
| F-OR-05 | P0 | **P1** | Funcional, não compromete dados |
| F-RL-04 | P1 | **P3** | Sem vetor externo |
| F-SS-01 | P1 | **P3** | Módulo não utilizado pelo pipeline ativo |

### 7.3 Lacunas Críticas Detectadas

| ID | Arquivo | Descrição | Sev. |
|----|---------|-----------|------|
| GAP-FT-01 | `forbidden_topics_gate.py:67-72` | `{"forbidden_topics": []}` desliga o gate (via pipeline, L195 bloqueia) | P1 |
| GAP-HT-01 | `ws_server.py:142-161` | HITL sem autenticação — qualquer frame WS aprova | P0 |
| GAP-WS-01 | `ws_server.py:220` | CSWSH — sem `origins=` no `websockets.serve()` | P0 |
| GAP-12 | `integration/__init__.py:16-17` | Pipeline opt-in e fail-open — `persona_id=None` desativa tudo | P0 |
| GAP-13 | `broker.py:64` | Spoofing de `persona_id` — sem atestação criptográfica | P1 |
| GAP-10 | `orchestrator.py:41-45` | 3 de 5 agentes sem persona → zero governance | P1 |
| GAP-CB-01 | `circuit_breaker.py:99-109` | HALF_OPEN permite todas as requisições (thundering herd) | P1 |
| GAP-SS-01 | `session_store.py:26,74-114` | `FULL_ACCESS` permite leitura cross-session + scope_policy bypassável | P1 |
| GAP-06 | `integration/__init__.py:367-408` | Tool results não passam por DLP | P1 |
| GAP-03 | `autonomy.py:153-160` | Shadowing de campos financeiros (`amount`=0, `valor`=90000) | P1 |
| GAP-14 | `integration/__init__.py:330-344` | Rate Limiter antes do RBAC (ordering DoS) | P2 |
| GAP-05 | `broker.py:126-162` | Pre-call deny executa post-call (audit + CB para tools não executadas) | P2 |
| GAP-17 | `dlp_guardrail.py:190-213` | PIIs sobrepostas corrompem texto mascarado | P2 |
| GAP-18 | `dlp_guardrail.py:17-51` | Ausência de RG, CEP, CNH, PIX | P2 |
| GAP-RL-01 | `rate_limiter.py` (RateLimiterRegistry) | Criação ilimitada de buckets por nomes dinâmicos → OOM | P2 |
| GAP-WA-01 | `worm_audit.py:188-189` | Sem `os.fsync()` → crash perde registros | P1 |
| GAP-WA-02 | `worm_audit.py` (read_all/verify_chain) | JSON adulterado → `continue` silencioso | Adiado |
| GAP-19 | `dlp_guardrail.py` | Evasão por Base64/URL encoding/gramática PT-BR | Adiado |

### 7.4 Reproduções Executadas com Sucesso

```
F-AU-01: float("50.000,00") → ValueError → None → APPROVE ✅
F-AU-02: amount=-1000000 <= 500 → APPROVE ✅
GAP-FT-01: {"forbidden_topics": []} → gate GREEN (bypass) ✅
GAP-CB-01: 3 allow_request() em HALF_OPEN → todas True (thundering herd) ✅
GAP-14: Token consumido antes de RBAC deny (DoS por exaustão) ✅
```

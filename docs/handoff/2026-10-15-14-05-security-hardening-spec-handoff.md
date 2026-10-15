# Handoff Autossuficiente — Security Hardening P0/P1 (Fase 1-fix)

> **De**: Fase 1-fix (Correção da Discovery 3D pós-auditoria adversarial)
> **Para**: Fase 2 (Especificação & Invariantes Negativos)
> **Data**: 2026-10-15T14:42-03:00
> **Task**: `security-hardening-p0-p1`
> **Tag de Referência**: `v1.0.0-moe` (commit `59ad40b`)
> **Suíte Baseline**: 882 passed, 16 failed (pré-existentes), 1 warning — 35.54s
> **Revisão**: v2.0 — Corrigida por auditoria adversarial com 3 agentes independentes

---

## Seção 1: Contexto & Motivação

O KIOSK AI-OS foi lançado como `v1.0.0-moe` (tag `59ad40b`) com 11 PRs (#17–#27) implementando o pipeline MoE/Zero-Trust: Circuit Breaker, Rate Limiter, DLP, MoE Router, PersonaContract, RBAC, Forbidden Topics, IO Contracts, HITL Protocol, Handoff Protocol, WORM Audit, Autonomy Levels.

Uma auditoria estática completa dos 18 módulos (~4.000 linhas de código de governança) revelou vulnerabilidades que foram revisadas por uma **auditoria adversarial com 3 agentes independentes**. Essa contra-auditoria identificou:

- **3 falsos positivos** na Discovery original (corrigidos nesta revisão)
- **5 inversões de severidade** (reclassificadas nesta revisão)
- **19+ lacunas críticas** não detectadas na Discovery original (adicionadas nesta revisão)
- **Falhas metodológicas**: evidências 100% teóricas, PD-OVR fantasmas, handoff incompleto

### Resultado Consolidado (pós-correção)

| Severidade | Contagem | IDs |
|-----------|----------|-----|
| **P0** | 6 | F-AU-01, F-AU-02, F-IP-05, GAP-HT-01, GAP-WS-01, GAP-12 |
| **P1** | 13 | F-OR-05, F-FT-01, F-BR-01, F-WA-02, F-DLP-04, F-IP-01, GAP-FT-01, GAP-13, GAP-10, GAP-CB-01, GAP-SS-01, GAP-06, GAP-03 |
| **P2** | 5 | GAP-14, GAP-05, GAP-17, GAP-18, GAP-RL-01 |
| **P3** | 2 | F-RL-04, F-SS-01 |
| **Adiado** | 2 | GAP-19, GAP-WA-02 |

---

## Seção 2: Causa Raiz Consolidada

### P0 — Vulnerabilidades de Segurança Críticas

#### 1. F-AU-01: Auto-aprovação financeira indevida
- **Arquivo**: `core/policy/autonomy.py:147-161`
- **Mecanismo**: `_extract_amount("R$ 50.000,00")` → `float("R$ 50.000,00")` → `ValueError` → retorna `None`. O `evaluate_autonomy()` (L112-121) trata `amount=None` como "sem valor financeiro" → **APPROVE automático** de transações de qualquer valor.
- **Causa raiz**: O código não distingue "campo ausente" de "campo presente mas não-parseável". Formato BR com pontos de milhar e vírgula decimal não é suportado por `float()`.
- **Reprodução**: `python -c "from core.policy.autonomy import _extract_amount; print(_extract_amount({'amount': 'R$ 50.000,00'}))"` → `None`

#### 2. F-AU-02: Valores negativos auto-aprovados (**reclassificado de P1 para P0**)
- **Arquivo**: `core/policy/autonomy.py:130`
- **Mecanismo**: `amount = -1000` → `amount <= auto_approve_up_to_brl (500)` → `True` → **APPROVE**.
- **Justificativa para P0**: O impacto é idêntico ao de F-AU-01 — ambos resultam em aprovação automática indevida de operações financeiras. Pela regra de consistência do Due Diligence Harness §7, bugs com mesmo impacto devem ter mesma severidade.
- **Reprodução**: `python -c "from core.policy.autonomy import evaluate_autonomy; print(evaluate_autonomy('conditional_hitl', 'transfer', {'amount': -1000}, 500).decision)"` → `APPROVE`

#### 3. F-IP-05: Contaminação cruzada do Circuit Breaker
- **Arquivo**: `core/broker.py:79-94,126-162` + `core/integration/__init__.py:253-259`
- **Mecanismo**: Quando `pre_call_pipeline` bloqueia (RBAC deny), o `return` na L94 está dentro do `try`. O `finally` na L126 executa `post_call_pipeline(success=False)` → `record_failure()` → CB incrementa falha. Uma negação de RBAC é contabilizada como falha da tool, potencialmente **abrindo o Circuit Breaker para todos**.
- **Nota**: O `state` é criado na L88-93 antes do `return`, e L148 verifica `if persona_id and state is not None` → True → executa.
- **Reprodução**: `pre_call_pipeline("persona-finops", "transfer", {}, "task")` com RBAC deny → `post_call_pipeline(success=False)` → `cb.record_failure()` incrementa contagem

#### 4. GAP-FT-01: Forbidden topics sem baseline e payload-overridable (**NOVO**)
- **Arquivo**: `core/gates/forbidden_topics_gate.py:67-72` + `core/integration/__init__.py:188-196`
- **Mecanismo**: Duas falhas combinadas:
  1. O singleton `_get_forbidden_gate()` é criado com `ForbiddenTopicsGate()` → `forbidden_topics=[]`. **Não há tópicos base do sistema** — os tópicos vêm exclusivamente do contrato da persona (L195-196). Agentes sem persona (GAP-10) não têm forbidden topics.
  2. O método `gate.evaluate()` aceita `payload["forbidden_topics"]` que **sobrescreve** (não faz merge com) os tópicos configurados. Um caller que injete `{"forbidden_topics": []}` no payload desliga o gate completamente.
- **Vetor real**: Não é exploratável via pipeline normal (L195 `if contract.forbidden_topics:` impede lista vazia), mas o **design sem baseline** significa que qualquer agente sem contrato opera sem nenhuma restrição de tópicos.
- **Reprodução**: `ForbiddenTopicsGate(["senhas"]).evaluate({"input_text": "senhas de producao", "forbidden_topics": []}).passed` → `True` (bypass direto confirmado)

#### 5. GAP-HT-01: HITL sem autenticação (**NOVO**)
- **Arquivo**: `backend/ws_server.py:142-161`
- **Mecanismo**: O handler de `HITL_DECISION` (L142) aceita qualquer frame WebSocket com `action.type == "HITL_DECISION"`. Chama `HITLResponse.from_frame(hitl_payload)` → `store.resolve(response)` **sem nenhuma verificação de autenticação**. Qualquer cliente WS conectado pode aprovar ações HITL pendentes.
- **Combinado com GAP-WS-01**: Sem validação de Origin, um atacante em qualquer website pode abrir conexão WS e enviar HITL_DECISION.

#### 6. GAP-WS-01: Cross-Site WebSocket Hijacking (**NOVO**)
- **Arquivo**: `backend/ws_server.py:220`
- **Mecanismo**: `websockets.serve(handler, HOST, PORT)` — sem parâmetro `origins=` na chamada. O servidor aceita conexões de **qualquer Origin**, incluindo páginas maliciosas. Um atacante pode criar uma página web que abre `ws://127.0.0.1:8848` e enviar comandos arbitrários.
- **Impacto**: Combinado com GAP-HT-01, permite aprovação remota de ações HITL e execução de missões via CSWSH.
- **Nota**: O handoff original listava `ws_server.py` como **No-Touch**. Isso é uma falha metodológica — um ponto de entrada externo sem auth não pode ser excluído do escopo (Due Diligence Harness §4).

#### 7. GAP-12: Pipeline opt-in e fail-open (**NOVO**)
- **Arquivo**: `core/integration/__init__.py:16-17` + `core/broker.py:79`
- **Mecanismo**: O pipeline é opt-in via `persona_id`. O `broker.py:79` verifica `if persona_id:` — sem `persona_id`, **todo o pipeline de segurança é ignorado** (RBAC, forbidden topics, autonomy, IO contracts). Isso é um fail-open by design.
- **Vetor**: `tool_executor.py` chama `broker.call()` com `persona_id=AGENT_PERSONA_MAP.get(agent)`. 3 de 5 agentes (researcher, coder, writer) não têm persona mapeada (GAP-10), resultando em `persona_id=None` → zero governance.

### P1 — Bugs Críticos

#### 8. F-OR-05: TTL inclui tempo de espera HITL (**reclassificado de P0 para P1**)
- **Arquivo**: `backend/orchestrator.py:224,258,297`
- **Mecanismo**: `mission_start = time.time()` é marcado no início da missão (L224), ANTES de `_wait_approval(timeout=300s)` (L258). Se o operador leva >30s para aprovar, o TTL de 30s já expirou → missão abortada no primeiro step (L297).
- **Justificativa para P1**: É um bug funcional que causa timeout indevido, mas **não compromete dados nem permite bypass de segurança**. A missão é abortada de forma segura (fail-closed).
- **Resolução**: PD-OVR-003 — resetar `mission_start` após aprovação HITL.

#### 9. F-FT-01: Substring match em forbidden topics
- **Arquivo**: `core/gates/forbidden_topics_gate.py:87`
- **Mecanismo**: `if pattern in normalized_input:` — "pix" casa com "pixel", "pixelado" etc. (substring match sem word boundary).
- **Reprodução**: `ForbiddenTopicsGate(["pix"]).evaluate({"input_text": "vou fazer pixel art"})` → RED (falso positivo)

#### 10. F-BR-01: Tool sem timeout — trava indefinidamente
- **Arquivo**: `core/broker.py:56`
- **Mecanismo**: `result = await IMPLEMENTATIONS[tool](**args)` sem `asyncio.wait_for()` — se a tool travar, o broker trava para sempre.

#### 11. F-WA-02: Sem fsync no WORM audit (**corrigido — afirmação falsa removida**)
- **Arquivo**: `core/audit/worm_audit.py:185-191`
- **Mecanismo**: ~~"`_last_hash` atualizado ANTES de confirmar escrita em disco"~~ — **FALSO**. A ordem real é: L189 escreve (`f.write(line)`), L191 atualiza `_last_hash`. O bug real é a **ausência de `os.fsync()`** após `f.write()` — um crash do SO entre write e flush pode perder o registro, causando dessincronização da hash chain.
- **Evidência de correção**: Leitura direta de `worm_audit.py:185-191` confirma a ordem correta.

#### 12. F-DLP-04: Bypass de injection por Unicode
- **Arquivo**: `core/security/dlp_guardrail.py:178-188`
- **Mecanismo**: `_detect_injection(text)` roda regex no texto original sem normalização NFKC. Homoglifos (Cyrillic "а" em vez de Latin "a") e zero-width chars evadem os patterns.
- **Resolução**: PD-OVR-002 — normalizar NFKC apenas para injection scan.

#### 13. F-IP-01: Exceção em qualquer check bloqueia pipeline
- **Arquivo**: `core/integration/__init__.py:312-364`
- **Mecanismo**: Os checks em `pre_call_pipeline()` são chamados em sequência sem isolamento. Se um check levanta exceção, toda a chamada falha sem executar os demais checks.

#### 14. GAP-13: Spoofing de persona_id (**NOVO**)
- **Arquivo**: `core/broker.py:64` + `core/integration/__init__.py:101-107`
- **Mecanismo**: `persona_id` é uma string passada pelo chamador sem binding criptográfico. Qualquer caller pode declarar qualquer persona_id, obtendo os privilégios associados. Due Diligence Harness §6 manda reportar como gap de spoofing.

#### 15. GAP-10: 3 de 5 agentes sem persona (**NOVO**)
- **Arquivo**: `backend/orchestrator.py:41-45`
- **Mecanismo**: `AGENT_PERSONA_MAP` mapeia apenas `manager` → `maia-orchestrator` e `reviewer` → `eva-supervisor`. Os agentes `researcher`, `coder` e `writer` não têm mapeamento. `persona_id = AGENT_PERSONA_MAP.get(agent)` retorna `None` → todo o pipeline é ignorado (GAP-12).

#### 16. GAP-CB-01: HALF_OPEN permite thundering herd (**NOVO**)
- **Arquivo**: `core/resilience/circuit_breaker.py:99-109`
- **Mecanismo**: `allow_request()` retorna `True` para HALF_OPEN (L105-106) sem nenhum semáforo de slot único. Em ambiente concurrent, **todas as requisições simultâneas** passam pelo HALF_OPEN, causando thundering herd no serviço que está se recuperando.

#### 17. GAP-SS-01: FULL_ACCESS permite leitura cross-session (**NOVO**)
- **Arquivo**: `core/memory/session_store.py:26,74-114`
- **Mecanismo**: `ScopePolicy.FULL_ACCESS` (usado por `manager`) retorna todos os campos sem filtro (L104-105). Se o manager acessar uma sessão de outro agente, vê tudo incluindo PII.

#### 18. GAP-06: Tool results não passam por DLP (**NOVO**)
- **Arquivo**: `core/integration/__init__.py:367-408`
- **Mecanismo**: `post_call_pipeline()` faz CB + audit + output contract, mas **não executa DLP no resultado da tool**. Um resultado com PII (CPF, cartão) é logado no audit e retornado ao agente sem mascaramento.

#### 19. GAP-03: Shadowing de campos financeiros (**NOVO**)
- **Arquivo**: `core/policy/autonomy.py:153-160`
- **Mecanismo**: `_extract_amount()` busca campos em ordem fixa (`amount_fields = ("amount", "valor", "value", "total", "amount_brl")`), primeiro match ganha. Um payload `{"amount": 0, "valor": 90000}` → `amount=0` → APPROVE, enquanto `valor=90000` é ignorado.

### P2 — Bugs de Média Severidade (adiados)

#### 20. GAP-14: Rate Limiter antes do RBAC
- **Arquivo**: `core/integration/__init__.py:330-344`
- **Mecanismo**: Pipeline order é CB → RL → RBAC. Rate Limiter (L336) consome token **antes** de verificar se a persona tem permissão RBAC (L342). Atacante sem permissão consome tokens de rate limiting dos outros (ordering DoS).

#### 21. GAP-05: Pre-call deny executa post-call
- **Arquivo**: `core/broker.py:126-162`
- **Mecanismo**: Quando `pre_call_pipeline` bloqueia (tool não executada), `post_call_pipeline` executa no `finally` com `success=False`. Além de F-IP-05 (CB), isso grava audit trail para tools que nunca executaram.

#### 22. GAP-17: PIIs sobrepostas corrompem texto mascarado
- **Arquivo**: `core/security/dlp_guardrail.py:190-213`
- **Mecanismo**: `_mask_pii()` itera PII_RULES em ordem e substitui de trás para frente. Se um CPF e um CNPJ se sobrepõem no texto, os índices ficam inconsistentes e o texto é corrompido.

#### 23. GAP-18: PII patterns faltando (RG, CEP, CNH, PIX)
- **Arquivo**: `core/security/dlp_guardrail.py:17-51`
- **Mecanismo**: `_PII_RULES` cobre CPF, CNPJ, cartão, API key, email, telefone. Faltam: RG, CEP, CNH, chave PIX (email já coberto, mas falta CPF-PIX, telefone-PIX, aleatória).

#### 24. GAP-RL-01: OOM por criação ilimitada de buckets
- **Arquivo**: `core/resilience/rate_limiter.py` (via RateLimiterRegistry)
- **Mecanismo**: `try_acquire(tool_name)` cria um bucket por tool_name sob demanda. Nomes dinâmicos de tool criam buckets infinitos → OOM.

### P3 — Bugs de Baixa Severidade

#### 25. F-RL-04: Tokens negativos (**reclassificado de P1 para P3**)
- **Arquivo**: `core/resilience/rate_limiter.py:72-81`
- **Mecanismo**: `try_acquire(tokens=-5)` → `self._tokens >= -5` = True → `self._tokens -= (-5)` = adiciona 5 tokens.
- **Justificativa para P3**: `try_acquire()` não é exposto via WS. Requer acesso interno ao código. Vetor externo praticamente inexistente.

#### 26. F-SS-01: SessionStore sem lock (**reclassificado de P1 para P3**)
- **Arquivo**: `core/memory/session_store.py:58-128`
- **Mecanismo**: `SessionMemoryStore` não usa `threading.Lock` — race condition em multi-threaded.
- **Justificativa para P3**: O módulo **não é utilizado diretamente** pelo pipeline ativo. O pipeline é asyncio single-threaded. Risco futuro apenas.

### Adiados (fora do escopo desta sprint)

#### GAP-19: Evasão de injection por Base64/URL encoding/gramática PT-BR
- **Justificativa**: Requer research sobre adversarial ML e patterns de evasão. Escopo de sprint dedicada.

#### GAP-WA-02: JSON adulterado → continue silencioso
- **Arquivo**: `core/audit/worm_audit.py` (read_all/verify_chain)
- **Justificativa**: Requer decisão sobre política de recovery (fail-hard vs repair).

---

## Seção 3: Arquivos Envolvidos

### Escopo Ativo (P0 + P1)

| # | Arquivo | Linhas | Bugs |
|---|---------|--------|------|
| 1 | `core/policy/autonomy.py` | 162 | F-AU-01, F-AU-02, GAP-03 |
| 2 | `core/broker.py` | 164 | F-IP-05, F-BR-01, GAP-05 |
| 3 | `backend/orchestrator.py` | 507 | F-OR-05 |
| 4 | `core/gates/forbidden_topics_gate.py` | 115 | F-FT-01, GAP-FT-01 |
| 5 | `core/audit/worm_audit.py` | 301 | F-WA-02 |
| 6 | `core/security/dlp_guardrail.py` | 219 | F-DLP-04, GAP-06 |
| 7 | `core/integration/__init__.py` | 524 | F-IP-01, GAP-12, GAP-14 |
| 8 | `core/resilience/circuit_breaker.py` | 203 | GAP-CB-01 |
| 9 | `core/memory/session_store.py` | 128 | GAP-SS-01 |
| 10 | `backend/ws_server.py` | 236 | GAP-WS-01, GAP-HT-01 |
| 11 | `backend/tool_executor.py` | ~24 | GAP-13 (persona_id passthrough) |

### No-Touch Files (justificativa obrigatória)

| Arquivo | Justificativa |
|---------|---------------|
| `core/schema/persona_contract.py` | Nenhuma mudança necessária — schema não tem bug |
| `core/routing/moe_router.py` | Mudanças são P2 (sprint seguinte) — routing de persona |
| `core/governance/*.py` | Mudanças são P2/P3 — handoff/hitl protocol internals |

> ⚠️ **ws_server.py REMOVIDO do No-Touch**: É ponto de entrada externo sem autenticação (Due Diligence Harness §4). Inclui GAP-WS-01 (CSWSH) e GAP-HT-01 (HITL sem auth).

---

## Seção 4: Testes Existentes (Baseline)

```
882 passed, 16 failed, 1 warning — 35.54s
```

### 16 Testes Falhando (Análise Obrigatória — Due Diligence Harness §1)

Os 16 testes falhando estão em `tests/test_nexus_ws.py`:

| # | Teste | Classe | Tipo | Motivo da Falha |
|---|-------|--------|------|-----------------|
| 1 | `test_cross_origin_pages_cannot_connect` | TestWsServerProtocol | **Segurança (CSWSH)** | Mock `exec_tool` → `tool_executor` |
| 2 | `test_start_without_a_valid_mission_is_rejected` | TestWsServerProtocol | **Segurança (Input Val)** | Mock `exec_tool` → `tool_executor` |
| 3 | `test_empty_new_task_is_rejected` | TestWsServerProtocol | **Segurança (Input Val)** | Mock `exec_tool` → `tool_executor` |
| 4 | `test_no_mission_pattern_runs_a_host_command` | TestHostCommandsNeedHumanApproval | **Segurança (RCE gate)** | `AUTO_TOOLS` removido |
| 5 | `test_a_host_command_step_is_refused_without_calling_the_executor` | TestHostCommandsNeedHumanApproval | **Segurança (RCE gate)** | Mock `exec_tool` → `tool_executor` |
| 6 | `test_approve_without_a_mission_waiting_is_rejected` | TestWsServerProtocol | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 7 | `test_mission_events_use_the_mission_from_the_start_envelope` | TestWsServerProtocol | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 8 | `test_revisions_increase_across_missions` | TestWsServerProtocol | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 9 | `test_every_event_passes_the_frontend_decoder` | TestOrchestratorContract | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 10 | `test_distribute_event_uses_from_key` | TestOrchestratorContract | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 11 | `test_mission_ends_with_every_agent_done` | TestOrchestratorContract | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 12 | `test_run_mission_adopts_the_given_mission_id` | TestOrchestratorMissionId | Contrato de protocolo | Mock `exec_tool` → `tool_executor` |
| 13 | `test_ws_port_does_not_collide_with_the_bff` | TestWsServerPort | Infraestrutura | `PORT=8848 != 8849` |
| 14 | `test_include_content_adds_the_chunk_text` | TestRetrieverContent | Funcional | Mock desatualizado |
| 15 | `test_search_maps_retriever_fields` | TestToolExecutorSearch | Funcional | Mock desatualizado |
| 16 | `test_events_from_the_ws_server_reach_the_frontend_reducer` | TestEndToEndReducer | E2E | Mock `exec_tool` → `tool_executor` |

> [!CAUTION]
> **5 de 16 testes falhando são de SEGURANÇA** (CSWSH, RCE gate, input validation). Não podem ser aceitos como "pré-existentes" sem investigação. A falha é por mock desatualizado (`exec_tool → tool_executor`) ou referência a `AUTO_TOOLS` removido. **A correção do mock é pré-requisito para validar a cobertura de segurança do WebSocket.**

### Novos Testes Necessários

| Bug | Cenário de Teste |
|-----|-----------------|
| F-AU-01 | `"R$ 50.000,00"` → ESCALATE |
| F-AU-02 | `amount = -1000` → ESCALATE |
| F-IP-05 | RBAC deny NÃO abre Circuit Breaker |
| F-OR-05 | TTL não conta tempo de aprovação HITL |
| F-FT-01 | Word boundary no forbidden topics gate |
| F-BR-01 | Tool timeout via `asyncio.wait_for()` |
| F-WA-02 | `os.fsync()` chamado após write |
| F-DLP-04 | Unicode NFKC antes do injection scan |
| F-IP-01 | Pipeline check isolation (try/except individual) |
| GAP-FT-01 | `{"forbidden_topics": []}` não desliga o gate |
| GAP-WS-01 | `origins=` configurado no `websockets.serve()` |
| GAP-HT-01 | HITL_DECISION requer autenticação |
| GAP-12 | Pipeline executa mesmo sem persona_id para gates críticos |
| GAP-CB-01 | HALF_OPEN permite no máximo 1 requisição simultânea |
| GAP-SS-01 | FULL_ACCESS não permite cross-session |
| GAP-06 | DLP executa no resultado da tool |
| GAP-03 | Campos financeiros não permitem shadowing |

---

## Seção 5: Invariantes a Preservar

1. **Backward compatibility**: Callers sem `persona_id` devem funcionar identicamente ao comportamento atual (exceto para gates de segurança críticos — ver Q6).
2. **882 testes existentes**: Nenhum teste passando pode quebrar.
3. **API pública**: Assinaturas de funções públicas não devem mudar (exceto adição de parâmetros com defaults).
4. **WORM audit**: Hash-chain existente deve permanecer verificável por `verify_chain()`.
5. **Conventional Commits**: Em português, seguindo `fix: F-XX-NN — descrição`.
6. **Git workflow**: Branch `fix/security-hardening-p0-p1`, PR para `main`, nunca push direto.

---

## Seção 6: Decisões de Produto Tomadas

### PD-OVR-001: F-IP-05 × F-BR-01 — Implementação Independente
**Arquivo**: `docs/product-decisions/PD-OVR-001-ip05-br01-independentes.md`
**Decisão**: Implementar F-IP-05 e F-BR-01 de forma independente. Sem conflito no `finally` do `broker.py`.

### PD-OVR-002: Unicode Normalization — Apenas Injection Scan
**Arquivo**: `docs/product-decisions/PD-OVR-002-unicode-apenas-injection.md`
**Decisão**: Normalizar NFKC apenas para injection scan no DLP. PII masking opera no texto original.

### PD-OVR-003: TTL Reset — Fix Mínimo
**Arquivo**: `docs/product-decisions/PD-OVR-003-ttl-reset-apos-hitl.md`
**Decisão**: Resetar `mission_start` após aprovação HITL. TTL fixo 30s. Configurável por persona adiado para P2.

---

## Seção 7: Riscos & Premissas

### Riscos

| # | Risco | Severidade | Mitigação |
|---|-------|------------|-----------|
| R1 | Mudar `broker.py:finally` pode afetar rastreabilidade | Médio | Garantir que `post_call_pipeline` executa quando tool FOI executada, NÃO quando pre_call bloqueou |
| R2 | Timeout de tool (F-BR-01) pode cortar operações legítimas lentas | Médio | Usar timeout generoso (15s) e documentar como override por persona |
| R3 | Word boundary em forbidden topics pode ser insuficiente para frases compostas | Baixo | Testar com todos os forbidden topics existentes nos 5 BUILTIN_CONTRACTS |
| R4 | Normalização Unicode no DLP pode afetar matching de PII | Baixo | PD-OVR-002 — normalização apenas para injection, PII no original |
| R5 | Corrigir 5 testes de segurança em test_nexus_ws.py pode revelar bugs adicionais | Médio | Escopo de correção limitado a atualizar mocks (exec_tool → tool_executor) |
| R6 | GAP-12 (fail-open) requer decisão fundamental sobre backward compatibility | Alto | Q6 — precisa PD-OVR na Fase 2 (fail-closed para security gates) |
| R7 | ws_server.py sem auth pode ter mais vetores além de CSWSH/HITL | Médio | Auditoria completa do handler na Fase 2 |

### Premissas

- Deploy é single-process (asyncio). Multi-process (gunicorn) é futuro.
- O file lock do WORM (F-WA-01) é adiado para P2 (requer decisão sobre single vs multi-process).
- Os 16 testes falhando em `test_nexus_ws.py` devem ter seus mocks corrigidos como pré-requisito (5 são testes de segurança).

### Hipóteses Descartadas

| # | Hipótese | Evidência de Descarte |
|---|----------|----------------------|
| H1 | "O problema de TTL é cosmético — o Orchestrator nunca pede aprovação HITL" | **Descartada**: L254-260 do orchestrator.py mostra que `guard["action"] == "approval"` dispara `_wait_approval()`. |
| H2 | "O CB cross-contamination só acontece com persona_id" | **Descartada**: `broker.py:148` — o `finally` roda SEMPRE com persona_id. Sem persona_id o pipeline não roda, mas COM persona_id e pre_call deny, post_call roda. |
| H3 | "O rate limiter com tokens negativos requer acesso interno ao código" | **Confirmada como baixo risco (P3)**: `try_acquire()` não é exposto via WS. |
| H4 | "A vulnerabilidade F-AU-01 requer persona com conditional_hitl" | **Confirmada**: Apenas `persona-finops` tem `conditional_hitl`. Risco limitado a 1 persona. |
| H5 | "O Session Store sem lock é seguro porque asyncio é single-threaded" | **Parcialmente descartada**: asyncio é single-threaded, mas `threading.Lock` é usado em TODOS os outros módulos. Módulo não utilizado pelo pipeline ativo → P3. |
| H6 | "F-WA-02: _last_hash é atualizado ANTES da escrita em disco" | **DESCARTADA (FALSO POSITIVO)**: L189 escreve, L191 atualiza. Bug real = falta de fsync. |
| H7 | "ReDoS no DLP é possível" | **DESCARTADA**: Regex testada com 50k chars, <4ms. Complexidade O(N). |
| H8 | "Step Name Injection no orchestrator é possível" | **DESCARTADA**: Steps vêm de `MISSION_PATTERNS` (lista estática hardcoded, não injetável pelo usuário). |

---

## Seção 8: Referências & Evidências

| Artefato | Caminho |
|----------|---------|
| Evidências 3D (original + lacunas) | `docs/superpowers/evidence/2026-10-15-security-hardening-evidence.md` |
| PD-OVR-001 | `docs/product-decisions/PD-OVR-001-ip05-br01-independentes.md` |
| PD-OVR-002 | `docs/product-decisions/PD-OVR-002-unicode-apenas-injection.md` |
| PD-OVR-003 | `docs/product-decisions/PD-OVR-003-ttl-reset-apos-hitl.md` |
| Reproduções de bugs | Comandos inline executados em `c:\KIOSK\second-brain` com output real |
| Simulador MoE (referência) | `simulador_de_governan_a_e_orquestra_o_multi_agentes_moe.tsx` |
| CHANGELOG-MOE.md | `CHANGELOG-MOE.md` |
| Tag v1.0.0-moe | `git tag v1.0.0-moe` (commit `59ad40b`) |
| Auditoria adversarial | Contexto do handoff v2.0 — 3 agentes independentes |

---

## Seção 9: Queries & Verificações Pendentes para Fase 2

1. **Q1**: O `asyncio.wait_for()` em F-BR-01 deve gerar `asyncio.TimeoutError`. Como deve ser tratado? Sugestão: capturar como `{"error": "ToolTimeout"}` e contar como failure no CB.

2. **Q2**: Em F-IP-05, quando `pre_call` bloqueia, o `post_call_pipeline` não deve executar de todo, ou deve executar parcialmente (ex: audit sim, CB não)?

3. **Q3**: Em F-AU-01, qual o comportamento correto quando `_extract_amount` encontra o campo mas não parseia? Sugestão: retornar sentinel `UNPARSEABLE` em vez de `None`, e tratar como ESCALATE.

4. **Q4**: O TTL de F-OR-05 deve ser configurável por persona (via PersonaContract) ou fixo? **Parcialmente resolvido**: TTL fixo 30s agora (PD-OVR-003), configurável por persona adiado para P2.

5. ~~**Q5**: A normalização Unicode de F-DLP-04 deve ser aplicada também ao texto mascarado (redacted), ou apenas ao scan de injection?~~ **Resolvido**: Apenas injection scan (PD-OVR-002).

6. **Q6 (G3)**: Definir política formal de fail-open vs fail-closed para cada gate do pipeline. Recomendação: **fail-closed** para gates de segurança (RBAC, DLP, ForbiddenTopics) e **fail-open** para gates de resiliência (CB, RL). Precisa formalizar como PD-OVR na Fase 2.

7. **Q7 (NOVO)**: Como tratar os 5 testes de segurança falhando em `test_nexus_ws.py`? Corrigir mocks como pré-requisito ou adiar? Recomendação: corrigir mocks como parte desta sprint — são testes de CSWSH, RCE gate e input validation.

8. **Q8 (NOVO)**: GAP-FT-01 — o gate deve ter uma lista **base** imutável de forbidden topics que não pode ser sobrescrita pelo payload? Ou a sobrescrita deve ser tratada como merge?

9. **Q9 (NOVO)**: GAP-12 — qual a política para callers sem persona_id? Opções: (a) fail-closed — rejeitar, (b) persona default com permissões mínimas, (c) executar apenas gates de segurança sem persona-specific checks.

10. **Q10 (NOVO)**: GAP-WS-01 — deve-se implementar autenticação por token WS, ou apenas validação de Origin é suficiente para o escopo atual?

---

## Seção 10: Critério de Conclusão da Próxima Fase

A Fase 2 (Spec Gate) estará completa quando:

1. [ ] Spec formal em `docs/superpowers/specs/2026-10-15-security-hardening-spec.md`
2. [ ] Invariantes negativos documentados (o que é PROIBIDO fazer)
3. [ ] Queries Q1-Q4, Q6-Q10 respondidas com decisão documentada (Q5 já resolvido)
4. [ ] Política formal fail-open/fail-closed definida como PD-OVR
5. [ ] Aprovação formal humana para prosseguir ao plano
6. [ ] Handoff para Fase 3

---

## Apêndice A: Blast Radius por Módulo

| Módulo | Consumidores Diretos | Impacto de Mudança | Portas Expostas |
|--------|---------------------|-------------------|-----------------|
| `ws_server.py` | Frontend (ws://127.0.0.1:8848) | **CRÍTICO** — ponto de entrada | WS 8848, sem auth |
| `broker.py` | `tool_executor.py`, `mission_guard.py` | **ALTO** — ponto central | Nenhuma |
| `integration/__init__.py` | `broker.py`, `orchestrator.py`, `ws_server.py` | **ALTO** — pipeline completo | Nenhuma |
| `orchestrator.py` | `ws_server.py` | **ALTO** — async generator | Nenhuma |
| `autonomy.py` | `integration/__init__.py` via `check_autonomy()` | MÉDIO — 1 caller | Nenhuma |
| `rate_limiter.py` | `integration/__init__.py` via `check_rate_limit()` | MÉDIO — 1 caller | Nenhuma |
| `forbidden_topics_gate.py` | `integration/__init__.py` via `_get_forbidden_gate()` | MÉDIO — 1 caller | Nenhuma |
| `circuit_breaker.py` | `integration/__init__.py` via `_get_cb_registry()` | MÉDIO — 1 caller | Nenhuma |
| `worm_audit.py` | `integration/__init__.py` via `_get_audit_log()` | MÉDIO — 1 caller | Nenhuma |
| `dlp_guardrail.py` | `broker.py` (pré-LLM) | MÉDIO — 1 caller | Nenhuma |
| `session_store.py` | **Não utilizado** pelo pipeline ativo | BAIXO — futuro | Nenhuma |

## Apêndice B: Falsos Positivos da Discovery Original (Removidos)

| ID | Afirmação Original | Evidência de Descarte |
|----|--------------------|-----------------------|
| FP-1 | F-WA-02: "_last_hash atualizado ANTES do disco" | **FALSO**: L189 escreve, L191 atualiza. Bug real = fsync. |
| FP-2 | ReDoS no DLP | **FALSO**: Regex testada com 50k chars, <4ms. Complexidade O(N). |
| FP-3 | Step Name Injection no orchestrator | **FALSO**: Steps vêm de MISSION_PATTERNS estático. |

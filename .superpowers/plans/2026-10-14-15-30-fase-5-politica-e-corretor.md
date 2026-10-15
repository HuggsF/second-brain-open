# Fase 5: política única e corretor de ferramentas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Todo acesso a ferramenta por agente passa por uma política (`core/policy/`) e um corretor (`core/broker.py`), os portões validam a missão antes de ela começar, e cada chamada deixa rastro com a identidade `agent:<papel>`.

**Architecture:** `core/policy/` são funções puras (classe da ferramenta, permissão do papel, regras de comando) que devolvem `Verdict`. `core/tools.py` guarda as implementações das ferramentas (movidas de `backend/tool_executor.py`, sem política). `core/broker.py` decide, executa e grava rastro. `backend/tool_executor.py` vira adaptador fino sobre o corretor, e o orquestrador e o `ws_server` passam a usar o corretor, os portões e `validate_mission_envelope`.

**Tech Stack:** Python 3.14, pytest (já em `requirements.txt`), FastMCP (só os servidores existentes), SQLite via `core/evidence_store.py`, sem dependência nova.

**Spec:** `.superpowers/specs/2026-10-14-13-55-multiagent-platform-design.md` (seções 5, 6.2, 6.3, 7 Fase 5, 8)

## Global Constraints

- `core/policy/` é puro: sem I/O, sem rede, sem import de `backend/` nem de `mcp_servers/` (D1).
- Veredito fecha para negar: qualquer erro, formato inválido ou ferramenta fora do registro vira `DENY` (D3, "fail-closed").
- Quatro classes: `READ`, `WRITE_LOCAL`, `PROD_READ`, `PROD_MUTATING` (D4). `PROD_MUTATING` nunca é `APPROVE`.
- Shell genérico não é ferramenta automática de agente; `sqlite3` fora da lista genérica (D5).
- Identidade do agente: `agent:<role>` ou `agent:<role>/<specialty>`; papéis = `ALLOWED_ROLES`; especialidades = `DEV`, `DEVOPS`, `QA`, `PRODUTO` (D6).
- `task_id` da missão = `"M<missionId>"` (D7).
- Resultado e rastro nunca carregam segredo; em erro guarda-se só o nome da classe da exceção.
- Notas do vault novas ficam em CRLF; o snapshot do dashboard é regenerado de um checkout limpo (`python dashboard/build_graph.py`).
- Nenhuma lista de comandos permitidos fora de `core/policy/`.
- Portões ligados: RED bloqueia a missão, YELLOW vira pedido de aprovação, GREEN segue (6.3).
- Linha de base a manter verde: 419 testes Python, 72 de domínio e portões, suíte Node do dashboard (117 de 119, os 2 vermelhos conhecidos de UX ficam como estão).
- Trabalhar numa branch nova a partir de `main` (`feat/fase-5-politica-e-corretor`), em worktree limpo. A pasta de trabalho do dono tem 34 caminhos não commitados (spec O2): não editar lá.

## Review Focus

- Passo do orquestrador com `tool` que não é texto, ou `input` que não é objeto: o corretor responde `DENY`/`malformed_args`, não levanta exceção (Task 3).
- `run_safe_command` com `command` contendo quebra de linha, caractere de controle ou `sqlite3 x.db "delete ..."`: `DENY`, nunca executa (Task 1).
- Ferramenta que falha com mensagem contendo token ou chave de NF: o resultado e a linha do rastro trazem só o nome da classe (Task 3).
- `missionId` booleano, zero, `2**53` ou texto no WebSocket: `REJECT`, sem iniciar missão (Task 6).
- Arquivo de rastro que não pode ser gravado: o corretor ainda devolve o veredito e o resultado, sem lançar e sem transformar `DENY` em `APPROVE` (Task 3).

---

### Task 1: Pacote `core/policy/` (classes, vereditos, identidade, comandos, `decide`)

**Files:**
- Create: `core/policy/__init__.py`, `core/policy/classes.py`, `core/policy/verdict.py`, `core/policy/identity.py`, `core/policy/commands.py`, `core/policy/decide.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes: `core.domain.nexus.entities.ALLOWED_ROLES`, `TOOL_REGISTRY`.
- Produces:
  - `ToolClass(str, Enum)`: `READ`, `WRITE_LOCAL`, `PROD_READ`, `PROD_MUTATING`.
  - `TOOL_CLASSES: Dict[str, ToolClass]` com: `search_knowledge_base`, `get_adr`, `get_brain_status`, `list_rules`, `get_rule_evidence`, `get_system_architecture`, `read_vault_file` = `READ`; `record_test_execution` = `WRITE_LOCAL`; `run_safe_command` = `PROD_READ`.
  - `Decision(str, Enum)`: `APPROVE`, `ESCALATE`, `DENY`. `Reason(str, Enum)` (vocabulário fechado): `read_auto`, `write_local_traced`, `prod_read_needs_human`, `prod_mutating_never_auto`, `unknown_tool`, `role_not_allowed`, `bad_identity`, `command_refused`, `malformed_args`, `policy_error`. `@dataclass(frozen=True) Verdict(decision: Decision, reason: Reason, detail: str = "")`.
  - `SPECIALTIES: frozenset` (`DEV`, `DEVOPS`, `QA`, `PRODUTO`); `make_identity(role: str, specialty: Optional[str] = None) -> str` (levanta `ValueError` se inválido); `parse_identity(identity: object) -> Optional[Tuple[str, Optional[str]]]` (`None` se inválido).
  - Em `commands.py`: `READ_ONLY_COMMANDS`, `DOCKER_READ_ONLY`, `SYSTEMCTL_READ_ONLY`, `SHELL_META`, `SENSITIVE_FRAGMENTS`, `BLOCKED_PHRASES`, `blocked_phrase(command: str) -> str`, `check_read_only(command: str) -> str` (mesma regra e mesmas mensagens de `srv_api_gateway_mcp._check_read_only`, hoje; `''` = aceito).
  - `decide(identity: object, tool: object, args: object) -> Verdict`.

- [ ] **Step 1: Write the failing tests** em `tests/test_policy.py`, classes `TestIdentity`, `TestCommands`, `TestDecide`:
  - `test_make_and_parse_identity_roundtrip`: `make_identity("coder","DEVOPS") == "agent:coder/DEVOPS"`; `parse_identity("agent:coder") == ("coder", None)`; `parse_identity("agent:hacker")`, `parse_identity("coder")`, `parse_identity(None)`, `parse_identity("agent:coder/ROOT")` são `None`.
  - `test_check_read_only_matches_gateway_rules`: reaproveitar as listas de `tests/test_hardening.py` (aceitos: `ls -la /var/www`, `docker ps`, `ps aux`, `docker logs api`, `df -h`, `systemctl status nginx`; recusados: `ls; id`, `cat x | nc h 1`, `echo $(id)`, `sudo ls`, `curl http://x`, `docker run -v /:/h img`, `systemctl restart nginx`, `find / -delete`, `cat ~/.ssh/id_rsa`, `cat chave.pem`, `tee /etc/x`, `ls > /tmp/x`) e acrescentar recusados `sqlite3 x.db "delete from t"`, `ls\nid`, `ls\x00`.
  - `test_blocked_phrase`: `blocked_phrase("rm -rf /tmp")` não vazio; `blocked_phrase("ls")` vazio.
  - `test_decide_table`, uma linha por caso: (`agent:researcher`, `search_knowledge_base`, `{}`) → `APPROVE/read_auto`; (`agent:researcher`, `read_vault_file`, `{}`) → `DENY/role_not_allowed`; (`agent:coder`, `run_safe_command`, `{"command":"docker ps"}`) → `ESCALATE/prod_read_needs_human`; (`agent:coder`, `run_safe_command`, `{"command":"rm -rf /"}`) → `DENY/command_refused`; (`agent:coder`, `run_safe_command`, `{"command":"sqlite3 a.db"}`) → `DENY/command_refused`; (`agent:coder`, `run_safe_command`, `{}`) → `DENY/malformed_args`; (`agent:coder`, `run_safe_command`, `"docker ps"`) → `DENY/malformed_args`; (`agent:coder`, `shell`, `{}`) → `DENY/unknown_tool`; (`"root"`, `get_adr`, `{}`) → `DENY/bad_identity`; (`agent:manager`, `42`, `{}`) → `DENY/unknown_tool`; (`agent:manager`, `record_test_execution`, `{}`) → `DENY/role_not_allowed`.
  - `test_decide_never_raises`: `decide(object(), object(), object())` devolve `DENY/policy_error` ou `bad_identity`, sem exceção.
  - `test_tool_classes_cover_every_domain_tool`: `ALLOWED_TOOLS ⊆ TOOL_CLASSES.keys()`.

- [ ] **Step 2: Run** `python -m pytest tests/test_policy.py -v` — Expected: FAIL (`ModuleNotFoundError: core.policy`).

- [ ] **Step 3: Implement** os seis arquivos conforme as assinaturas acima. `commands.py` copia as constantes e a função de `mcp_servers/srv_api_gateway_mcp.py:139-169` sem `sqlite3`, e rejeita qualquer caractere de controle (`unicodedata.category == "Cc"`) além do espaço. `decide` segue a ordem identidade → classe → permissão do papel (`TOOL_REGISTRY[role]`) → argumentos (só `run_safe_command`: `args` dict com `command` texto; `blocked_phrase` e `check_read_only`) → classe decide (`READ` e `WRITE_LOCAL` `APPROVE`; `PROD_READ` `ESCALATE`; `PROD_MUTATING` `DENY`); tudo dentro de `try/except Exception` devolvendo `DENY/policy_error`.

- [ ] **Step 4: Run** `python -m pytest tests/test_policy.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/policy tests/test_policy.py
git commit -m "feat(policy): política única de ferramentas (classes, vereditos, identidade, comandos)"
```

### Task 2: Registro de ferramentas igual à realidade e `core/tools.py`

**Files:**
- Create: `core/tools.py`, `scripts` não muda; regenerar `nexus/src/generated/nexus-entities.json`
- Modify: `core/domain/nexus/entities.py` (`TOOL_REGISTRY`, comentário de `AUTO_TOOLS`), `tests/test_gates.py:49-64`, `tests/test_domain_entities.py:89`, `tests/test_domain_workflow.py:63`
- Test: `tests/test_tools.py`, `tests/test_policy_registry.py`

**Interfaces:**
- Consumes: as funções hoje em `backend/tool_executor.py` (`search_knowledge`, `get_adr`, `get_brain_status`, `list_rules_with_evidence`, `get_system_doc`, `read_vault_file`).
- Produces:
  - `core/tools.py`: as mesmas seis funções `async`, movidas sem mudar o resultado, mais `async get_rule_evidence(rule_id: str) -> dict` e `async run_safe_command(command: str) -> dict` (esta importa `_exec_command` de `mcp_servers.srv_api_gateway_mcp` de forma tardia e devolve `{"tool","success","exit_code","stdout","stderr","command"}`; sem `paramiko` instalado devolve `success: False` com erro textual). `IMPLEMENTATIONS: Dict[str, Callable]` com as oito chaves de `TOOL_CLASSES` exceto `record_test_execution`.
  - `TOOL_REGISTRY` novo (decisão desta fase): `manager` mantém as quatro; `researcher` igual; `coder` = `search_knowledge_base`, `read_vault_file`, `get_system_architecture`, `run_safe_command`; `writer` = `search_knowledge_base`, `read_vault_file`, `get_adr`; `reviewer` = `search_knowledge_base`, `get_adr`, `get_rule_evidence`. Saem `run_tests` (o runner fica fora do repositório), `validate_plan` e `write_doc` (nenhum código as provê; relatórios não escrevem no vault).

- [ ] **Step 1: Write the failing tests**
  - `tests/test_policy_registry.py::test_registry_matches_implementations`: `ALLOWED_TOOLS == set(IMPLEMENTATIONS)`; `AUTO_TOOLS == {t for t in ALLOWED_TOOLS if TOOL_CLASSES[t] in (READ, WRITE_LOCAL)}`; `"run_safe_command" not in AUTO_TOOLS`.
  - `tests/test_tools.py::test_get_rule_evidence_returns_rule_state` (com `RULE-001` real do vault: chaves `tool`, `rule_id`, `state`, `playbooks`), `::test_get_rule_evidence_unknown_rule` (`found: False`), `::test_run_safe_command_without_ssh_module` (mock do import → `success False`, sem exceção).
  - Atualizar nos testes existentes as ferramentas removidas por ferramentas que continuam no registro (`validate_plan` → `get_rule_evidence`, `run_tests` → `run_safe_command`), mantendo o que cada teste prova (DAG válido, ciclo).

- [ ] **Step 2: Run** `python -m pytest tests/test_policy_registry.py tests/test_tools.py tests/test_gates.py tests/test_domain_entities.py tests/test_domain_workflow.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement** `core/tools.py` (mover o código, `get_rule_evidence` usa `evidence.load_definitions()` e `EvidenceStore` como `list_rules_with_evidence`), editar `TOOL_REGISTRY`, depois `python scripts/generate_nexus_entities.py`.

- [ ] **Step 4: Run** a mesma linha — Expected: PASS. Rodar também `python -m pytest -q` — Expected: sem regressão (o `tool_executor` ainda importa suas cópias; serão trocadas na Task 4).

- [ ] **Step 5: Commit**

```bash
git add core/tools.py core/domain/nexus/entities.py nexus/src/generated/nexus-entities.json tests
git commit -m "feat(domain): registro de ferramentas igual à implementação; get_rule_evidence e core/tools"
```

### Task 3: Corretor `core/broker.py`

**Files:**
- Create: `core/broker.py`
- Test: `tests/test_broker.py`

**Interfaces:**
- Consumes: `core.policy.decide`, `Verdict`, `Decision`; `core.tools.IMPLEMENTATIONS`; `core.tracing` (`derive_trace_id`, `new_span_id`, `write_record`, `CallState`, `current_call`, `now_iso`, `redact_args`).
- Produces:
  - `async call(identity: str, tool: str, args: dict, task_id: Optional[str] = None, *, approved: bool = False, trace_path: Optional[Path] = None) -> dict`. Retorno: `{"tool", "verdict": "APPROVE|ESCALATE|DENY", "reason", ...resultado da ferramenta...}`. `DENY` → `{"refused": True, "error": <reason>}` sem executar. `ESCALATE` e `approved=False` → `{"approval_required": True, "refused": True, "error": "exige aprovação humana"}` sem executar. `ESCALATE` e `approved=True` → executa (a aprovação humana vale só para essa chamada). Erro na ferramenta → `{"error": "<NomeDaClasse>"}`.
  - `record_event(identity: str, event: str, status: str, args: Optional[dict] = None, task_id: Optional[str] = None, trace_path: Optional[Path] = None) -> None` grava um evento solto no rastro (usado pelos portões, Task 5); nunca lança.
  - Rastro: uma linha `event: "call"`, `server: "broker"`, `caller: identity`, `status` `ok|error|refused|escalated`, `args` por `redact_args`, `task_label` derivado de `task_id`. Durante a execução, `current_call` fica definido para que `emit_child("ssh.exec", ...)` do gateway se anexe à chamada.

- [ ] **Step 1: Write the failing tests** (`unittest.IsolatedAsyncioTestCase`, rastro num diretório temporário passado em `trace_path`, ferramentas trocadas com `mock.patch.dict(IMPLEMENTATIONS, ...)`):
  - `test_approve_executes_and_traces_identity`: `call("agent:researcher","get_adr",{"identifier":"ADR-003"},"M7")` devolve `verdict == "APPROVE"` e uma linha no rastro com `caller == "agent:researcher"`, `tool == "get_adr"`, `task_label == "M7"`, `status == "ok"`.
  - `test_deny_does_not_execute`: ferramenta falsa não é chamada para `("agent:researcher","read_vault_file",{})`; `status == "refused"`.
  - `test_escalate_without_approval_does_not_execute`, `test_escalate_with_approval_executes` (`run_safe_command` falso).
  - `test_denied_command_never_executes_even_if_approved`: `approved=True` com `{"command":"rm -rf /"}` continua `DENY` e não executa.
  - `test_tool_error_keeps_only_class_name`: ferramenta levanta `RuntimeError("token=abc123 CPF 123.456.789-09")`; resultado e arquivo de rastro não contêm `abc123` nem `123.456.789-09`; `error == "RuntimeError"`.
  - `test_malformed_input_never_raises`: `call("agent:coder", 42, "x", None)` devolve `verdict == "DENY"` sem exceção.
  - `test_unwritable_trace_does_not_change_verdict`: `trace_path` apontando para um diretório; o veredito e o resultado continuam corretos.
  - `test_child_events_attach_to_call`: ferramenta falsa chama `tracing.emit_child("ssh.exec","ok",{"command":"docker ps","exit_code":0})` e o rastro contém o filho com `parent_span_id` igual ao `span_id` da chamada.

- [ ] **Step 2: Run** `python -m pytest tests/test_broker.py -v` — Expected: FAIL (`ModuleNotFoundError: core.broker`).

- [ ] **Step 3: Implement** `core/broker.py`. Escrever a linha de rastro depois da execução, no `finally`, dentro de `try/except` que só imprime em `stderr` (como em `core/trace_middleware.py`). Argumentos `args` que não forem `dict` são tratados antes de `decide` como `malformed_args`.

- [ ] **Step 4: Run** `python -m pytest tests/test_broker.py tests/test_policy.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/broker.py tests/test_broker.py
git commit -m "feat(broker): corretor único que decide, executa e grava rastro com identidade do agente"
```

### Task 4: Executor vira adaptador; orquestrador e gateway usam política e corretor

**Files:**
- Modify: `backend/tool_executor.py` (reduzir a adaptador), `backend/orchestrator.py` (`run_mission`, loop dos passos), `mcp_servers/srv_api_gateway_mcp.py:139-190`
- Test: `tests/test_no_local_allowlist.py`, `tests/test_ws_server.py` (casos novos), `tests/test_hardening.py` (continua passando sem mudança)

**Interfaces:**
- Consumes: `core.broker.call`; `core.policy.commands` (`check_read_only`, `blocked_phrase`, `READ_ONLY_COMMANDS` etc.).
- Produces:
  - `backend.tool_executor.execute(tool_name: str, *, identity: str = "agent:manager", task_id: Optional[str] = None, approved: bool = False, **kwargs) -> dict` = `await broker.call(identity, tool_name, kwargs, task_id, approved=approved)`. `TOOLS` deixa de existir.
  - Gateway: `_check_read_only`, `_READ_ONLY_COMMANDS`, `_DOCKER_READ_ONLY`, `_SYSTEMCTL_READ_ONLY`, `_SHELL_META` continuam existindo como aliases importados de `core.policy.commands` (para `tests/test_hardening.py`), e a lista `forbidden` local é substituída por `blocked_phrase`.
  - Orquestrador: cada passo chama `exec_tool(step["tool"], identity=make_identity(step["agent"]), task_id=f"M{self.mission_id}", **step["input"])`; o ramo `if step["tool"] in AUTO_TOOLS` some, a decisão é do corretor. Resultado com `refused` mantém a mensagem atual de "exige aprovação humana" no balão.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_no_local_allowlist.py::test_no_command_allowlist_outside_policy`: percorre `backend/`, `core/` (exceto `core/policy/`) e `mcp_servers/` e falha se algum `.py` contém literal `"journalctl"` ou `'journalctl'` ou `"systemctl"` entre aspas (a lista de comandos só existe em `core/policy/commands.py`).
  - `tests/test_ws_server.py::test_orchestrator_calls_carry_agent_identity_and_mission_task_id`: roda `diagnosticar erro no hub` com `mission_id=42` e `trace_path` temporário (patch de `tracing.TRACE_LOG`); todas as linhas `server == "broker"` têm `caller` começando em `agent:` e `task_label == "M42"`.
  - `::test_orchestrator_refuses_run_safe_command_step_without_executing`: injeta um passo `{"agent":"coder","tool":"run_safe_command","input":{"command":"docker ps"}}` (patch de `_match_pattern`), a ferramenta SSH falsa não é chamada e há `message` no evento dizendo que exige aprovação.
  - `tests/test_hardening.py` inalterado deve passar.

- [ ] **Step 2: Run** `python -m pytest tests/test_no_local_allowlist.py tests/test_ws_server.py tests/test_hardening.py -v` — Expected: FAIL nos dois testes novos e no guarda.

- [ ] **Step 3: Implement** as três edições. O executor mantém no máximo `execute`; as implementações já estão em `core/tools.py` (Task 2).

- [ ] **Step 4: Run** `python -m pytest -q` — Expected: tudo passa (419 + os novos).

- [ ] **Step 5: Commit**

```bash
git add backend mcp_servers tests
git commit -m "refactor: executor vira adaptador do corretor; gateway usa a política única"
```

### Task 5: Portões ligados ao início da missão

**Files:**
- Create: `core/mission_guard.py`
- Modify: `backend/orchestrator.py` (`run_mission`, antes de "Executar cada step")
- Test: `tests/test_mission_guard.py`, `tests/test_ws_server.py` (casos novos)

**Interfaces:**
- Consumes: `core.gates.CompoundGatePipeline`, `core.broker.record_event`.
- Produces:
  - `build_plan(steps: List[dict]) -> dict`: `{"version": 1, "steps": [{"id": "s1", "role": agent, "dependsOn": ["s0"...], "tools": [tool], "budgetSeconds": 30}, ...]}` (cada passo depende do anterior).
  - `check_mission(steps: List[dict], mission_id: int, pipeline: Optional[CompoundGatePipeline] = None) -> dict` com `{"action": "proceed"|"approval"|"block", "semaphore": "GREEN|YELLOW|RED", "gate_results": [...]}`: RED → `block`, YELLOW → `approval`, GREEN → `proceed`; qualquer exceção do pipeline → `block`. Grava o resultado como evento `gate.pipeline` no rastro, `caller = "agent:manager"`, `task_id = f"M{mission_id}"`.
  - Orquestrador: `block` → um evento `message` do `manager` com o motivo e a missão termina sem executar passo algum; `approval` → emite `approval_request` do `manager`, espera `approve()` (mesmo timeout de 300 s) e só então segue; `proceed` segue.

- [ ] **Step 1: Write the failing tests**
  - `test_valid_pattern_is_green_and_proceeds`: passos do padrão `diagnosticar` → `action == "proceed"`.
  - `test_unknown_tool_is_red_and_blocks`: passo com `tool == "drop_table"` → `block`, `semaphore == "RED"`.
  - `test_unknown_role_is_red`: papel `hacker`.
  - `test_yellow_requires_approval`: pipeline falso cujo `run_all` devolve `global_semaphore: "YELLOW"` → `approval`.
  - `test_pipeline_exception_blocks`: pipeline falso que levanta `RuntimeError` → `block`.
  - `test_gate_result_is_recorded_in_trace`: linha `event == "gate.pipeline"`, `task_label == "M9"`.
  - Em `test_ws_server.py`: `test_mission_with_unknown_tool_is_blocked_before_any_step` (nenhuma linha `call` no rastro, evento `message` do `manager`), `test_yellow_mission_waits_for_approval` (patch de `check_mission` devolvendo `approval`; sem `approve()` o gerador espera, com `approve()` termina).

- [ ] **Step 2: Run** `python -m pytest tests/test_mission_guard.py tests/test_ws_server.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement** `core/mission_guard.py` e a chamada em `run_mission` logo depois de `steps = self._match_pattern(task)`.

- [ ] **Step 4: Run** `python -m pytest -q` — Expected: tudo passa.

- [ ] **Step 5: Commit**

```bash
git add core/mission_guard.py backend/orchestrator.py tests
git commit -m "feat(gates): portões rodam antes da missão; RED bloqueia, YELLOW pede aprovação"
```

### Task 6: `ws_server` usa `validate_mission_envelope`

**Files:**
- Modify: `backend/ws_server.py:71-90` (ramo `NEW_TASK`)
- Test: `tests/test_ws_server.py`

**Interfaces:**
- Consumes: `core.domain.workflow.entities.validate_mission_envelope(message) -> Optional[str]`.
- Produces: ramo `NEW_TASK` monta `{"mission": {"id": missionId, "task": task}}`, valida, e em erro responde `REJECT` com `reason` igual à mensagem, sem ACK e sem iniciar missão. `missionId` ausente continua valendo `1`.

- [ ] **Step 1: Write the failing tests** (com `DummyWebSocket` e o `handler` já usados no arquivo): `test_new_task_with_invalid_mission_id_is_rejected` para `True`, `0`, `2**53`, `"abc"`, `-3`; `test_new_task_over_4000_chars_is_rejected`; `test_new_task_valid_still_acks`. O `REJECT` contém `reason` e `missionId`.

- [ ] **Step 2: Run** `python -m pytest tests/test_ws_server.py -v` — Expected: FAIL nos novos.

- [ ] **Step 3: Implement** a validação no ramo `NEW_TASK`, trocando a checagem `not task_text or not isinstance(task_text, str)` por ela (a mensagem "Empty task" continua vindo de `validate_mission_envelope` como "mission.task must be a non-empty string"; ajustar o teste antigo que espera "Empty task", se houver, para o novo texto).

- [ ] **Step 4: Run** `python -m pytest -q` — Expected: tudo passa.

- [ ] **Step 5: Commit**

```bash
git add backend/ws_server.py tests/test_ws_server.py
git commit -m "feat(ws): NEW_TASK valida o envelope pelo domínio (ADR-020)"
```

### Task 7: ADR-022, documentação e verificação final

**Files:**
- Create: `vault/adrs/ADR-022-politica-unica-e-corretor-de-ferramentas.md` (CRLF, frontmatter `type: adr`, `scope: second-brain`, `status: Aceito`, `date`, `related: [ADR-012, ADR-017, ADR-020, ADR-021]`)
- Modify: `CLAUDE.md` (seção de ADRs: "ADR-001 to ADR-022", e uma linha que aponta para `core/policy/` como único lugar de listas de comandos), `dashboard/graph-data.js` (regenerado)
- Test: suíte completa

**Interfaces:**
- Consumes: tudo das Tasks 1 a 6.
- Produces: ADR com contexto, alternativas (manter duas listas; política só no gateway), decisão (D1 a D6 e o registro de 5 papéis × 4 especialidades, e que `validate_plan`, `run_tests` e `write_doc` saíram), consequências (a execução de `run_safe_command` por agente exige aprovação humana por chamada; o servidor MCP `srv_api_run_safe_command` ainda usa o opt-in `SRV_API_ALLOW_ARBITRARY`; `core/tools.py` importa o gateway de forma tardia, dívida a quitar quando houver `core/ssh.py`; a evidência continua auto-reportada).

- [ ] **Step 1: Escrever a ADR** e converter para CRLF (`.gitattributes` já força em `vault/**`; conferir com `file`).
- [ ] **Step 2: Run** `python dashboard/build_graph.py` e `python cli.py evidence --lint` — Expected: snapshot atualizado, lint sem problemas.
- [ ] **Step 3: Run** `python -m pytest -q` — Expected: todos passam. Run `node --test dashboard/tests` — Expected: 117 de 119 (os 2 vermelhos de UX conhecidos, nada novo).
- [ ] **Step 4: Verificar os critérios de aceite da spec** com um script de uma linha por critério, mostrando a saída: (a) `pytest tests/test_no_local_allowlist.py` passa; (b) plano com ferramenta desconhecida é RED (`tests/test_mission_guard.py::test_unknown_tool_is_red_and_blocks`); (c) após uma missão de teste, `python cli.py trace <trace_id>` lista chamadas com `caller` `agent:<papel>`.
- [ ] **Step 5: Commit**

```bash
git add vault/adrs CLAUDE.md dashboard/graph-data.js
git commit -m "docs(adr): ADR-022 política única e corretor de ferramentas"
```

Depois da Task 7: revisão final independente da branch inteira (modelo mais capaz disponível) e `superpowers:finishing-a-development-branch`.

---

## Self-review

- **Cobertura da spec (Fase 5):** `core/policy/` e `core/broker.py` (T1, T3); executor adaptador (T4); registro igual à realidade, com `get_rule_evidence` implementado e as três ferramentas sem dono removidas (T2); `run_safe_command` como `PROD_READ` (T1, T2); portões no início da missão (T5); `ws_server` com `validate_mission_envelope` (T6); `sqlite3` fora (T1, T4); critérios de aceite (T7 passo 4); ADR-022 (T7). Seção 8: tabela da política, corretor com SSH simulado, guarda de lista, portões RED e YELLOW — todos têm teste.
- **Consistência de tipos:** `make_identity`/`parse_identity`, `Verdict`, `Decision`, `Reason`, `IMPLEMENTATIONS`, `call(...)`, `record_event(...)`, `check_mission(...)` têm o mesmo nome e assinatura onde são consumidos.
- **Decisões que a spec deixou abertas e que este plano fixa:** `run_tests`, `validate_plan`, `write_doc` saem do registro; `run_safe_command` fica só para o papel `coder` e sempre escala; a execução SSH continua numa só implementação (a do gateway, com chave do servidor memorizada); `record_test_execution` entra no registro de classes como `WRITE_LOCAL`, mas não em nenhum papel.
- **Fora desta fase:** especialidades na tela (Fase 7), luzes de teste (Fase 6), relatórios (Fase 8), runner (Fase 9), os 2 portões vermelhos de UX, e o rótulo `validate_plan` em `dashboard/agent-arena.js` (texto de interface sem efeito de política; vai junto da Fase 7).

# Fase 6: luzes de teste e domínio de observação — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada regra de negócio tem uma luz de teste (verde, amarela, vermelha, cinza) calculada das execuções registradas, separada da luz de saúde do Hub, e a lógica de observação sai do navegador para `core/domain/observation/`.

**Architecture:** Playbooks ganham `kind: test | runbook` e `ttl_hours`; `evidence.list_rules` passa a devolver a luz por regra. Um domínio de observação em Python (porte do `project()` de `dashboard/hub-topology.js`, com testes de paridade contra o JS) calcula a saúde por aspecto e as contradições "teste verde, saúde vermelha". O BFF passa a servir as duas APIs numa origem só (`/api/playbooks*`, `/api/rules`, `/v1/observability/assessment`). O JEV é reescrito como app React 19 com Tailwind 4 (`jev-app/`, mesmas versões do `nexus/`), compilado para `dashboard/jev/` e servido pelo próprio BFF; o dashboard o embute por iframe de mesma origem e a tela só renderiza.

**Tech Stack:** Python 3.14, pytest, SQLite (`core/evidence_store.py`), PyYAML, Node 24 (testes do dashboard, geração dos dados de paridade e build do `jev-app/`); React 19.3.0, Vite 8.3.4, Tailwind 4.3.3, lucide-react (versões exatas, como `nexus/package.json`); vitest, jsdom e @testing-library/react só como dependências de desenvolvimento do `jev-app/`.

**Spec:** `.superpowers/specs/2026-10-14-13-55-multiagent-platform-design.md` (D8, D9, seções 4, 6.4, 7 Fase 6, 8)

## Global Constraints

- Playbook sem `kind` vale `runbook` (nenhuma nota existente muda de significado); `ttl_hours` padrão 168 (spec 6.4).
- A cor conta só playbooks `active` com `kind: test`, no ambiente que o playbook declara (spec 6.4).
- Verde = todo playbook contado tem a última execução `pass`, dentro do TTL, no próprio ambiente. Amarela = algum playbook contado sem execução, só `skipped`, `pass` expirado, ou só execução `local` onde se exige `hml` ou `production`. Vermelha = a última execução de qualquer playbook contado é `fail` ou `error`. Cinza = nenhum playbook contado tem execução. Precedência: vermelha, cinza, amarela, verde.
- A luz de saúde do Hub mantém as regras do `project()` atual (obsoleta após 180 s) e nunca se mistura com a luz de teste; a contradição "testes verdes, saúde vermelha" é um alerta do domínio de observação (D8, D9).
- `evidence.list_rules` mantém os campos atuais (`state` etc.) e só acrescenta campos; `get_rule_evidence` (Fase 5) continua funcionando.
- A tabela `executions` ganha `commit_sha` e `run_id` opcionais por `ALTER TABLE ... ADD COLUMN`, sem perder dados de bancos já existentes.
- Execuções não guardam conteúdo de pedido; a trava de segredos (`tracing.find_sensitive`) continua valendo.
- `core/domain/observation/` só usa a biblioteca padrão (como `core/domain/nexus` e `workflow`).
- Notas novas ou editadas do vault ficam em CRLF; o snapshot do dashboard (`python dashboard/build_graph.py`) é regenerado de um checkout limpo.
- Front-end do JEV: React 19 + Tailwind 4 + Vite 8 em `jev-app/`, pinados nas versões exatas do `nexus/package.json` (Node >= 22.12). Tokens de cor, tipografia e espaçamento vêm de `dashboard/DESIGN.md` (fundo `#101513`, acento `#b8f37b`, fonte do sistema "Segoe UI", sem download de fonte), mapeados no tema do Tailwind; modo cockpit (denso, números em monoespaçada, pouca animação, só `transform` e `opacity`). Seguir as skills instaladas `design-taste-frontend-v1` (com o modo cockpit) e `redesign-existing-projects` como guia de estilo; as regras do projeto (`dashboard/DESIGN.md`, portões de UX, esta lista) têm precedência sobre as skills.
- O BFF serve `/dashboard/*` com CSP `script-src 'self'; style-src 'self'; font-src` padrão e só os sufixos `.html .js .css .json .svg .png .jpg .webp .md`: o app compilado não pode usar atributo `style=` inline, script inline, fonte web nem arquivo de outro sufixo (mapas de código ficam desligados). Saída do build: `dashboard/jev/` (index.html + assets), commitada, com `base: './'`; `node_modules` e cache do Vite ficam fora do git.
- Acessibilidade e semântica: o modal de registro de execução é um `<dialog>` (com `showModal`), foco devolvido ao abrir e fechar, rótulos em todos os campos, cor nunca como único sinal (a luz tem texto e ícone).
- Textos visíveis em português (BR); sem emoji como ícone (lucide-react).
- O escopo da migração é a tela do JEV (hoje `dashboard/jev-ui.js`, 995 linhas); o resto do dashboard continua em JavaScript puro. O que existir em `jev-ui.js` e não for portado entra na lista "removido" do relatório da Task 6, com o motivo.
- Linha de base a manter: testes Python da `main`, suíte Node com os 2 portões vermelhos de UX conhecidos e nada novo.
- Branch nova a partir de `main` (`feat/fase-6-luzes-de-teste`), em worktree limpo. A pasta de trabalho do dono não é tocada.

## Review Focus

- Playbook sem `kind` continua `runbook` e não muda nenhuma luz; `kind` inválido vira erro de lint, sem exceção (Task 1).
- `ttl_hours` zero, negativo, booleano, texto ou absurdo (> 8760) vira erro de lint e o padrão 168 não é aplicado em silêncio (Task 1).
- Execução com `ts` ilegível ou no futuro (mais de 5 minutos adiante): nunca conta como `pass` dentro do TTL; a luz fica amarela com motivo, sem exceção (Task 2).
- Última execução `skipped` depois de um `pass` antigo: amarela, não verde; execução local depois de uma de `hml`: o ambiente do playbook decide (Task 2).
- Observação ausente, parcial, obsoleta ou com falha de coleta: saúde `unknown` ou amarela, nunca verde, sem exceção; contradição só quando a luz da regra é verde e a saúde do mesmo ambiente é vermelha (Task 3).

---

### Task 1: `kind`, `ttl_hours` e colunas novas de execução

**Files:**
- Modify: `core/evidence.py` (`Playbook`, `_parse_playbook`, `validate_execution`, `rule_evidence`), `core/evidence_store.py` (`_SCHEMA`, migração, `record`, `_COLUMNS`), `mcp_servers/brain_mcp.py` (`record_test_execution`), `dashboard/serve.py` (`_record_execution`, meta do playbook), `cli.py` (comando `evidence`, só exibição do `kind`)
- Modify (vault, CRLF): `vault/playbooks/PB-001-...md` e `PB-002-...md` ganham `kind: test`
- Test: `tests/test_evidence.py`, `tests/test_evidence_store.py`, `tests/test_evidence_tools.py`, `tests/test_evidence_seed.py`

**Interfaces:**
- Consumes: estrutura atual de `Playbook`, `validate_execution`, `EvidenceStore.record`.
- Produces:
  - `KINDS = ("test", "runbook")`, `DEFAULT_TTL_HOURS = 168`, `MAX_TTL_HOURS = 8760` em `core/evidence.py`.
  - `Playbook.kind: str = "runbook"` e `Playbook.ttl_hours: int = 168` (campos com padrão, no fim do dataclass).
  - `EvidenceStore.record(..., commit_sha: Optional[str] = None, run_id: Optional[str] = None)`; as linhas devolvidas por `latest` carregam as duas chaves.
  - `validate_execution(defs, playbook_id, result, summary, evidence_ref, environment, commit_sha=None, run_id=None) -> Tuple[Optional[Dict[str,str]], Optional[str]]`: `commit_sha` aceita `^[0-9a-f]{7,40}$` ou vazio; `run_id` aceita `^[A-Za-z0-9._:/#-]{1,80}$` ou vazio; ambos passam pela trava de segredos; o dicionário limpo ganha as chaves `commit_sha` e `run_id` (vazias viram `None`).

- [ ] **Step 1: Write the failing tests**
  - `test_playbook_kind_defaults_to_runbook_and_ttl_168`: nota sem `kind`/`ttl_hours` → `kind == "runbook"`, `ttl_hours == 168`.
  - `test_playbook_kind_test_and_ttl_parsed`: `kind: test`, `ttl_hours: 24`.
  - `test_invalid_kind_and_ttl_are_lint_errors_not_exceptions`: `kind: smoke`; `ttl_hours` em `0`, `-1`, `true`, `"x"`, `9000`, `1.5` → cada caso aparece em `defs.errors` e a nota é descartada.
  - `test_real_seed_marks_pb001_and_pb002_as_tests`: `defs.playbooks["PB-001"].kind == "test"`, `PB-002` idem, e todos os outros `runbook`; o teste de CRLF existente continua verde.
  - Store: `test_executions_table_gets_new_columns_on_existing_db` (cria um banco com o esquema antigo e uma linha, abre com `EvidenceStore`, a linha continua e `commit_sha`/`run_id` existem como `None`); `test_record_roundtrips_commit_sha_and_run_id`.
  - Validação: `test_validate_execution_commit_sha_and_run_id` com aceitos (`abc1234`, `a`*40, `run-123`, `gha:98765`) e recusados (`xyz`, 41 hex, `run id com espaço`, texto com CPF `123.456.789-09`).
  - Ferramenta MCP: `record_test_execution` aceita `commit_sha` e `run_id` opcionais e os grava (teste em `tests/test_evidence_tools.py`).

- [ ] **Step 2: Run** `python -m pytest tests/test_evidence.py tests/test_evidence_store.py tests/test_evidence_tools.py tests/test_evidence_seed.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement** os campos novos e a migração (`PRAGMA table_info(executions)` e `ALTER TABLE executions ADD COLUMN ...` para cada coluna ausente, dentro de `_SCHEMA` handling do `__init__`); a validação de `kind` e `ttl_hours` em `_parse_playbook` (aceita só `int` que não seja `bool`, entre 1 e 8760); `kind: test` nos dois playbooks do vault (arquivos em CRLF, sem LF solto); `record_test_execution`, `PlaybooksApi._record_execution` e o `cli.py evidence` repassam e mostram os campos novos.

- [ ] **Step 4: Run** a mesma linha — Expected: PASS. Depois `python -m pytest -q` — Expected: sem regressão.

- [ ] **Step 5: Commit**

```bash
git add core mcp_servers dashboard/serve.py cli.py vault/playbooks tests
git commit -m "feat(evidence): kind e ttl_hours nos playbooks; commit_sha e run_id nas execuções"
```

### Task 2: Luz de teste por regra em `evidence.list_rules`

**Files:**
- Modify: `core/evidence.py` (`list_rules`, novo `rule_light`)
- Test: `tests/test_evidence_lights.py`, `tests/test_evidence.py` (casos de `list_rules` existentes continuam passando)

**Interfaces:**
- Consumes: `Playbook.kind`, `Playbook.ttl_hours`, `EvidenceStore.latest(playbook_id, limit)` (linhas com `ts`, `result`, `environment`).
- Produces:
  - `rule_light(playbooks: List[Playbook], store: EvidenceStore, now: Optional[datetime] = None) -> Dict[str, Any]` com `{"light": "green"|"yellow"|"red"|"grey", "reason": str, "test_playbooks": [ids], "test_environments": [envs]}`.
  - `list_rules(defs, store, now=None)`: cada linha mantém `id`, `title`, `status`, `playbooks`, `playbook_latest`, `state` e ganha `light`, `light_reason`, `test_playbooks`, `test_environments`.

- [ ] **Step 1: Write the failing tests** (`tests/test_evidence_lights.py`, banco temporário, `now` fixo, playbooks construídos em memória):
  - `test_grey_without_any_test_execution`; `test_grey_when_rule_has_no_test_playbook` (só runbooks; `test_playbooks == []`).
  - `test_green_requires_every_counted_playbook`: com PB-001 (`local`) e PB-002 (`hml`), ambos `kind: test` e ativos, só PB-001 com `pass` → amarela; com PB-002 `pass` em `hml` também → verde. **Critério de aceite da fase:** RULE-001 não é verde enquanto PB-002 não tiver `pass`.
  - `test_fail_or_error_in_any_counted_playbook_is_red` (último `fail` de PB-001 com PB-002 `pass` → vermelha; `error` idem); vermelha vence cinza e amarela.
  - `test_runbook_and_retired_playbooks_never_count`.
  - `test_expired_pass_is_yellow` (`pass` com 169 h e TTL 168); `test_pass_inside_ttl_is_green` (167 h); TTL próprio (`ttl_hours: 24` com `pass` de 30 h → amarela).
  - `test_local_run_does_not_satisfy_hml_playbook` (playbook `hml` só com execução `local` → amarela, motivo cita o ambiente exigido).
  - `test_skipped_after_old_pass_is_yellow`; `test_unparseable_or_future_ts_is_never_a_fresh_pass` (`ts` lixo e `ts` 10 minutos no futuro → amarela com motivo, sem exceção).
  - `test_existing_state_field_unchanged` (`state` continua `ok`/`parcial`/`falha`/`sem evidência ainda` nos casos do arquivo `tests/test_evidence.py`).

- [ ] **Step 2: Run** `python -m pytest tests/test_evidence_lights.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement** `rule_light` e a integração. A "última execução no ambiente do playbook" é a mais recente com `environment == playbook.environment`; a "última execução" para a vermelha é a mais recente em qualquer ambiente. `ts` é lido com `datetime.fromisoformat`; erro ou mais de 5 minutos no futuro marca o playbook como "dados inválidos" (amarela). O `reason` é um texto curto em português que nomeia o playbook que decidiu a cor.

- [ ] **Step 4: Run** `python -m pytest tests/test_evidence_lights.py tests/test_evidence.py tests/test_evidence_tools.py -v` — Expected: PASS. Depois `python -m pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add core/evidence.py tests/test_evidence_lights.py
git commit -m "feat(evidence): luz de teste por regra (verde, amarela, vermelha, cinza) com TTL e ambiente"
```

### Task 3: Domínio de observação (`core/domain/observation/`)

**Files:**
- Create: `core/domain/observation/__init__.py`, `core/domain/observation/entities.py`, `core/domain/observation/projection.py`, `scripts/generate_observation_golden.js` (gera os dados de paridade a partir de `dashboard/hub-topology.js`), `tests/fixtures/observation_golden.json`
- Test: `tests/test_domain_observation.py`

**Interfaces:**
- Consumes: o contrato do envelope do BFF (`store.latest`: `environment`, `observation.report.snapshots`, `age_seconds`, `stale`, `collection_failed`, `last_attempt`) e as regras de `dashboard/hub-topology.js` (`evaluateProcess`, `evaluateEndpoint`, `evaluateDatabase`, `stateOf`, `collectionOf`, `project`).
- Produces:
  - `ServiceHealth(id: str, status: str, reason: str)` (`id` em `process`, `internal`, `external`, `database`; `status` em `green`, `yellow`, `red`, `unknown`), dataclass congelada.
  - `ObservationSnapshot(environment: str, nodes: Tuple[ServiceHealth, ...], status: str, reason: str, stale: bool)`.
  - `project(environment: str, latest: Optional[dict], now_seconds: float) -> ObservationSnapshot` (porte fiel do `project` do JS: mesmos status e mesmos textos de `reason`; aqui só vira Python).
  - `Contradiction(rule_id: str, environment: str, light: str, health: str, reason: str)`; `detect_contradictions(rules: List[dict], snapshots: Dict[str, ObservationSnapshot]) -> List[Contradiction]`: uma contradição por regra e ambiente observado (`production`, `hml`) quando `rule["light"] == "green"`, o ambiente consta em `rule["test_environments"]` e `snapshots[env].status == "red"`.

- [ ] **Step 1: Write the failing tests**
  - Paridade: `scripts/generate_observation_golden.js` roda o `project()` do JS sobre um conjunto fixo de entradas (as do `dashboard/tests/hub-topology.test.cjs`: tudo verde, observação ausente, obsoleta, falha de coleta, banco com `failed` alto, processo reiniciado, SHA divergente, `workerEnabled` falso em produção, etc., mínimo 12 casos com `NOW` fixo) e grava `{"cases": [{"name", "environment", "latest", "now", "expected": {"status", "reason", "nodes": [{"id","status","reason"}]}}]}` em `tests/fixtures/observation_golden.json`; `test_projection_matches_javascript_golden` compara os 12+ casos campo a campo.
  - `test_missing_partial_or_malformed_observation_is_never_green_and_never_raises`: `None`, `{}`, `{"observation": {"report": {"snapshots": []}}}`, `snapshots` de tamanho 1, valores de tipo errado, `stale: "yes"`.
  - `test_detect_contradictions_only_when_light_green_and_health_red`: verde+vermelha → 1 contradição com `rule_id`, `environment`, textos; verde+verde, amarela+vermelha, verde+amarela, regra sem o ambiente em `test_environments` → nenhuma.
  - `test_domain_has_no_io_imports`: o código-fonte de `core/domain/observation/*.py` não importa nada fora da biblioteca padrão e de `core.domain`.

- [ ] **Step 2: Run** `node scripts/generate_observation_golden.js` e depois `python -m pytest tests/test_domain_observation.py -v` — Expected: FAIL (módulo ausente).

- [ ] **Step 3: Implement** o porte (função por avaliador, mesmos limiares e mensagens do JS; o que o JS trata como inválido o Python trata igual). Se uma regra do JS for ambígua, o JS é a fonte e o teste de paridade a fixa.

- [ ] **Step 4: Run** `python -m pytest tests/test_domain_observation.py -v` — Expected: PASS. `node --test dashboard/tests/hub-topology.test.cjs` continua verde (o JS não mudou).

- [ ] **Step 5: Commit**

```bash
git add core/domain/observation scripts/generate_observation_golden.js tests/fixtures/observation_golden.json tests/test_domain_observation.py
git commit -m "feat(observation): domínio de observação em Python com paridade contra o JS"
```

### Task 4: BFF com as duas APIs numa origem só

**Files:**
- Create: `backend/playbooks_api.py` (a classe `PlaybooksApi` extraída de `dashboard/serve.py`, mesmo comportamento)
- Modify: `dashboard/serve.py` (importa a classe), `backend/server.py` (`do_GET`, `do_POST`), `core/evidence.py` não muda
- Test: `tests/test_playbooks_api.py` (continua verde com a classe movida), `tests/test_bff_wave1.py`, novo `tests/test_bff_phase6.py`

**Interfaces:**
- Consumes: `PlaybooksApi.handle(path, method, body) -> Optional[Tuple[int, dict]]`; `evidence.list_rules`; `core.domain.observation.project`, `detect_contradictions`; `Store.latest(environment)` do BFF.
- Produces:
  - `backend.playbooks_api.PlaybooksApi` com a nova rota `GET /api/rules` → `{"rules": list_rules(...)}`.
  - Rotas do BFF (todas atrás da sessão e da checagem de origem já existentes): `GET /api/playbooks`, `GET /api/playbooks/{id}`, `GET /api/playbooks/{id}/executions`, `GET /api/playbooks/executions`, `GET /api/rules`, `POST /api/playbooks/executions` e `POST /api/playbooks/{id}/render` (exigem `Content-Type: application/json`).
  - `GET /v1/observability/assessment?environment=production|hml` → `{schema_version, space_id, request_id, environment, status, reason, stale, nodes: [{id,status,reason}], contradictions: [{rule_id, environment, light, health, reason}]}` calculado com o domínio de observação sobre `store.latest(environment)` e as luzes de `list_rules`.

- [ ] **Step 1: Write the failing tests** (`tests/test_bff_phase6.py`, no estilo de `tests/test_bff_wave1.py`: servidor em porta livre, sessão válida, banco temporário): sem sessão → 401 em cada rota nova; origem errada → 403; `GET /api/rules` devolve uma linha por regra com `light`; `POST /api/playbooks/executions` com `evidence_ref` vazio → 400 `VALIDATION_FAILED`; com tudo válido → 201 e a luz da regra muda; `Content-Type` errado → 415; `GET /v1/observability/assessment` com observação inexistente → `status` `unknown`/`yellow` e 200, `environment` inválido → 400 `INVALID_ENVIRONMENT`; com uma observação vermelha injetada em `Store` e uma regra verde → uma contradição na resposta. O servidor de `dashboard/serve.py` continua servindo as mesmas rotas de playbooks (`tests/test_playbooks_api.py` verde).

- [ ] **Step 2: Run** `python -m pytest tests/test_bff_phase6.py tests/test_playbooks_api.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement** a extração (sem mudar comportamento: o resto do arquivo `dashboard/serve.py` só troca a definição da classe por um `import`), as rotas do BFF e a rota de avaliação. O assessment é função pura de `(latest, rules, now)` num helper testável, não código solto no handler.

- [ ] **Step 4: Run** `python -m pytest -q` — Expected: sem regressão.

- [ ] **Step 5: Commit**

```bash
git add backend dashboard/serve.py tests
git commit -m "feat(bff): playbooks, regras e avaliação de observação numa origem só"
```

### Task 5: App `jev-app/` (React 19 + Tailwind 4): estrutura, tema, cliente da API e lógica pura

**Files:**
- Create: `jev-app/package.json` (versões exatas; `type: module`; scripts `dev`, `build`, `test`; `engines.node >= 22.12.0`), `jev-app/package-lock.json`, `jev-app/vite.config.js` (plugins `@tailwindcss/vite` e React; `base: './'`; `build.outDir: '../dashboard/jev'`, `emptyOutDir: true`, `sourcemap: false`; proxy de desenvolvimento de `/api` e `/v1` para `http://127.0.0.1:8848`), `jev-app/index.html`, `jev-app/src/main.jsx`, `jev-app/src/index.css` (Tailwind 4 `@import "tailwindcss"` e `@theme` com os tokens de `dashboard/DESIGN.md`), `jev-app/src/lib/api.js`, `jev-app/src/lib/lights.js`, `jev-app/src/lib/validation.js`, `jev-app/README.md` (comandos de build e a regra "o build é commitado")
- Modify: `.gitignore` (`jev-app/node_modules/`, `jev-app/.vite/`)
- Test: `jev-app/src/lib/lights.test.js`, `jev-app/src/lib/validation.test.js`, `jev-app/src/lib/api.test.js` (vitest)

**Interfaces:**
- Consumes: `GET /api/playbooks`, `GET /api/playbooks/{id}`, `GET /api/playbooks/executions`, `GET /api/playbooks/{id}/executions`, `POST /api/playbooks/executions`, `GET /api/rules`, `GET /v1/observability?environment=…`, `GET /v1/observability/assessment?environment=…` (Task 4).
- Produces (módulos puros, sem DOM):
  - `lib/lights.js`: `LIGHTS = ['green','yellow','red','grey']`; `lightMeta(light) -> {label: string, icon: string, tone: string}` (rótulo em português e nome do ícone lucide, tom = chave do tema; valor desconhecido devolve o cinza); `healthMeta(status)` idem para `green|yellow|red|unknown`.
  - `lib/validation.js`: `validateExecution(form) -> {ok: boolean, errors: Record<string,string>}` para `{result, environment, summary, evidenceRef, commitSha, runId}` com as mesmas regras do backend (`summary` 1 a 500; `evidenceRef` obrigatório, 1 a 300, forma `caminho:linha`, URL `http(s)` ou id de ticket; `commitSha` vazio ou `^[0-9a-f]{7,40}$`; `runId` vazio ou `^[A-Za-z0-9._:/#-]{1,80}$`).
  - `lib/api.js`: `observationUrl(env)`, `assessmentUrl(env)` (strings), `fetchJson(url, init) -> Promise<{ok, status, data}>` que nunca lança (erro de rede vira `{ok:false, status:0, data:null}`), `getRules()`, `getPlaybooks()`, `getExecutions(playbookId?)`, `getAssessment(env)`, `postExecution(payload)`; `observationUrl('production')` é `/v1/observability?environment=production`.
  - O tema (`index.css`) expõe os tokens de `dashboard/DESIGN.md` como variáveis do Tailwind (`--color-bg`, `--color-accent`, …) e cores semânticas das luzes (`light-green`, `light-yellow`, `light-red`, `light-grey`).

- [ ] **Step 1: Write the failing tests** (vitest): `lightMeta` cobre as 4 cores e o valor desconhecido (`'purple'`, `undefined`) devolve cinza com rótulo; `healthMeta('unknown')`; `validateExecution` aceita `{summary:'ok', evidenceRef:'vault/x.md:3', result:'pass', environment:'hml'}`, `DEM-12` e uma URL `https://…`, recusa `evidenceRef` vazio ou só espaços, `summary` vazio, `summary` com 501 caracteres, `commitSha: 'xyz'`, `runId: 'com espaço'`; `observationUrl` não contém `/v1/observation/`; `fetchJson` com `fetch` simulado que rejeita devolve `{ok:false,status:0,data:null}` sem lançar, e com resposta 400 devolve `ok:false` e o corpo.
- [ ] **Step 2: Run** `cd jev-app && npm install && npm test` — Expected: FAIL (módulos ausentes).
- [ ] **Step 3: Implement** os módulos e a estrutura do app (ainda sem telas: `main.jsx` monta um `App` mínimo que só mostra o título). `npm run build` gera `dashboard/jev/index.html` e `assets/*.js|css` (confirmar que só aparecem os sufixos permitidos pelo BFF).
- [ ] **Step 4: Run** `cd jev-app && npm test && npm run build` — Expected: testes passam e o build termina sem aviso; `ls dashboard/jev dashboard/jev/assets` mostra só sufixos permitidos.
- [ ] **Step 5: Commit**

```bash
git add jev-app dashboard/jev .gitignore
git commit -m "feat(jev-app): app React 19 + Tailwind 4 com tema do dashboard, cliente da API e lógica pura"
```

### Task 6: Telas do JEV em React: regras com luzes, playbooks, execuções e registro

**Files:**
- Create: `jev-app/src/App.jsx` (navegação por abas: Regras, Playbooks, Execuções), `jev-app/src/components/LightChip.jsx`, `RulesView.jsx`, `PlaybooksView.jsx`, `ExecutionsView.jsx`, `ExecutionDialog.jsx` (registro, `<dialog>`), `ContradictionBanner.jsx`, `EnvToggle.jsx`, `jev-app/src/hooks/useAsync.js`
- Modify: `jev-app/src/main.jsx`
- Test: `jev-app/src/components/*.test.jsx` (vitest + jsdom + @testing-library/react), com `fetch` simulado

**Interfaces:**
- Consumes: os módulos da Task 5 e as respostas de `GET /api/rules` (linhas com `id`, `title`, `status`, `playbooks`, `playbook_latest`, `state`, `light`, `light_reason`, `test_playbooks`, `test_environments`), `GET /api/playbooks` (`id`, `title`, `status`, `kind`, `environment`, …), `GET /api/playbooks/executions` (`playbook_id`, `ts`, `result`, `environment`, `evidence_ref`, `summary`, `commit_sha`, `run_id`, `source`) e `GET /v1/observability/assessment` (`status`, `reason`, `stale`, `nodes`, `contradictions`).
- Produces: um app que, para cada regra, mostra **dois sinais separados**: o `LightChip` de teste (cor, ícone e texto, com `light_reason` como apoio acessível) e o chip de saúde do ambiente, mais o `ContradictionBanner` quando `assessment.contradictions` não está vazio; o `ExecutionDialog` registra uma execução com `evidence_ref` obrigatório (mensagem de erro por campo vinda de `validateExecution`, erro do servidor exibido sem perder o formulário), `commit_sha` e `run_id` opcionais.

- [ ] **Step 1: Write the failing tests**: `RulesView` com `fetch` simulado devolvendo 3 regras (verde, amarela, cinza) mostra três chips com os textos "Verde", "Amarela", "Cinza" e o `light_reason`; uma regra vermelha mostra o texto "Vermelha" e nunca depende só de cor (existe texto e ícone); saúde obsoleta mostra o chip de saúde amarelo sem alterar o chip de teste; `ContradictionBanner` aparece só quando há contradição e cita `rule_id` e ambiente; `ExecutionDialog` abre como `dialog` aberto (`open`), recusa envio com `evidence_ref` vazio (mensagem no campo, `postExecution` não é chamado), envia com dados válidos e fecha, mostra erro do servidor (400 `VALIDATION_FAILED`) mantendo os campos preenchidos, devolve o foco ao botão que o abriu; erro de rede em `getRules` mostra um estado de erro com botão "Tentar novamente"; lista vazia mostra estado vazio com texto; estado de carregamento mostra texto de carregamento.
- [ ] **Step 2: Run** `cd jev-app && npm test` — Expected: FAIL.
- [ ] **Step 3: Implement** as telas. Inventariar primeiro o que `dashboard/jev-ui.js` oferece (cobertura de playbooks por ambiente, linha do tempo de execuções, parâmetros Liquid ao registrar, aviso de contradição, abas por ambiente) e portar o que tem valor para quem opera (cobertura, histórico, registro); o que não for portado vai para a lista "removido" do relatório. Sem `style=` inline, sem emoji, atalhos de teclado básicos (Esc fecha o diálogo).
- [ ] **Step 4: Run** `cd jev-app && npm test && npm run build` — Expected: PASS e build limpo.
- [ ] **Step 5: Commit**

```bash
git add jev-app dashboard/jev
git commit -m "feat(jev-app): regras com luz de teste e saúde separadas, playbooks, execuções e registro em dialog"
```

### Task 7: Dashboard embute o JEV novo e remove o JEV em JavaScript puro

**Files:**
- Modify: `dashboard/app.js` (rota `jev`: cabeçalho com botão "Abrir em nova aba" e iframe de mesma origem para `/dashboard/jev/index.html`, com estado de erro igual ao do Nexus quando a página não carrega), `dashboard/index.html` (remove `jev-ui.js`), `dashboard/serve.py` (servir `jev/` com os mesmos sufixos; conferir a CSP), `dashboard/graph-catalog.json` e o que referenciar `jev-ui.js` (grep)
- Delete: `dashboard/jev-ui.js`
- Test: `dashboard/tests/syntax.test.cjs` (continua), `dashboard/tests/ux-gates.test.cjs` (não pode piorar; o excesso de `hardcoded_values` cai de 12 para 10 porque o JEV antigo sai), `tests/test_bff_phase6.py` (o BFF devolve 200 para `/dashboard/jev/index.html` e para os arquivos de `assets/`, com sessão; 404 para um sufixo não permitido dentro de `jev/`)

**Interfaces:**
- Consumes: `dashboard/jev/` (Task 5 e 6) e a rota `jev` do `app.js`.
- Produces: página "JEV" do dashboard que abre o app React na mesma origem, de modo que o cookie de sessão do BFF vale para as chamadas `/api/*` e `/v1/*`.

- [ ] **Step 1: Write the failing tests**: no BFF, `GET /dashboard/jev/index.html` com sessão → 200 `text/html`; um `assets/*.js` e um `assets/*.css` listados no `index.html` → 200 com o tipo certo; `GET /dashboard/jev/x.map` → 404; sem sessão → 401. No dashboard: um teste Node que carrega `app.js` com o DOM de teste usado pelos outros (ver `dashboard/tests/app-el.test.cjs`) e verifica que a rota `jev` cria um `iframe` com `src` terminando em `/dashboard/jev/index.html` e sem `style` inline novo; `grep` do repositório não acha mais `BrainJEV` nem `jev-ui.js`.
- [ ] **Step 2: Run** `python -m pytest tests/test_bff_phase6.py -v` e `node --test dashboard/tests/*.test.cjs` — Expected: FAIL.
- [ ] **Step 3: Implement** a troca; o `iframe` usa classes (não `style=`) e a altura vem de uma classe do `style.css`.
- [ ] **Step 4: Run** `python -m pytest -q` e `node --test dashboard/tests/*.test.cjs` — Expected: Python verde; Node com no máximo os 2 portões de UX vermelhos de antes (`hardcoded_values` com excesso menor, `modal_semantics` agora verde se o `<dialog>` for o único modal do JEV e nenhum outro `div` modal restar; se continuar vermelho por outro arquivo, dizer qual). Abrir o BFF com sessão local no navegador do app e conferir: página JEV carrega o app React, sem erro de console, regras com luz de teste e saúde, diálogo de registro funcionando.
- [ ] **Step 5: Commit**

```bash
git add dashboard
git rm dashboard/jev-ui.js
git commit -m "refactor(dashboard): JEV passa a ser o app React embutido; remove jev-ui.js"
```

### Task 8: ADR-023, documentação e verificação final

**Files:**
- Create: `vault/adrs/ADR-023-luzes-de-teste-e-dominio-de-observacao.md` (CRLF; formato da ADR-021: contexto, alternativas, decisão, consequências; relacionadas ADR-005, ADR-019, ADR-021)
- Modify: `CLAUDE.md` (intervalo de ADRs e uma linha sobre a luz de teste vs luz de saúde), `dashboard/graph-data.js` (regenerado), `vault/systems/...` não muda
- Test: suíte completa

**Interfaces:**
- Consumes: Tasks 1 a 7.
- Produces: ADR com as decisões D8 e D9 como construídas, a regra de cor, a escolha de marcar só PB-001 e PB-002 como `kind: test` (PB-003 é verificação manual em homologação e fica `runbook`), a regra "contradição = luz de teste verde + saúde vermelha no mesmo ambiente", a migração do JEV para React 19 com Tailwind 4 (`jev-app/`, build commitado em `dashboard/jev/`, iframe de mesma origem, o que foi portado e o que foi removido do `jev-ui.js`) e o que ficou de fora (migração do resto do dashboard, alertas ativos, luzes por sistema além do Hub, relatórios da Fase 8) e as dívidas conhecidas.

- [ ] **Step 1: Escrever a ADR** e conferir CRLF-only nos bytes.
- [ ] **Step 2: Run** `python dashboard/build_graph.py` e `python cli.py evidence --lint` — Expected: snapshot atualizado, lint sem problemas.
- [ ] **Step 3: Run** `python -m pytest -q` e `node --test dashboard/tests/*.test.cjs` — Expected: tudo passa, salvo os 2 vermelhos de UX conhecidos.
- [ ] **Step 4: Verificar os critérios de aceite da spec com execução real** e registrar a saída: (a) banco temporário com os dados da semente: `python cli.py evidence` mostra RULE-001 **não verde**; registrar `pass` de PB-002 em `hml` com evidência válida → RULE-001 verde; registrar `fail` em qualquer um → vermelha; (b) `GET /api/rules` e `GET /v1/observability/assessment` respondem no BFF com sessão local.
- [ ] **Step 5: Commit**

```bash
git add vault/adrs CLAUDE.md dashboard/graph-data.js
git commit -m "docs(adr): ADR-023 luzes de teste e domínio de observação"
```

Depois da Task 8: revisão final independente da branch inteira e `superpowers:finishing-a-development-branch`.

---

## Self-review

- **Cobertura da spec (Fase 6 e 6.4):** `kind` e `ttl_hours` (T1); regra de cor com TTL, ambiente e precedência (T2); `commit_sha` e `run_id` com migração (T1); `core/domain/observation/` com `ServiceHealth`, `ObservationSnapshot`, `Contradiction`, `detect_contradictions` (T3); endpoint de regras e uma origem para as duas APIs (T4); JEV reescrito em React com Tailwind, com as correções (rota, `evidence_ref` obrigatório em `<dialog>`, `retired`, endpoint de regras) e as duas luzes separadas (T5, T6, T7); critério de aceite RULE-001 só verde com PB-002 (T2 teste e T6 execução real).
- **Consistência de tipos:** `light`, `light_reason`, `test_playbooks`, `test_environments` (T2) são os campos que T3 (`detect_contradictions`), T4 (assessment e `/api/rules`) e T5 e T6 (`lightMeta`, `RulesView`) consomem; `project` e `ObservationSnapshot` (T3) são os que T4 usa.
- **Decisões fixadas aqui:** só PB-001 e PB-002 são `kind: test`; contradição só quando a luz da regra é verde e o ambiente de teste do playbook coincide com o ambiente observado em vermelho; ambientes sem observação (local) nunca geram contradição; `GET /v1/observability/assessment` é a rota nova (a rota de observação do JEV passa a ser `/v1/observability`, a que o BFF já tem).
- **Fora desta fase:** migração do resto do dashboard para React com Tailwind, alertas ativos (Teams e e-mail), luzes por outros sistemas além do Hub, relatórios (Fase 8), runner (Fase 9).

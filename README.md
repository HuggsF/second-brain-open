# Second Brain —  [empresa]

Base de conhecimento de engenharia da [empresa], local e offline.
O **vault** em Markdown é a fonte de verdade; o índice vetorial (Qdrant + Ollama), o grafo do dashboard e as
respostas dos servidores MCP são derivados dele e podem ser reconstruídos.

Regras de trabalho no repositório (proibições, gate de testes, definição de pronto): [CLAUDE.md](CLAUDE.md).

| Peça | Onde | Para quê |
|---|---|---|
| Vault | `vault/` | Notas Markdown: ADRs, sistemas, regras, playbooks, produto, times |
| CLI | `cli.py` | Sincronizar o índice, perguntar com RAG, evidências, trace |
| Servidores MCP | `mcp_servers/` | Ferramentas para IDEs e agentes (busca, ADRs, GitHub, SRV-API, Hub, tarefas locais) |
| BFF | `backend/` | Servidor local com sessão: dashboard, observabilidade, WebSocket e API de workflows |
| Graph Engine | `core/graph/` | Node Loop Graph: 7 nós, telemetria, circuit breakers, HITL |
| Nexus | `nexus/` | Escritório visual de agentes (React + Vite) — simulação local ou WS para backend |
| Dashboard | `dashboard/` | Interface estática: biblioteca, grafo, consultas, Workflow Studio, observabilidade |
| Ingestão | `ingestion/` | Sync do vault, Google Drive, curso de System Design, chunks de inteligência |

Fora do escopo: o código do Hub Logístico e do SRV-API (outros repositórios, somente leitura daqui) e os
resultados de análise 360 (`C:/KIOSK/analise-360`).

## Instalação

Requer Python 3.14+ e Node.js ≥ 22.12.0 (para Nexus e testes do dashboard).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d          # Qdrant (6333) e Ollama (11434)
.\.venv\Scripts\python.exe cli.py pull-models
.\.venv\Scripts\python.exe cli.py status
```

Os gateways que acessam GitHub e o servidor SRV-API leem host, usuário e caminho da chave do arquivo `.env`
(nunca versionado). Não defina `SRV_API_ALLOW_ARBITRARY`.

## CLI

| Comando | O que faz |
|---|---|
| `cli.py status` | Estado do Qdrant, do Ollama e do vault |
| `cli.py sync` | Sincronização diferencial (SHA-256) do vault com o Qdrant; sai com 1 se algum arquivo falhar |
| `cli.py sync --reconcile` | Reconcilia o manifesto com o índice vetorial: remove órfãos, reindexa o que falta; sai com 1 se algum arquivo falhar |
| `cli.py sync --rebuild` | Reconstrói o índice inteiro em uma coleção nova e troca o alias; saída para manifesto ilegível |
| `cli.py sync --rebuild --yes` | Igual, confirmando a primeira migração da coleção atual para alias (a busca falha por um instante) |
| `cli.py ask "pergunta"` | Resposta com RAG local e fontes |
| `cli.py pull-models` | Baixa os modelos de embedding e de chat no Ollama |
| `cli.py drive-sync` | Baixa documentos do Google Drive e gera notas em `vault/product/references/` |
| `cli.py evidence [RULE-ID]` | Árvore de evidências de uma regra; `--lint` valida regras e playbooks; `--import-seed` importa `evidence/seed-executions.json` |
| `cli.py trace TRACE_ID` | Cadeia de chamadas MCP de uma tarefa; `--recent N` lista as últimas |
| `cli.py task classify\|extract\|summarize\|validate\|status` | Tarefas pequenas no modelo local; imprime o envelope `task.result` |
| `cli.py task-eval` | Mede a qualidade do modelo local contra `tests/golden_dataset_local_tasks.json` (precisa do Ollama; fora do gate) |

Todos os comandos rodam com `.\.venv\Scripts\python.exe cli.py ...` a partir da raiz.

## Dashboard

O dashboard é estático (`dashboard/index.html`) e lê o snapshot `dashboard/graph-data.js`. Depois de alterar o
vault ou `dashboard/graph-catalog.json`, gere o snapshot de novo:

```powershell
.\.venv\Scripts\python.exe dashboard\build_graph.py
```

Há dois servidores, ambos só em loopback:

| Servidor | Comando | Endereço | Serve |
|---|---|---|---|
| BFF (uso normal) | `.\.venv\Scripts\python.exe -m backend.server` | `http://127.0.0.1:8848/dashboard/` | Dashboard, `/v1/*` (observabilidade) e `/api/workflow/*`, com sessão |
| Desenvolvimento | `.\.venv\Scripts\python.exe dashboard\serve.py` | `http://127.0.0.1:8847/` | Dashboard e `/api/workflow/*`, sem sessão e sem observabilidade |

O BFF grava um link de uso único (30 min) em `.runtime/connect.url`; abra-o para criar a sessão (8 h). Para
gerar outro link sem subir o servidor: `python -m backend.server --issue-link`. Ao subir, o BFF coleta a cada
60 s o estado de produção e homologação do Hub pela ferramenta MCP `observe_hub`, somente leitura.

A API do Workflow Studio (`backend/workflow_api.py`) registra cada passo executado no dashboard em
`.runtime/workflow_audit.jsonl` e o associa a uma nota do vault; ela não executa agentes. Escrita exige `Origin`
igual ao do servidor. Detalhes do BFF: [second-brain-observability-bff](vault/systems/second-brain-observability-bff.md).

## Orchestrator — Graph Engine

O orquestrador de missões usa o **Node Loop Graph** (`core/graph/`), uma arquitetura baseada em grafos com 7 nós
assíncronos puros, circuit breakers duplos e suporte a Human-in-the-Loop (HITL).

| Nó | Responsabilidade |
|---|---|
| `plan_node` | Decompõe a tarefa em steps via keyword matching |
| `gate_node` | Quality gates: DAG, DLP, grounding, idempotência |
| `route_node` | MoE routing dinâmico + unbind de circuit breakers abertos |
| `execute_node` | Executa o step corrente via broker com retry |
| `validate_node` | Valida o resultado do último step executado |
| `correct_node` | Incrementa contador de retry e rebobina step_index |
| `post_gate_node` | Quality gates pós-missão e sintetização de estado |

Circuit breaker (por step e global) e suspensão Human-in-the-Loop (HITL) são coordenados pelo motor de
execução (`runner.py`) e pelo servidor WebSocket (`ws_server.py`), mantendo os nós puros e desacoplados.

A feature flag `MISSION_ENGINE=graph` ativa o graph engine; sem ela, o orquestrador legado
(`backend/orchestrator.py`) continua ativo. Ambas as APIs coexistem (Strangler Fig pattern).

```powershell
# Ativar o graph engine no WebSocket server
$env:MISSION_ENGINE = "graph"
.\.venv\Scripts\python.exe -m backend.ws_server
```

Detalhes da arquitetura: [ADR do Node Loop Graph](vault/adrs/) · Telemetria: registro estruturado de traces, spans por nó e contagem de tokens em `.runtime/trace-log.jsonl`.

## Nexus — Escritório de Agentes

O **Nexus** (`nexus/`) é o frontend React + Vite que visualiza e controla missões. Opera em dois modos:

| Modo | Variável | Comportamento |
|---|---|---|
| **Simulação local** | `VITE_ADAPTER_MODE=local` (padrão) | Tick driver local, dados simulados, métricas fictícias |
| **Backend real** | `VITE_ADAPTER_MODE=ws` | WebSocket para `ws_server.py`, missões reais, telemetria |

```powershell
# Modo simulação (desenvolvimento)
cd nexus; npm install; npm run dev

# Modo backend real
$env:VITE_ADAPTER_MODE = "ws"
npm run dev
```

O adaptador de transporte (`nexus/src/adapters/`) implementa o protocolo de eventos
(`event-protocol.js`) e roteia ações do React para o backend via WebSocket.

## Servidores MCP

Cada ferramenta aceita um `task_id` opcional; as chamadas ficam em `.runtime/trace-log.jsonl` e se consultam com
`cli.py trace`.

| Servidor | Ferramentas |
|---|---|
| `brain_mcp.py` | `search_knowledge_base`, `get_adr`, `get_system_architecture`, `get_brain_status`, `list_rules`, `get_rule_evidence`, `record_test_execution` |
| `github_gateway_mcp.py` | `github_check_status`, `github_list_repositories`, `github_get_repository_details`, `github_search_code`, `github_list_contents` |
| `srv_api_gateway_mcp.py` | `srv_api_health_check`, `srv_api_resource_usage`, `srv_api_list_services`, `srv_api_view_logs`, `srv_api_run_safe_command` |
| `hub_observability_mcp.py` | `observe_hub(environment)` |
| `local_tasks_mcp.py` | `classify`, `extract`, `summarize`, `validate`, `local_tasks_status` |

Exemplo de registro no cliente MCP (o caminho do arquivo de configuração depende do cliente):

```json
{
  "mcpServers": {
    "kiosk-second-brain": {
      "command": "C:\\KIOSK\\second-brain\\.venv\\Scripts\\python.exe",
      "args": ["C:\\KIOSK\\second-brain\\mcp_servers\\brain_mcp.py"]
    }
  }
}
```

Os gateways de GitHub e SRV-API são somente leitura por padrão; um comando que altere estado num host exige
autorização humana explícita (CLAUDE.md, seção 2).

## Tarefas locais

Tarefas pequenas (classificar, extrair campos de um template, resumir, validar um documento) rodam num modelo
local do Ollama, sem custo de tokens pagos. O núcleo (`core/protocol/`, `core/local_tasks/`, `core/events.py`) é
agnóstico; vocabulário, limites e preço de referência vêm do perfil em `profiles/<nome>/profile.yaml`
([ADR-017](vault/adrs/ADR-017-tier-local-de-tarefas-e-nucleo-com-perfis.md)).

- **Ferramentas MCP** (`local_tasks_mcp.py`, `task_id` opcional em todas): `classify`, `extract`, `summarize`,
  `validate` e `local_tasks_status` (modelo disponível, falhas de gravação de eventos, templates). O trace MCP
  guarda só o tamanho de `text`, `document` e `source` (`{"chars": n}`), nunca o conteúdo; sem `task_id`, o
  envelope usa o `trace_id` da própria chamada MCP.
- **Perfil:** `BRAIN_PROFILE` escolhe a pasta de `profiles/`; sem a variável vale `settings.default_profile`
  (`config.py`). `profiles/example/` é o modelo para outra instância.
- **CLI:** `cli.py task classify|extract|summarize|validate|status` (texto por argumento ou `--file`, em UTF-8).
  `validate` aceita também um objeto JSON (texto que começa com `{`), como o `payload` de `extract`.
- **Envelope `brain.task/1`:** `status` é `ok`, `invalid`, `escalate` ou `error`. `escalate` devolve a tarefa ao
  chamador, que a refaz com o próprio modelo; o motivo fica em `reason`: `local_unavailable` (nenhum provedor
  da cadeia respondeu: sem chave, HTTP de erro, rede ou Ollama fora), `timeout` (timeout do provedor ou prazo
  total da tarefa), `schema_invalid` (saída fora do schema depois de 1 retry), `no_valid_label` (`classify` sem
  rótulo do vocabulário) e `input_too_large` (entrada acima de `max_input_tokens` ou de `max_blocks`). Template
  ou tarefa desconhecidos e perfil inexistente voltam como `invalid` (`unknown_template`, `unknown_task`,
  `profile_not_found`). `validate` sem `source` é determinístico e não chama o
  modelo; com `source`, chama o modelo uma vez para conferir o documento contra a fonte.
- **Eventos:** cada chamada vira uma linha em `.runtime/events.jsonl` (rotação 5 MB × 3), com custo local e o custo
  pago equivalente. O texto da tarefa nunca é gravado, só `payload_bytes`, os rótulos `type` e `team` de
  `classify` e `valid` de `validate`. O `from` é `cli`, `task-eval` ou o nome do cliente MCP.
  `event_write_failures` (em `local_tasks_status` e `cli.py task status`) conta as falhas do processo que
  responde, desde que ele iniciou: o do servidor MCP não soma as do CLI, e vice-versa.
- **Latência:** as chamadas MCP são síncronas; pelo Ollama bloqueiam o agente por cerca de 20 s (modelo carregado) a 44–51 s
  (primeira chamada, a frio). O perfil `kiosk` usa `timeout_seconds: 120`; o padrão do núcleo é 30.
- **Limites:** cada `run_task` tem prazo total de `timeout_seconds` × (1 + `retries`) × 2, conferido antes de cada
  chamada ao modelo (estourado, `escalate: timeout` com o custo já gasto); `summarize` com mais de `max_blocks`
  blocos (padrão 4) devolve `escalate: input_too_large` sem chamar o modelo. O timeout de ferramenta do cliente
  MCP precisa ser pelo menos o `timeout_seconds` do perfil; para não cortar retries e o map-reduce de
  `summarize`, use o prazo total.
- **Modelo carregado:** cada chamada pede ao Ollama para manter o modelo na memória por `keep_alive` (perfil,
  padrão `30m`; `-1` = sempre). Sem isso o Ollama descarrega após 5 min e a primeira chamada paga o
  carregamento (44–51 s medidos numa CPU sem GPU dedicada).
- **Qualidade:** `cli.py task-eval` (12 casos, `llama3.2:3b`, 2026-10-13) acertou 92% no geral: `classify` 2 de 3,
  `extract` 3 de 3, `summarize` 3 de 3, `validate` 3 de 3, nenhum `escalate`. Em `extract`, o acerto mede a
  validade do schema (as chaves exigidas presentes), não se os valores extraídos estão certos. A amostra é
  pequena; refaça a medida ao trocar de modelo.

### Provedores de nuvem

O perfil pode definir uma cadeia de provedores (`providers`) que são tentados em ordem
([ADR-018](vault/adrs/ADR-018-provedores-nuvem-com-reserva-local.md)). Se o primeiro falhar (timeout,
erro HTTP, chave ausente), o próximo é tentado. O último é normalmente o Ollama local.

No perfil `kiosk` a cadeia é `deepseek/deepseek-v4-flash-0731` no OpenRouter e o Ollama `llama3.2:3b` de
reserva. Toda requisição à nuvem leva `provider: {data_collection: deny, zdr: true}`: só endpoints sem retenção
de dados e que não coletam nem treinam com o conteúdo. O envelope diz quem respondeu (`cost.tier` `cloud` ou
`local`, `cost.provider`, `cost.model`) e quanto custou (`cost.actual_usd`, pelo `price` do perfil).
`local_tasks_status` lista cada provedor com `configured` (a chave está no ambiente) e `available` (respondeu
à sonda em até 5 s); `model_available` só é verdadeiro se algum provedor tiver os dois.

**Configuração:**

1. Adicione `OPENROUTER_API_KEY` ao `.env` da raiz (nunca versionado; quem edita é o humano). Sem a chave, a
   nuvem é pulada e tudo vai ao Ollama.
2. Fora da raiz (um worktree, por exemplo), aponte para o arquivo com `BRAIN_ENV_FILE`:
   `BRAIN_ENV_FILE=C:/KIOSK/second-brain/.env`.
3. **Trave a privacidade também na conta**, em https://openrouter.ai/settings/privacy: desligue o uso de
   dados para treino/coleta e ligue *Zero Data Retention*. O corpo da requisição já pede isso, mas a trava na
   conta cobre qualquer chamada feita com a mesma chave fora deste núcleo.

**Resultados (`cli.py task-eval`, 2026-10-13, detalhes em
`.superpowers/specs/2026-10-13-12-43-avaliacao-provedores.md`):**

| Modelo (nuvem, ZDR) | Acerto | Latência média | Tiers (9 chamadas) | Custo por chamada |
|---|---|---|---|---|
| `deepseek/deepseek-v4-flash-0731` (escolhido) | 100% | 6,2 s | cloud 9 | US$ 0,000195 |
| `openai/gpt-oss-20b` | 100% | 7,8 s | cloud 9 | US$ 0,000029 |
| `inclusionai/ling-3.0-flash-vl` | 92% | 12,7 s | cloud 5, local 4 (HTTP 429 nos endpoints ZDR) | US$ 0,000007 |

`task-eval --profile kiosk` final: acerto 100%, 9 de 9 chamadas na nuvem, latência mediana 7,2 s mas média
17,6 s por causa de uma resposta de 87,5 s (raciocínio longo; o `timeout_seconds` do provedor é timeout de
leitura, não prazo total), US$ 0,000294 por chamada. Por isso o ADR-018 ainda está `Proposto`.

## Vault

| Pasta | Conteúdo |
|---|---|
| `adrs/` | Decisões com alternativas descartadas (`ADR-NNN-*.md`) |
| `systems/` | Uma nota por sistema ou integração ("como X funciona?") |
| `rules/`, `playbooks/` | Regras de negócio e cenários de teste que as validam; execuções ficam em `.runtime/evidence.db` |
| `domain/` | Marcas e regras de negócio da holding |
| `architecture/` | Guidelines, índices e sínteses de System Design e do MBA Full Cycle |
| `product/` | Visão, PRDs, discovery; `references/` guarda metadados das fontes ingeridas do Drive |
| `teams/` | Times, responsabilidades e `teams.yaml` |
| `daily/` | Diário das sessões, por data |
| `_templates/` | Modelos para cada tipo de nota |

Toda nota começa com frontmatter YAML ([ADR-014](vault/adrs/ADR-014-frontmatter-yaml-como-padrao-de-metadados-do-vault.md)):

```yaml
---
type: adr            # adr | system | architecture | product | reference | team | domain | daily | radar
status: Aceito       # ADRs: Proposto | Aceito | Depreciado | Substituído por ADR-NNN
date: 2026-10-13
---
```

Regras e playbooks usam o frontmatter próprio validado por `cli.py evidence --lint`. Vault em CRLF
(`.gitattributes`). Depois de editar notas: `cli.py sync` e `dashboard\build_graph.py`.

## Ingestão

- `cli.py drive-sync`: o texto extraído fica fora do repositório
  ([ADR-015](vault/adrs/ADR-015-texto-bruto-de-cursos-fora-do-repositorio.md)); a nota de referência guarda o SHA-256
  da origem e não é sobrescrita quando o mesmo arquivo reaparece.
- `ingestion/system_design_sync.py`: indexa o curso de System Design a partir de `SYSTEM_DESIGN_COURSE_ROOT`
  (padrão `~/Downloads/Descomplicando System Design`).
- `ingestion/generate_intelligence_chunks.py`: gera `extracted_system_design/chunks_system_design.json` e
  `dashboard/system-design-chunks.js`.
- `ingestion/scheduler.py`: observa o vault e sincroniza continuamente.

## Testes

Não há CI; o gate é rodado à mão (lista completa em CLAUDE.md, seção 3):

```powershell
# Backend — todos os testes (inclui graph engine, gates, orchestrator)
.\.venv\Scripts\python.exe -m pytest tests/ -v --tb=short

# Frontend — Nexus adapters e simulação (executado da raiz)
node --test --test-isolation=none nexus/tests/adapters.test.mjs

# Dashboard — testes Node.js
node --test dashboard/tests/*.test.cjs
.\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py
```

`integration.test.cjs` compara hashes de citação com os bytes atuais do vault: rode `dashboard\build_graph.py`
antes dele sempre que o vault mudar. Avaliações do motor de busca e dos quality gates: `evals/runner.py`.

**Cobertura atual (2026-10-17):**

| Suíte | Testes | Subtestes | Tempo |
|---|---|---|---|
| Backend (pytest) | 1.212 passed | 242 | ~74s |
| Frontend (Nexus) | 11 passed | — | ~200ms |
| Dashboard (Node) | — | — | — |

O graph engine adiciona **138 testes** dedicados em 5 arquivos:
`test_graph_unit.py`, `test_graph_integration.py`, `test_graph_entrypoint.py`,
`test_graph_nexus_adapter.py`, `test_graph_ws_smoke.py`.

## Arquitetura

O projeto segue **Clean Architecture** com camadas bem definidas e **Dependency Inversion** via protocolos:

| Camada | Diretórios | Responsabilidade |
|---|---|---|
| **Domain** | `core/state.py`, `core/ports.py`, `core/domain/` | Entidades, Value Objects, Ports (protocolos) |
| **Application** | `core/graph/`, `core/gates/`, `core/routing/` | Casos de uso, orquestração, quality gates |
| **Infrastructure** | `core/bootstrap.py`, `core/graph/telemetry.py`, `core/graph/nexus_adapter.py` | Composição, telemetria, adaptadores |
| **Interface** | `backend/`, `nexus/`, `dashboard/` | Transporte (WS, HTTP), UI |

**Princípios aplicados:**

- **SOLID** — SRP por nó, OCP via edges data-driven, ISP com 5 protocolos focados, DIP via `core/ports.py`
- **DDD** — Entidades (`Mission`, `Step`), Value Objects (`Message`, `TokenUsage`), Ports & Adapters
- **Imutabilidade** — `GraphState` usa padrão `{**state, 'field': value}`, dataclasses frozen
- **Hexagonal** — `core/ports.py` define interfaces; `core/bootstrap.py` é o Composition Root

Dependências apontam **sempre para dentro** (Interface → Application → Domain). O `core/` nunca importa de
`backend/` ou `nexus/`; a única exceção transitória é `core/graph/nodes.py` importando constantes de
`backend.orchestrator` (Strangler Fig — será eliminada ao migrar as constantes para `core/domain/`).


# Second Brain — KIOSK Brands

Base de conhecimento de engenharia da KIOSK Brands (Touti, Amavia e Yes! Cosméticos), local e offline.
O **vault** em Markdown é a fonte de verdade; o índice vetorial (Qdrant + Ollama), o grafo do dashboard e as
respostas dos servidores MCP são derivados dele e podem ser reconstruídos.

Regras de trabalho no repositório (proibições, gate de testes, definição de pronto): [CLAUDE.md](CLAUDE.md).

| Peça | Onde | Para quê |
|---|---|---|
| Vault | `vault/` | Notas Markdown: ADRs, sistemas, regras, playbooks, produto, times |
| CLI | `cli.py` | Sincronizar o índice, perguntar com RAG, evidências, trace |
| Servidores MCP | `mcp_servers/` | Ferramentas para IDEs e agentes (busca, ADRs, GitHub, SRV-API, Hub, tarefas locais) |
| BFF | `backend/` | Servidor local com sessão: dashboard, observabilidade e API de workflows |
| Dashboard | `dashboard/` | Interface estática: biblioteca, grafo, consultas, Workflow Studio, observabilidade |
| Ingestão | `ingestion/` | Sync do vault, Google Drive, curso de System Design, chunks de inteligência |

Fora do escopo: o código do Hub Logístico e do SRV-API (outros repositórios, somente leitura daqui) e os
resultados de análise 360 (`C:/KIOSK/analise-360`).

## Instalação

Requer Python 3 e, para os testes do dashboard, Node 24.

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
  chamador (modelo local fora do ar, entrada acima do limite, saída fora do schema depois de 1 retry, tempo
  esgotado): o núcleo nunca chama fornecedor pago, então o agente refaz a tarefa. Template ou tarefa
  desconhecidos e perfil inexistente voltam como `invalid` (`unknown_template`, `unknown_task`,
  `profile_not_found`). O motivo fica em `reason`. `validate` sem `source` é determinístico e não chama o
  modelo; com `source`, chama o modelo uma vez para conferir o documento contra a fonte.
- **Eventos:** cada chamada vira uma linha em `.runtime/events.jsonl` (rotação 5 MB × 3), com custo local e o custo
  pago equivalente. O texto da tarefa nunca é gravado, só `payload_bytes`, os rótulos `type` e `team` de
  `classify` e `valid` de `validate`. O `from` é `cli`, `task-eval` ou o nome do cliente MCP.
  `event_write_failures` (em `local_tasks_status` e `cli.py task status`) conta as falhas do processo que
  responde, desde que ele iniciou: o do servidor MCP não soma as do CLI, e vice-versa.
- **Latência:** as chamadas MCP são síncronas e bloqueiam o agente por cerca de 20 s (modelo carregado) a 44–51 s
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

**Configuração:**

1. Adicione `OPENROUTER_API_KEY=sk-or-v1-...` ao arquivo `.env` (nunca versionado).
2. Defina `BRAIN_ENV_FILE` para apontar para o `.env` se o CLI não rodar na raiz:
   `BRAIN_ENV_FILE=C:/KIOSK/second-brain/.env`.
3. Em https://openrouter.ai/settings/privacy, marque **data_collection: deny** e ative o ZDR
   (zero data retention) para os modelos usados.
4. O motivo `local_unavailable` no envelope indica que nenhum provedor (nuvem + local) estava
   disponível; `escalate` com outro motivo indica que o modelo respondeu mas a saída não cumpriu
   o schema.

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
.\.venv\Scripts\python.exe -m unittest tests.test_components tests.test_bff_wave1 tests.test_hardening tests.test_tracing tests.test_trace_middleware tests.test_trace_servers tests.test_trace_cli tests.test_evidence tests.test_evidence_store tests.test_evidence_tools tests.test_evidence_cli tests.test_evidence_seed tests.test_gates tests.test_memory tests.test_workflow_api tests.test_drive_sync tests.test_protocol tests.test_agnostic_core tests.test_events tests.test_local_tasks tests.test_local_tasks_mcp tests.test_local_tasks_cli tests.test_providers tests.test_openai_compat_client
node --test --test-isolation=none dashboard/tests/*.test.cjs
.\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py
```

`integration.test.cjs` compara hashes de citação com os bytes atuais do vault: rode `dashboard\build_graph.py`
antes dele sempre que o vault mudar. Avaliações do motor de busca e dos quality gates: `evals/runner.py`.

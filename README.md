# Second Brain — KIOSK Brands

Base de conhecimento de engenharia da KIOSK Brands (Touti, Amavia e Yes! Cosméticos), local e offline.
O **vault** em Markdown é a fonte de verdade; o índice vetorial (Qdrant + Ollama), o grafo do dashboard e as
respostas dos servidores MCP são derivados dele e podem ser reconstruídos.

Regras de trabalho no repositório (proibições, gate de testes, definição de pronto): [CLAUDE.md](CLAUDE.md).

| Peça | Onde | Para quê |
|---|---|---|
| Vault | `vault/` | Notas Markdown: ADRs, sistemas, regras, playbooks, produto, times |
| CLI | `cli.py` | Sincronizar o índice, perguntar com RAG, evidências, trace |
| Servidores MCP | `mcp_servers/` | Ferramentas para IDEs e agentes (busca, ADRs, GitHub, SRV-API, Hub) |
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
.\.venv\Scripts\python.exe -m unittest tests.test_components tests.test_bff_wave1 tests.test_hardening tests.test_tracing tests.test_trace_middleware tests.test_trace_servers tests.test_trace_cli tests.test_evidence tests.test_evidence_store tests.test_evidence_tools tests.test_evidence_cli tests.test_evidence_seed tests.test_gates tests.test_memory tests.test_workflow_api tests.test_drive_sync
node --test --test-isolation=none dashboard/tests/*.test.cjs
.\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py
```

`integration.test.cjs` compara hashes de citação com os bytes atuais do vault: rode `dashboard\build_graph.py`
antes dele sempre que o vault mudar. Avaliações do motor de busca e dos quality gates: `evals/runner.py`.

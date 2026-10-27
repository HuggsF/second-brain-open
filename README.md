# Second Brain (open version)

Motor local de conhecimento e orquestração de agentes. Um **vault** em Markdown é a fonte de verdade. O índice
vetorial (Qdrant + Ollama), as respostas dos servidores MCP e a interface de agentes são derivados dele.

Esta é uma versão genérica, sem dados de nenhuma organização. O vault não vem incluído: aponte `config.py`
para o seu.

## O que tem aqui

| Peça | Onde | Para quê |
|---|---|---|
| Graph Engine | `core/graph/` | Orquestrador de missões em 7 nós assíncronos, com circuit breakers e aprovação humana (HITL) |
| Quality gates | `core/gates/` | DAG, DLP, grounding, regras e idempotência antes e depois de cada missão |
| Resiliência | `core/resilience/` | Circuit breaker e rate limiter por ferramenta |
| Política | `core/policy/` | Decisão APPROVE, ESCALATE ou DENY por identidade, ferramenta e comando |
| Ports | `core/ports.py` | Interfaces (Protocol) que isolam o núcleo da infraestrutura |
| Protocolo e tarefas locais | `core/protocol/`, `core/local_tasks/` | Contratos de mensagem e tarefas pequenas em modelo local |
| Evidências e rastreio | `core/evidence.py`, `core/tracing.py` | Ligação entre regras, testes executados e chamadas MCP, com campos sensíveis mascarados |
| Servidor MCP | `mcp_servers/local_tasks_mcp.py` | Ferramentas `classify`, `extract`, `summarize`, `validate` |
| Backend | `backend/` | Orquestrador, WebSocket e API de workflows |
| Nexus | `nexus/` | Interface React + Vite que mostra as missões dos agentes |
| Avaliação | `evals/` | Casos de referência (exemplo fictício) e métricas |

## Instalação

Requer Python 3.14+ e Node.js 22.12+ (para o Nexus).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
docker compose up -d          # Qdrant (6333) e Ollama (11434)
```

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

## Limites desta versão

- Sem vault: comandos que leem notas (`cli.py sync`, `ask`) precisam de um vault seu.
- Sem adaptadores de infraestrutura: `core/tools.py` e `core/bootstrap.py` aceitam um executor de comandos
  e um coletor de observações, mas nenhum vem implementado.
- O dashboard estático do projeto original não foi incluído.

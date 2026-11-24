# Second Brain (open version)

Motor local de conhecimento e orquestração de agentes. Um **vault** em Markdown é a fonte de verdade. O índice
de busca (um arquivo SQLite), as respostas dos servidores MCP e a interface de agentes são derivados dele.

Esta é uma versão genérica, sem dados de nenhuma organização. O vault não vem incluído: aponte a variável
`BRAIN_VAULT_DIR` para o seu.

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
| Busca | `core/indice_texto.py`, `core/retriever.py`, `ingestion/sync.py` | Índice de texto completo em SQLite (FTS5), sem serviço nenhum |
| Avaliação | `evals/` | Casos de referência (exemplo fictício) e métricas |

## Fichas de projeto

Uma ficha é uma pasta de Markdown por projeto, em `fichas/`: visão, especificação, arquitetura, decisões,
prontidão, auditorias por etapa e processos humanos. Cada seção declara o padrão de onde veio, e a ficha
encolhe conforme o porte do projeto.

- [`fichas/second-brain-open/`](fichas/second-brain-open/ficha.md): este repositório, descrito como está.
- [`fichas/rag-dojo/`](fichas/rag-dojo/ficha.md): um projeto de estudo de RAG.

```bash
.venv/Scripts/python cli.py ficha nova meu-projeto --nome "Meu Projeto" --porte pequeno
.venv/Scripts/python cli.py ficha validar      # sai com 1 se alguma ficha tiver problema
```

## Instalação

Requer Python 3.14+, com SQLite 3.43 ou mais novo (FTS5), e Node.js 22.12+ (para o Nexus). Não precisa de
Docker.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

## Busca

```bash
export BRAIN_VAULT_DIR=/caminho/do/seu/vault      # o repositório não traz um
.venv/Scripts/python cli.py sync                 # indexa o vault em .runtime/indice-busca.db
.venv/Scripts/python cli.py buscar "uma pergunta"  # trechos encontrados, sem chamar modelo
.venv/Scripts/python cli.py status               # estado do índice e do vault
.venv/Scripts/python cli.py ask "uma pergunta"     # gera a resposta; pede um servidor local de modelos
```

`BRAIN_INDEX_PATH` muda o arquivo do índice. Caminho relativo, nas duas variáveis, resolve contra a raiz do
repositório.

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

## Limites desta versão

- Sem vault: `sync`, `buscar` e `ask` precisam de um vault seu.
- A busca é por palavras, e o piso de relevância não foi medido neste repositório: o padrão é só um corte
  relativo ao melhor resultado (`RETRIEVAL_MIN_SCORE` e `RETRIEVAL_MAX_DROP` ajustam).
- `ask` gera a resposta em um servidor local de modelos (`OLLAMA_URL`), que você sobe por conta própria.
  Sem ele, `ask` mostra as fontes e sai com 1; `buscar` não precisa dele.
- Sem adaptadores de infraestrutura: `core/tools.py` e `core/bootstrap.py` aceitam um executor de comandos
  e um coletor de observações, mas nenhum vem implementado.
- O dashboard estático do projeto original não foi incluído.

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
.venv/Scripts/python cli.py ask "uma pergunta"     # gera a resposta pela cadeia de provedores do perfil
```

`BRAIN_INDEX_PATH` muda o arquivo do índice. Caminho relativo, nas duas variáveis, resolve contra a raiz do
repositório.

## Demandas

Uma demanda é um pedido de mudança em um projeto que tem ficha. Ela é triada, segue por fases com portões,
e os rascunhos dos seus artefatos são gravados dentro da ficha, em `fichas/<projeto>/demandas/<id>/`.

```bash
.venv/Scripts/python cli.py demanda nova "Título" --descricao "Texto do pedido"
.venv/Scripts/python cli.py gerar-artefatos DEM-001      # rascunho da triagem; depois, os da fase
.venv/Scripts/python cli.py demanda mostrar DEM-001      # fase, triagem e o que falta
.venv/Scripts/python cli.py demanda triar DEM-001 --aprovar-por gestor-demandas --trilha completa
.venv/Scripts/python cli.py demanda avancar DEM-001 --ator gestor-demandas
```

A triagem responde quatro perguntas e escolhe uma trilha (`operacional`, `correcao_direta`, `leve`,
`completa`); o guia está em `profiles/example/guia_triagem.md` e o catálogo de produtos em
`profiles/example/produtos.yaml`. Quem aprova é um papel, não uma pessoa.

As páginas geradas nascem com `status: proposta` e não abrem portão: uma pessoa revisa e troca o status.
`gerar-artefatos` não altera página existente; com `--refazer`, apaga e regera só as que ainda estão em
`proposta`. O passo a passo está no
[runbook](fichas/second-brain-open/08-processos/runbook-conduzir-uma-demanda.md). `DOCS_REPO_PATH` aponta
outra pasta de documentos, se você não quiser os rascunhos dentro de `fichas/`.

## Resposta, custo e orçamento

`ask` e `task` geram pela cadeia de provedores do perfil ativo (`profiles/example/profile.yaml`, ou o que
`BRAIN_PROFILE` apontar). Sem cadeia declarada, a geração usa um servidor local de modelos (`OLLAMA_URL`)
e o gasto registrado é zero.

```bash
.venv/Scripts/python cli.py budget               # estado, gasto e limite do dia e do mês
.venv/Scripts/python cli.py budget --history 7   # gasto por dia
.venv/Scripts/python cli.py budget --rebuild     # refaz o banco de orçamento a partir do log de eventos
```

Cada resposta diz quem gerou e quanto custou. Com o orçamento esgotado, nenhuma chamada vai à nuvem: a
cadeia usa só provedores locais, ou o `ask` mostra as fontes e sai com 1, e `task` sai com 3.

Para usar um provedor de nuvem compatível com a API da OpenAI, descomente o bloco `providers` do perfil de
exemplo. A chave fica em uma variável de ambiente, nunca no perfil. Conteúdo de tarefa só deve ir a
provedor que declare retenção zero e recusa de coleta ou treino; o motor repassa essa declaração ao
provedor, mas não confere se ele a cumpre.

## Testes

```bash
.venv/Scripts/python -m pytest -q
```

## Limites desta versão

- Sem vault: `sync`, `buscar` e `ask` precisam de um vault seu.
- A busca é por palavras, e o piso de relevância não foi medido neste repositório: o padrão é só um corte
  relativo ao melhor resultado (`RETRIEVAL_MIN_SCORE` e `RETRIEVAL_MAX_DROP` ajustam).
- `ask` e `task` precisam de um modelo: um servidor local (`OLLAMA_URL`), que você sobe por conta própria,
  ou um provedor de nuvem declarado no perfil. Sem nenhum, `ask` mostra as fontes e sai com 1; `buscar`
  não precisa de modelo.
- A geração nunca foi testada aqui contra modelo real nem provedor de nuvem: os testes usam clientes
  falsos. O prazo de 120 segundos do perfil de exemplo é uma estimativa.
- Demandas só pela linha de comando: não há API nem quadro, nem comando para bloquear, cancelar ou
  devolver para retrabalho.
- A trilha completa não chega a `done` sozinha: o portão de entrega pede um arquivo de rastreio entre
  exemplos de regra e testes, e o verificador que o produz não está neste repositório.
- Os rascunhos de artefatos nunca foram gerados aqui com modelo real, e o catálogo de atividades do guia
  de triagem de exemplo é fictício.
- Sem adaptadores de infraestrutura: `core/tools.py` e `core/bootstrap.py` aceitam um executor de comandos
  e um coletor de observações, mas nenhum vem implementado.
- O dashboard estático do projeto original não foi incluído.

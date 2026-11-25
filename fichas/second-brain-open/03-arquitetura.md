---
secao: 3
origem: C4 níveis 1 e 2; arc42 reduzido
aplica: sim
---
# Arquitetura

## Contexto

```mermaid
flowchart LR
    pessoa[Quem mantém o conhecimento] -->|linha de comando e interface| motor[Second Brain]
    agente[Agente de IA no editor] -->|MCP| motor
    motor -->|lê| vault[(Vault em Markdown)]
    motor -->|índice de texto| indice[(Arquivo SQLite)]
    motor -.->|geração do ask e das tarefas, opcional| modelos[Servidor local de modelos]
    motor -.->|só se o perfil declarar, dentro do orçamento| nuvem[Provedor de nuvem]
    motor -->|custo de cada chamada| gasto[(Banco de orçamento em SQLite)]
    motor -->|fase e artefatos de cada demanda| demandas[(Banco de demandas em SQLite)]
    motor -->|rascunhos de cada demanda| fichas[(Fichas de projeto em Markdown)]
```

## Contêineres

```mermaid
flowchart TB
    cli[cli.py<br/>sync, buscar, ask, budget, task, demanda, gerar-artefatos, status, trace, evidence, ficha]
    ingestao[ingestion/<br/>sync do vault para o índice]
    mcp[mcp_servers/<br/>tarefas locais]
    backend[backend/<br/>orquestrador, WebSocket, API de fluxos]
    nexus[nexus/<br/>interface React, protótipo]
    subgraph nucleo[core/]
        grafo[graph/<br/>missão em nós assíncronos]
        portoes[gates/<br/>portões de qualidade]
        politica[policy/<br/>aprovar, escalar, negar]
        resil[resilience/<br/>disjuntor e limite de taxa]
        evid[evidence e tracing<br/>regra, teste, rastreio]
        portas[ports.py<br/>interfaces para a infraestrutura]
        busca[indice_texto e retriever<br/>busca de texto completo]
        cadeia[local_tasks, cost e budget<br/>cadeia de provedores, custo e orçamento]
        demanda[demand_lifecycle e triagem<br/>fases, trilhas e portões]
        geracao[geracao, docs_registry e produtos<br/>rascunhos dentro da ficha]
    end
    cli --> nucleo
    cli --> ingestao
    ingestao --> busca
    mcp --> nucleo
    busca -->|gera a resposta| cadeia
    geracao -->|redige o rascunho| cadeia
    geracao -->|contexto do vault| busca
    geracao -->|grava o vínculo| demanda
    demanda -->|lê o status das páginas| geracao
    backend --> grafo
    nexus -->|WebSocket| backend
    grafo --> portoes
    grafo --> politica
    grafo --> resil
```

## Estratégia

- **Fonte única em arquivos.** O vault é a verdade; índice e respostas são derivados.
- **Núcleo sem infraestrutura.** `core/ports.py` define as interfaces; quem instala fornece os adaptadores.
- **Decisão centralizada.** Nenhum módulo fora de `core/policy/` mantém lista de comandos permitidos.
- **Tudo local e sem serviço para buscar.** O índice é um arquivo SQLite derivado do vault; só a geração
  (`ask` e tarefas) usa um modelo.
- **Um caminho de geração, com custo e teto.** `ask` e tarefas passam pela mesma cadeia de provedores do
  perfil; cada chamada registra o custo, e o orçamento barra a nuvem quando esgota
  ([ADR-006](04-decisoes/ADR-006-resposta-pela-cadeia.md)).
- **A demanda deixa rastro na ficha.** Uma demanda tem trilha e portões por fase; os rascunhos dos
  artefatos são gravados dentro da ficha do projeto e só valem depois de revisados por uma pessoa
  ([ADR-007](04-decisoes/ADR-007-demanda-na-ficha.md)).

## Riscos

| Risco | Efeito | Situação |
|---|---|---|
| Piso de relevância não medido | A busca pode devolver trecho fraco ou cortar trecho bom | Em aberto, até existir vault de exemplo |
| Busca por palavras | Pergunta com vocabulário diferente da nota não acha nada | Aceito; a busca devolve a lacuna |
| Geração com modelo real sem cobertura de teste | `ask` e tarefas só são verificados com clientes falsos | Em aberto |
| Garantias de privacidade do provedor de nuvem só declaradas | O motor repassa a declaração e não confere se o provedor a cumpre | Aceito e declarado no perfil de exemplo |
| Gasto do `ask` só no banco de orçamento | Se o banco se perder, a reconstrução não traz esse gasto e a nuvem volta a ser liberada | Em aberto |
| Prazo de 120 s do perfil de exemplo não medido | Pode sobrar ou faltar para um modelo local | Em aberto |
| Sem verificador de rastreio | A trilha completa não chega a `done` sem um arquivo produzido fora do repositório | Aceito e declarado no ADR-007 |
| Geração de rascunhos sem teste com modelo real | A qualidade dos rascunhos nunca foi medida aqui | Em aberto, até a demanda de exemplo |
| `--refazer` descarta edição à mão | Página em `proposta` editada e não validada é apagada | Aceito; a ajuda do comando avisa |
| Demanda só pela linha de comando | Sem bloqueio, cancelamento nem retrabalho por comando | Em aberto |
| Sem adaptadores de infraestrutura | Ferramentas de comando não executam nada | Aceito e declarado no README |
| Sem integração contínua | Regressão só aparece quando alguém roda a suíte | Em aberto |

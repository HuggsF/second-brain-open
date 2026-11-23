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
    motor -->|embeddings e respostas| modelos[Servidor local de modelos]
    motor -->|índice| vetores[(Banco vetorial local)]
```

## Contêineres

```mermaid
flowchart TB
    cli[cli.py<br/>sync, ask, trace, evidence, ficha]
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
    end
    cli --> nucleo
    mcp --> nucleo
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
- **Tudo local.** Os serviços auxiliares sobem por `docker-compose.yml` na própria máquina.

## Riscos

| Risco | Efeito | Situação |
|---|---|---|
| Dois serviços locais obrigatórios para a busca | Instalação mais pesada; `ask` falha sem eles | Em aberto |
| 92 testes assíncronos não rodam por falta de uma dependência de teste | O grafo de missão e o WebSocket estão sem verificação | Pendência da auditoria de construção |
| Sem adaptadores de infraestrutura | Ferramentas de comando não executam nada | Aceito e declarado no README |
| Sem integração contínua | Regressão só aparece quando alguém roda a suíte | Em aberto |

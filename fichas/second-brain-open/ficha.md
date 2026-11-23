---
slug: second-brain-open
nome: "Second Brain (versão aberta)"
porte: medio
estado: ativo
repositorio: https://github.com/HuggsF/second-brain-open
data: 2026-11-23
origem: Canvas de uma página do arc42
---
# Second Brain (versão aberta)

Motor local de conhecimento e orquestração de agentes. Esta ficha descreve o repositório como ele está
hoje, inclusive o que ainda não funciona: a situação da ficha vem da auditoria, não deste texto.

## O que é

Um vault em Markdown é a fonte de verdade. O índice de busca, as respostas do servidor MCP e a interface de
agentes são derivados dele. Em volta disso há um orquestrador de missões com portões de qualidade, uma
política central que decide o que cada agente pode executar, e um registro que liga regra, teste executado
e chamada de ferramenta.

## Para quem

Uma pessoa ou um time pequeno que quer agentes de IA trabalhando sobre o próprio conhecimento de
engenharia, na própria máquina, com limites explícitos do que o agente pode fazer.

## Onde está cada coisa

| Seção | Arquivo |
|---|---|
| Visão de negócio | [01-visao.md](01-visao.md) |
| Especificação | [02-especificacao.md](02-especificacao.md) |
| Arquitetura | [03-arquitetura.md](03-arquitetura.md) |
| Decisões | [04-decisoes/](04-decisoes/) |
| Prontidão | [05-prontidao.md](05-prontidao.md) |
| Auditorias por etapa | [06-auditorias/](06-auditorias/) |
| Processos humanos | [08-processos/](08-processos/) |

Por ser de porte médio, a ficha não tem operação, privacidade nem execução por agente.

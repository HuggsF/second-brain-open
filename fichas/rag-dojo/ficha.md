---
slug: rag-dojo
nome: "RAG Dojo"
porte: pequeno
estado: ativo
repositorio: https://github.com/HuggsF/rag-dojo
data: 2026-11-23
origem: Canvas de uma página do arc42
---
# RAG Dojo

Projeto de estudo de RAG (geração com recuperação) em seis espirais, da divisão de texto em trechos até um
laço de auto-melhoria. Esta ficha descreve o repositório público como ele está na branch `main`.

## O que é

Seis pacotes Python independentes, cada um com testes, em que cada espiral usa só o que a anterior exporta.
Não é um sistema de produção: o próprio README diz isso, e ainda não há resultado de benchmark publicado.

## Para quem

Quem quer aprender a pilha de RAG por etapas, com padrões de produção desde a primeira (testes, cobertura
mínima, contratos entre pacotes).

## Onde está cada coisa

| Seção | Arquivo |
|---|---|
| Visão de negócio | [01-visao.md](01-visao.md) |
| Arquitetura | [03-arquitetura.md](03-arquitetura.md) |
| Decisões | [04-decisoes/](04-decisoes/) |

Por ser de porte pequeno, a ficha não tem especificação, prontidão, auditorias, operação, processos,
privacidade nem execução por agente.

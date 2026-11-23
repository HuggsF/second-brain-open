---
secao: 1
origem: Pitch do Shape Up
aplica: sim
---
# Visão de negócio

## Problema

RAG costuma ser aprendido por partes soltas: um tutorial de embeddings, outro de grafo, outro de custo.
Falta um caminho único em que cada conceito se apoia no anterior e em que dá para ver, no código, por que
a etapa seguinte existe.

## Apetite

Seis espirais, e não mais. O repositório não registra prazo; o limite é de escopo: cada espiral é um pacote
independente, com sua própria suíte de testes.

## Solução

Um repositório em que cada espiral é um pacote Python independente:

1. trechos, embeddings e recuperação vetorial;
2. extração de entidades, grafo e recuperação híbrida;
3. pontuação de confiança e fallback em cascata;
4. memória e detecção de padrões;
5. contagem de tokens, custo, orçamento e roteamento de modelo;
6. laço de propor, resolver e verificar, com suíte de benchmark.

As dependências vão só para frente. Os dados de treino são documentação pública de código aberto.

## Armadilhas

- A camada gratuita do provedor de modelo tem limite diário; sem o modelo local de reserva, uma sessão de
  estudo para no meio.
- Seis pacotes que só dependem para frente exigem disciplina: um import de volta quebra a independência.
- Não há resultado de benchmark publicado, então nenhuma espiral pode alegar ganho medido.

## Fora de escopo

- Uso em produção.
- Dados de cliente ou de negócio.
- Infraestrutura paga: só o custo de chamadas ao modelo é aceito, e a escolha foi a camada gratuita.

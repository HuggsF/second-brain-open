---
secao: 3
origem: C4 níveis 1 e 2; arc42 reduzido
aplica: sim
---
# Arquitetura

## Contexto

```mermaid
flowchart LR
    estudante[Quem estuda] -->|linha de comando| dojo[RAG Dojo]
    dojo -->|gera respostas e extrai entidades| nuvem[Provedor de modelo, camada gratuita]
    dojo -->|reserva quando o limite estoura| local[Modelo local]
    docs[Documentação pública de código aberto] -->|ingestão| dojo
```

## Contêineres

```mermaid
flowchart LR
    cli[CLI e fábrica de pipeline] --> s1
    s1["Espiral 1<br/>trechos, embeddings, recuperação"] --> s2["Espiral 2<br/>entidades, grafo, recuperação híbrida"]
    s2 --> s3["Espiral 3<br/>confiança e fallback"]
    s3 --> s4["Espiral 4<br/>memória e padrões"]
    s4 --> s5["Espiral 5<br/>tokens, custo, orçamento"]
    s5 --> s6["Espiral 6<br/>propor, resolver, verificar"]
    s1 --- vetores[(Banco vetorial em disco)]
    s2 --- grafo[(Banco de grafo)]
```

## Estratégia

- **Espirais independentes.** Cada pacote usa apenas os símbolos exportados pelo anterior, sem import
  circular. Uma espiral quebrada não derruba as de antes.
- **Banco vetorial embutido.** Roda no mesmo processo e grava em disco, para que a integração contínua não
  precise de servidor.
- **Modelo gratuito com reserva local.** O provedor de nuvem é o principal; o modelo local assume quando o
  limite diário estoura.
- **Testes como contrato.** O README registra cerca de 900 funções de teste e mínimo de 90% de cobertura
  por arquivo.

## Riscos

| Risco | Efeito | Situação |
|---|---|---|
| Limite da camada gratuita | Sessão interrompida | Coberto pela reserva local |
| Sem benchmark publicado | Não há como afirmar ganho de uma espiral sobre a outra | Em aberto |
| Banco de grafo exige serviço à parte a partir da espiral 2 | Ambiente mais pesado para quem começa | Aceito |

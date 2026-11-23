---
id: ADR-005
status: aceito
data: 2026-11-23
---
# Busca de texto completo em SQLite, sem banco vetorial

## Contexto

Para buscar no vault, o motor pedia dois serviços: um banco vetorial e um servidor de modelos que gerava
os embeddings. Eram dois processos para subir e vigiar em um motor feito para uma pessoa manter sozinha.
Além disso, o comando `sync` deste repositório nunca funcionou: importava um módulo de ingestão que não
tinha sido publicado. Código que sustenta a decisão: `core/indice_texto.py`, `core/consulta_texto.py`,
`ingestion/sync.py`, `core/retriever.py` e o teste `tests/test_sem_motor_vetorial.py`, que falha se o motor
vetorial voltar.

O desenho foi construído e medido antes pelo mesmo autor, em um vault privado. Os números dessa medição
não valem para este repositório e não são publicados aqui.

## Opções consideradas

1. **Texto completo em SQLite (FTS5), no próprio processo.** Um arquivo derivado do vault, sem serviço e
   sem dependência nova, ordenado por BM25 com pesos por título, seção, caminho e corpo.
2. **Vetores dentro do processo.** Tira os dois serviços, mas mantém um modelo de embedding para baixar e
   a reconstrução do índice a cada troca de modelo.
3. **Manter o banco vetorial só como armazenamento.** Continua sendo um serviço para subir e vigiar.

## Decisão

Opção 1. O índice fica em um arquivo SQLite (`.runtime/indice-busca.db`, ou onde `BRAIN_INDEX_PATH`
apontar), é reconstruído pelo `sync` e nunca é commitado. O manifesto de hashes das notas vive no mesmo
arquivo, gravado na mesma transação que os trechos. A busca aplica um corte relativo ao melhor resultado,
devolve um trecho por nota e recusa pergunta com nome próprio que não aparece no vault.

Esta decisão substitui o trecho do [ADR-001](ADR-001-vault-como-fonte.md) que fala em índice vetorial; o
resto dele continua valendo.

## Consequências

- `sync`, `buscar` e `status` funcionam sem Docker e sem servidor de modelos.
- Uma pergunta cujas palavras não aparecem na nota não acha nada. A busca devolve a lacuna em vez de um
  vizinho errado, e quem pergunta pode reformular.
- O piso absoluto de relevância não foi medido neste repositório: sem um vault de exemplo e um conjunto de
  perguntas de referência não há o que medir. O padrão é só o corte relativo.
- O índice pede SQLite 3.43 ou mais novo, com FTS5.
- A resposta do `ask` continua dependendo de um servidor local de modelos, agora opcional e isolado atrás
  de um gerador que pode ser trocado.

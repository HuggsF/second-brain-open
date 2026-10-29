---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-29
related: [ADR-034, ADR-037]
---
# ADR-039: Piso medido (0.70 / 0.10) e um trecho por nota aplicado na busca

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
O primeiro `cli.py retrieval-eval` com o índice reconstruído (2026-10-29, `evals/reports/retrieval-20261029-0901.json`, git-ignored) saiu com exit 1. No piso provisório da ADR-034 (`0.65` / `0.10` / `max_per_doc 2`), o recall@5 era 83% e só 73% dos negativos ficavam sem fonte. O único par que limpava todos os negativos (`0.75`) derrubava o recall para 61%.

Dois problemas apareceram:
- **Candidatos tomados por uma nota longa.** `max_per_doc` era aplicado depois da busca, sobre `limit * 3` hits do Qdrant. `product/prd-hub-logistico.md` tem 16 trechos e ocupava os 15 candidatos da pergunta sobre pedido sem objeto logístico; nem a RULE-005 nem `systems/hub-logistics-preflight.md` chegavam à seleção.
- **Scores comprimidos.** Com `nomic-embed-text`, as notas esperadas ficam entre 0,67 e 0,75 e os negativos chegam a 0,69 a 0,74. Nenhum piso sozinho separa os dois grupos; quem separa é o gate de termo da ADR-037.

## Alternativas Consideradas
- **Seguir a ADR-037 D5 e não mudar o piso até o eval sair 0:** descartada. Com o modelo de embedding atual nenhum par sai 0, e o piso provisório (`0.65`) deixa passar 27% dos negativos, pior que `0.70` em tudo.
- **Adotar o par sugerido pelo eval (`0.75` / `0.10`):** descartada. Limpa todos os negativos, mas o recall cai para 64%, abaixo do mínimo de 80%.
- **Aumentar só o número de candidatos (`limit * 10`):** descartada. Adia o problema: várias notas longas juntas voltam a ocupar o conjunto.
- **Manter `max_per_doc 2` com o agrupamento na busca:** medida e descartada. O recall continua em 83%, porque duas ou três notas ainda ocupam o top 5.

## Decisão
1. **D1, diversidade na busca.** `QdrantStore.search(per_doc=N)` usa `query_points_groups` agrupado por `file_path`: até `limit` notas, no máximo `N` trechos cada, por score decrescente. O retriever passa `settings.retrieval_max_per_doc`, e o `retrieval-eval` mede o mesmo conjunto de candidatos da produção.
2. **D2, um trecho por nota.** `RETRIEVAL_MAX_PER_DOC` passa de 2 para 1.
3. **D3, piso medido.** `RETRIEVAL_MIN_SCORE 0.70` e `RETRIEVAL_MAX_DROP 0.10`. Substitui a ADR-037 D5 só neste ponto: o piso pode mudar com o eval saindo 1 quando o par escolhido tem recall acima do mínimo e é melhor que o anterior nas duas medidas; o eval continua sugerindo pelo critério dela.

## Consequências
- **Medição (2026-10-29, `retrieval-20261029-0910.json`, com gate):** recall@5 89%, 97% dos negativos sem fonte, 3 de 3 limites conhecidos sem fonte. A RULE-005 volta a aparecer na pergunta do objeto logístico.
- **Ainda vaza um negativo:** uma pergunta sobre uma plataforma de cotação de frete sem registro no vault, cujo nome tem duas palavras comuns e escapa do gate de termo.
- **Ainda faltam no top 5:** RULE-001, RULE-004, PB-013, `systems/sults.md` e `systems/hub-logistics-preflight.md`, cada um numa pergunta. A nota certa tem score menor que vizinhas parecidas; é limite do embedding, não dos candidatos.
- **Contexto da resposta:** com um trecho por nota, a resposta do assistente (ADR-038) recebe até 4 notas diferentes, um trecho de cada, em vez de dois trechos da mesma nota.
- **Fora desta decisão:** trocar o modelo de embedding, busca híbrida e reordenação (rerank).

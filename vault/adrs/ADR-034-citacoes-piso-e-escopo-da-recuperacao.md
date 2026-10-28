---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-28
related: [ADR-033, ADR-021]
---
# ADR-034: Citações verificáveis, piso de relevância e escopo na recuperação vetorial

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
Depois da onda A (ADR-033), a recuperação vetorial ainda devolvia os top-k do Qdrant sem dizer de onde vinha cada trecho nem se havia evidência. Quatro lacunas: o trecho não trazia as linhas do arquivo original nem o hash do documento, então não dava para conferir a citação; a busca sempre devolvia algo, mesmo para uma pergunta fora do vault, e `BrainRetriever.answer()` mandava esse contexto fraco ao modelo; nenhum ponto guardava o espaço (`space_id`) e a busca não filtrava por ele; e o BFF não tinha endpoint de recuperação (`semantic_retrieval` era `false`). A avaliação existente (`evals/runner.py`) reportava um recall que não media a recuperação real.

Quatro decisões foram necessárias: o que identifica uma citação (D1), como declarar ausência de evidência (D2), como impor o escopo do espaço (D3) e onde a recuperação é exposta e avaliada (D4).

## Alternativas Consideradas
- **Piso absoluto fixo (um único `min_score` para sempre):** descartada. O score do `nomic-embed-text` não tem escala calibrada entre consultas; um corte fixo ou deixa passar ruído quando todos os hits são medianos ou corta resultados bons quando o melhor é só razoável. O piso adotado combina um mínimo absoluto com uma queda máxima em relação ao melhor hit, e os valores são calibrados por avaliação.
- **Classificação por nota (marcar cada nota como "evidência" ou "contexto"):** descartada. Exige curadoria manual de todo o vault, envelhece a cada edição e não resolve a pergunta sem resposta; a decisão de "há evidência" depende da consulta, não da nota.
- **Endpoint adiado para a onda seguinte:** descartada. Sem o endpoint, o contrato `POST /v1/retrievals` ficaria sem consumidor e as citações só seriam provadas por testes unitários. Expor no BFF, com sessão e guarda de mesma origem, é pequeno e fecha o ciclo.
- **Citação por afirmação (mapear cada frase da resposta a um trecho):** descartada. Exige um verificador de suporte (outro modelo ou regras) e uma avaliação própria; fica para a fase de `POST /v1/answers`. Nesta onda a citação identifica o trecho recuperado, não prova uma conclusão.

## Decisão
1. **D1 — citação identifica documento, seção, linhas e hash.** O chunker registra `line_start` e `line_end` no arquivo original (base 1, intervalo fechado; CRLF conta como uma quebra; o deslocamento do frontmatter entra na conta), sem alterar `content` nem `id`. O sync e a reconstrução gravam `doc_sha256` (o mesmo do manifesto) e `space_id` em cada ponto. `core/citations.py` define `Citation` (`document, section, line_start, line_end, sha256, score, stale`) e `build_citations`; a citação é `stale` quando o hash indexado difere do hash atual do arquivo, o arquivo sumiu, o resolvedor recusou o caminho ou não há hash.
2. **D2 — piso de relevância e lacunas explícitas.** `select_hits` aplica o piso: se o melhor score fica abaixo de `min_score`, nada passa; senão ficam os hits com `score >= min_score` e `score >= topo - max_drop`, depois no máximo `max_per_doc` por documento, depois `limit` (`limit <= 0` não devolve nada). `gaps_for` produz três textos exatos de lacuna, e "sem evidência" só aparece quando o topo está abaixo de `min_score`. `BrainRetriever.answer()` ganha `status` (`ok`, `no_evidence`, `model_error`); com `no_evidence` o modelo não é chamado. Valores provisórios em `config.py`: `min_score 0.65`, `max_drop 0.10`, `max_per_doc 2`.
3. **D3 — escopo por espaço.** `settings.space_id` vem de `BRAIN_SPACE`. `QdrantStore.search(..., space_id=...)` filtra por espaço, e `index_version()` devolve a coleção real por trás do alias (ADR-033). Um ponto sem `space_id` não é devolvido a uma busca com espaço.
4. **D4 — mesma lista em todos os consumidores, endpoint no BFF e avaliação real.** `BrainRetriever.query` devolve `citations`, `gaps`, `index_version` e, por fonte, `sha256`, `line_start`, `line_end`, `stale`. A ferramenta MCP `search_knowledge_base` devolve a mesma lista (vazia significa sem evidência); o broker acrescenta os quatro campos aos itens e `gaps` e `index_version` ao resultado. O BFF expõe `POST /v1/retrievals` (detalhes na nota `vault/systems/second-brain-observability-bff.md`) e `/v1/capabilities` passa a informar `semantic_retrieval: true`. `cli.py retrieval-eval [--min-recall 0.8] [--dataset] [--k 5]` mede recall e negativos com Qdrant e Ollama reais, varre a grade `min_score` × `max_drop`, sugere o par e grava relatório em `evals/reports/` (ignorado pelo git). O dataset dourado passa a 13 positivos e 10 negativos; `evals/runner.py` deixa de alegar recall e só pontua gates.

## Consequências
- **O índice existente não devolve nada até ser reconstruído.** Pontos antigos não têm `doc_sha256`, `space_id` nem linhas; o filtro por espaço os exclui. Até rodar `cli.py sync --rebuild --yes` a partir do checkout canônico, a busca responde sem evidência; `cli.py ask` mostra uma dica de reconstrução quando o índice está vazio para o espaço. A primeira reconstrução real é a migração de alias da ADR-033 D1, com uma janela curta de busca indisponível (`--yes` é obrigatório).
- **Os valores do piso são provisórios.** `0.65` / `0.10` / `max_per_doc 2` não foram medidos. Eles só deixam de ser provisórios depois que `cli.py retrieval-eval` rodar com o índice reconstruído e o par sugerido for gravado em `config.py` (a prova com Qdrant e Ollama reais depende de autorização do dono).
- **A obsolescência é calculada na consulta.** Cada consulta calcula o hash dos arquivos citados e compara com o hash indexado; o custo é uma leitura por documento citado, e o resultado reflete o disco naquele instante, não o do último sync.
- **A citação não prova a conclusão.** Ela diz de qual trecho, de qual revisão e de quais linhas veio o texto recuperado; a conferência por afirmação fica para `POST /v1/answers`.
- **O espaço é imposto no repositório de vetores, não no cliente.** O BFF piloto aceita só `space=kiosk`; outro espaço recebe 403. Multiusuário e permissões reais por espaço continuam fora do escopo.
- Falha do embedding ou do Qdrant no endpoint vira 503 tipado, sem texto de exceção na resposta (o detalhe vai ao log local).
- Provas offline: `tests.test_citations`, `tests.test_retrieval_contract`, `tests.test_bff_retrievals`.

---
type: adr
scope: second-brain
status: Proposto
date: 2026-10-28
related: [ADR-034, ADR-033]
---
# ADR-037: Segundo sinal de relevância (prefixos do embedding e termo sem registro no vault)

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
A ADR-034 pôs um piso de relevância na recuperação, mas o `retrieval-eval` de 2026-10-28 mostrou que o score vetorial sozinho não separa as perguntas com resposta das sem resposta. Perguntas sobre integrações plausíveis para a operação, que o vault não documenta, pontuaram 0.736–0.764, dentro da faixa dos positivos (0.745–0.870). Nenhum par `min_score` × `max_drop` da grade recusava todos os negativos sem derrubar o recall. O `nomic-embed-text` também recebia texto cru, sem os prefixos de tarefa com que foi treinado (`search_query: ` e `search_document: `).

Uma sonda na discovery testou quatro sinais. Os prefixos sozinhos não separaram as faixas, mas corrigiram um caso de ordenação. A cobertura lexical também não separou. Um nome próprio da pergunta que não aparece em nenhuma nota do vault, combinado com o piso, separou os 13 positivos dos 16 negativos daquele dataset. Como o sinal foi ajustado nesse mesmo dataset, a onda ampliou o dataset antes de medir de novo.

## Alternativas Consideradas
- **Só subir o piso:** descartada. Com piso 0.75 o recall cai para 67 % e ainda sobra negativo com fonte.
- **Cobertura lexical (fração dos termos da pergunta presentes no trecho):** descartada. As faixas se sobrepõem (positivos 0.25–0.88, negativos 0.00–0.44).
- **Reranker ou juiz LLM:** adiados. Nenhum reranker está instalado, e o juiz (`llama3.2:3b`) acrescenta latência por pergunta que não foi medida.
- **Filtrar a busca pelo esquema de embedding:** descartada. Esconderia um índice misto em vez de exigir a reconstrução.
- **Recusar a busca (HTTP 503 no BFF) com índice de esquema antigo, fixando a coleção por consulta:** descartada. Exigiria resolver o alias e verificar o esquema a cada pergunta. A ordem do runbook fecha a mesma janela sem custo por consulta.
- **Cache do vocabulário por hash do conteúdo a cada pergunta:** descartada. Lê todos os bytes do vault em cada consulta para cobrir só uma edição com mtime restaurado à mão.

## Decisão
1. **D1, recusa com o termo nomeado.** Um nome próprio da pergunta que não aparece no vault zera a seleção de trechos. `gaps` diz `Termo(s) sem registro no vault: X; não há evidência para esta consulta.`, e `answer()` devolve `no_evidence` sem chamar o modelo. Nome próprio é o token com duas ou mais maiúsculas em qualquer posição (siglas, `J&T`), ou com maiúscula inicial fora do início de frase. Tokens com menos de 3 caracteres não contam. O gate só remove trechos; nunca acrescenta. `apply_floor=False` e `entity_gate=False` o desligam.
2. **D2, dataset ampliado antes de medir.** `evals/golden_dataset.yaml` passou a 30 positivos e 30 negativos, 14 deles de domínio vizinho, além de 3 negativos de limite conhecido, todos escritos antes de qualquer medição nova. Cada negativo declara `absent_entities`, e `tests/test_golden_dataset.py` falha se algum desses nomes aparecer em qualquer nota do vault. Uma nota que cite um nome de negativo o torna conhecido e esconde o caso.
3. **D3, esquema de embedding no índice.** `config.py` define os prefixos (`OLLAMA_EMBED_QUERY_PREFIX` e `OLLAMA_EMBED_DOCUMENT_PREFIX`, padrões `search_query: ` e `search_document: `). O esquema são os 12 primeiros hex do SHA-256 de `[modelo, prefixo de pergunta, prefixo de documento]`, e o sync grava `embed_scheme` em cada ponto. `legacy_points_count()` conta os pontos sem `space_id` e também os de outro esquema.
4. **D4, vocabulário calculado no processo.** O vocabulário são os termos de todos os `.md` do vault, sem acento e em minúsculas. Fica em cache por raiz, invalidado quando muda o conjunto (caminho, tamanho, `mtime_ns`). Arquivo ilegível não contribui, e vault vazio desliga o gate em vez de recusar tudo. Nada novo vai para `.runtime/`.
5. **D5, piso só pelo eval.** O `retrieval-eval` imprime a grade sem gate e a grade com gate, e sugere o piso só pela segunda. O relatório grava `gate_rows`, `unknown` por pergunta, `known_limits` (fração sem fonte no par sugerido ou, sem sugestão, no piso atual marcado `provisional`), `embed_scheme` e o SHA-256 do dataset. O piso de `config.py` só muda se o eval sair 0.
6. **D6, quem recusa índice de esquema antigo.** Sync, reconcile e `retrieval-eval` recusam, com `Índice com esquema anterior; rode 'cli.py sync --rebuild --yes'.`. A busca não recusa nem filtra.

## Consequências
- **Runbook (obrigatório depois do merge ou de qualquer mudança de modelo ou prefixo), nesta ordem:** (1) `cli.py sync --rebuild --yes` no checkout canônico, antes de reiniciar o MCP `second-brain` e o BFF; (2) `get_brain_status` com `legacy_points: 0`; (3) reiniciar o MCP e o BFF; (4) `cli.py retrieval-eval`. Até o passo 3, os processos no ar seguem com o código antigo sobre o índice antigo, coerentes entre si. Reiniciar antes do rebuild faria perguntas com prefixo contra documentos sem prefixo, com scores piores e sem aviso.
- **Limites conhecidos:** um nome escrito só em minúsculas não aciona o gate e depende do piso (medido em `known_limits`). Outra grafia de um nome do vault (por exemplo `JT` para `J&T`) é recusada com o termo nomeado. Um termo citado de passagem em qualquer nota conta como conhecido, e então quem decide é o piso. Uma edição de nota com tamanho igual e mtime restaurado à mão não invalida o cache até a próxima mudança.
- **Pergunta sobre um sistema real ainda não documentado** é recusada com o nome dele em `gaps`. Esse é o comportamento desejado, porque o vault não sabe a resposta. Quem pergunta vê o termo e pode reescrever.
- **Generalização:** o dataset ampliado comprova o desempenho neste corpus. Os casos antigos influenciaram o desenho do gate, e a grade escolhe o piso no próprio dataset.
- **Fora desta onda:** busca híbrida (BM25 + vetor), reranker, sinônimos e correção de grafia. Se o recall da grade com gate ficar abaixo de 80 %, a busca híbrida é a próxima discovery.
- Spec: `.superpowers/runs/2026-10-28-segundo-sinal/spec.md`. Evidência da discovery: `.superpowers/runs/2026-10-28-segundo-sinal/evidence.md`.

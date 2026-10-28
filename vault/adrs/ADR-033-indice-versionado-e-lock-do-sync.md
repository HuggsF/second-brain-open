---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-27
related: [ADR-012, ADR-021, ADR-022]
---
# ADR-033: Índice versionado por alias e lock do SO no sync

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
A onda A fechou dois grupos de falhas na ingestão do vault para o Qdrant. O primeiro: ferramentas que leem arquivos a partir de argumentos externos (`get_adr`, `get_system_architecture`, `read_vault_file`) tinham resolução de caminho duplicada entre o MCP (`brain_mcp.py`) e o broker (`core/tools.py`); no broker, `read_vault_file` já verificava que o caminho ficava dentro do vault, mas `get_system_doc` montava o caminho sem essa verificação e `get_adr` usava o argumento direto num padrão de `glob`. O segundo: o sync incremental lia cada arquivo duas vezes (uma para o hash, outra para os chunks), gravava o manifesto sem atomicidade, devolvia `{}` para um manifesto existente e ilegível (o que faria o sync tratar tudo como novo), não tinha exclusão mútua entre processos (CLI e watcher) e não tinha caminho de recuperação quando manifesto e índice divergiam.

Duas decisões de desenho foram necessárias: como trocar o conteúdo do índice sem deixar a busca vazia (D1) e como impedir dois syncs simultâneos (D2). Duas decisões de escopo acompanham: `scripts/sanitize.py` fica fora desta onda (D3) e o resolvedor único vale só para as ferramentas com argumento externo (D4).

## Alternativas Consideradas
- **Coleção única com troca por arquivo também na reconstrução completa:** descartada. Para o sync incremental ela serve (grava os pontos novos e depois apaga os obsoletos), mas numa reconstrução completa deixa a coleção em estado misto por todo o tempo da operação e não há ponto único em que se possa validar o índice novo antes de publicá-lo.
- **Lock por arquivo com PID:** descartada. Um PID gravado em arquivo sobrevive a queda do processo, é reaproveitado pelo SO e exige heurística de "lock velho". O lock do SO (`msvcrt` no Windows, `fcntl` no Linux) é liberado pelo sistema quando o processo morre, sem limpeza manual.

## Decisão
1. **D1 — incremental e reconstrução têm mecanismos diferentes.** O sync incremental faz upsert dos pontos novos e só depois apaga os obsoletos do arquivo (`delete_stale`), de modo que uma nota modificada nunca fica com zero pontos. A reconstrução (`cli.py sync --rebuild`) grava numa coleção versionada `{alias}__{AAAAMMDDHHMMSS}` e troca o alias numa única chamada; o índice antigo só é retirado depois da troca. Cada arquivo é lido uma vez e o hash é calculado sobre esses mesmos bytes.
2. **D2 — lock do SO em `.runtime/sync.lock`** (`core/sync_lock.py`), com `SyncBusy` quando ocupado. O sync roda dentro do lock; o scheduler do watcher faz debounce pela última edição, rearma ao receber `SyncBusy` e espera até 30 s pelo lock (`lock_wait=30`).
3. **D3 — `scripts/sanitize.py` fora de escopo** desta onda.
4. **D4 — resolvedor único só para ferramentas com argumento externo.** `core/vault_docs.py` (`resolve_named`, `resolve_numbered`, `resolve_relative`, `DocError`) é usado pelo MCP e pelo broker. `get_adr` resolve por número exato e lista os candidatos quando há ambiguidade.
5. **Manifesto:** gravação atômica (arquivo temporário, `fsync`, `os.replace`); manifesto ilegível levanta `ManifestError` em vez de virar `{}`; o manifesto é carregado antes de qualquer acesso ao Qdrant.
6. **Reconciliação:** `ensure_collection` decide por `collection_exists`. Roda automaticamente quando a coleção acabou de ser criada, ou quando o manifesto não está vazio e a coleção tem zero pontos. Também sob demanda com `cli.py sync --reconcile`.
7. **Emenda E1:** `get_collections()` não lista aliases; decidir a existência por ela criaria uma coleção real com o mesmo nome do alias, escondendo o índice versionado. Por isso `ensure_collection` usa `collection_exists`, que enxerga aliases.

## Consequências
- **Janela única de indisponibilidade na migração.** A primeira `--rebuild` encontra uma coleção real com o nome do alias e precisa convertê-la em alias: durante essa migração a busca fica indisponível uma vez. Por isso o comando exige confirmação (`MigrationNeedsConfirmation`; `--yes` para prosseguir). Depois da migração, todas as reconstruções trocam o alias numa chamada, sem janela.
- **Manifesto ilegível agora falha de forma explícita.** O sync para com mensagem clara em vez de reindexar tudo em silêncio; o caminho de saída é `cli.py sync --rebuild`, que não depende do manifesto antigo.
- Qualquer falha antes da troca apaga a coleção nova e deixa o alias, a coleção anterior e o manifesto como estavam; depois da troca o manifesto novo é gravado e a coleção anterior é apagada. Durante a reconstrução o vault existe duas vezes no Qdrant: esse é o custo de validar o índice novo antes de publicar.
- O watcher e o CLI deixam de competir: quem chega depois recebe `SyncBusy` (CLI mostra mensagem de lock ocupado; watcher tenta de novo, inclusive no sync inicial).
- **Índice compartilhado entre checkouts.** O lock (`.runtime/sync.lock`) e o manifesto são de cada checkout, mas o índice `(QDRANT_URL, QDRANT_COLLECTION)` é o mesmo para todos os checkouts por padrão. Um `--reconcile` rodado num worktree apaga os pontos de notas que só existem no vault de outro checkout, e um `--rebuild` substitui o índice pelo vault do worktree. Regra: uma coleção por vault; `--reconcile` e `--rebuild` só a partir do checkout canônico; cada worktree que precisar sincronizar define o próprio `QDRANT_COLLECTION`. O lock não muda de lugar: um lock por URL e coleção só serializaria as escritas, e cada checkout continuaria com manifesto e vault próprios.
- O resultado do sync passa a trazer as falhas, e o índice válido nunca é substituído por estado incompleto (critério 9 da nota `vault/systems/second-brain-graphrag-multiagent.md`).
- A prova com Qdrant e Ollama reais (`cli.py sync` completo) é manual e depende de autorização do dono; os testes offline cobrem o restante (`tests.test_vault_docs`, `tests.test_sync_lock`, `tests.test_sync_consistency`).

---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-28
related: [ADR-035, ADR-008, ADR-018]
---
# ADR-036: Correções do orçamento de custo (limite zero, falhas do banco, gasto estimado e alerta)

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
A validação pós-merge da onda C (ADR-035) encontrou lacunas no orçamento e no circuit breaker de custo. `daily_usd: 0` ou `monthly_usd: 0` deixavam o estado em `normal` mesmo com gasto, ou seja, funcionavam como "ilimitado". Uma falha do SQLite em `BudgetTracker.record()` (por exemplo `database is locked`) fazia `run_task` levantar depois de o modelo já ter respondido e cobrado. Uma falha em `status()` também derrubava a tarefa. Uma resposta de nuvem sem `usage` contava 0 tokens e US$ 0, e um provedor `openai_compatible` sem `price` tinha preço 0. O alerta de 80 % exigido pela ADR-008 não chegava a ninguém: `warning` e `critical` só apareciam em consulta. Além disso, `cli.py budget --rebuild` abortava com uma linha de evento sem `ts`, e a ADR-035 citava chaves de perfil e testes que não existem (corrigidos nela mesma, só como fato).

As decisões abaixo cobrem a semântica do limite zero (D1), a tolerância a falha do banco (D2), a contagem do gasto que escapava (D3), o canal do alerta (D4), o rebuild robusto (D5), a razão da virada em UTC (D6) e o que fica adiado (D7). O contrato do envelope não muda: `envelope.schema.json` tem `additionalProperties: false`.

## Alternativas Consideradas
- **Limite 0 significa ilimitado:** descartada. Um limite explícito de US$ 0 é a forma mais direta de proibir gasto pago, e lê-lo como "sem teto" inverte a intenção de quem o escreveu. Quem não quer orçamento retira o bloco `budget` do perfil.
- **Deixar a tarefa cair quando `record()` ou `status()` falha:** descartada. Quando `record()` falha, o modelo já respondeu e a chamada já foi cobrada; descartar a resposta perde o resultado pago sem devolver o dinheiro. Quando `status()` falha, levantar derruba até tarefas que poderiam rodar localmente de graça.
- **Contar 0 quando falta `usage` ou `price`:** descartada. É exatamente o vazamento que o orçamento deveria impedir: chamadas pagas que não somam nada e nunca disparam o estado `exceeded`.
- **Campo de orçamento no envelope `task.result` para levar o alerta:** descartada. O schema do envelope é fechado (`additionalProperties: false`, também em `cost`); um campo novo quebraria a validação de todos os consumidores e misturaria o estado global do orçamento com o resultado de uma tarefa.
- **Abortar o `--rebuild` na primeira linha inválida:** descartada. Um evento truncado ou antigo, sem `ts`, impediria reconstruir todo o resto do histórico.
- **Contar as tentativas cobradas mas rejeitadas localmente (HTTP 200 malformado, timeout depois do envio):** adiada (D7).

## Decisão
1. **D1: limite 0 bloqueia gasto pago.** Em `core/budget.py:370-373`, `_pct` devolve infinito quando o limite é `<= 0`, então o período fica `exceeded` mesmo com US$ 0 gastos. O empate continua com o diário: com os dois limites em 0, `limiting_period` é `daily`; só com `monthly_usd: 0`, é `monthly`. Na mesma correção, `cost_log` ganhou o índice `idx_cost_log_ts` em `ts` (`core/budget.py:134`), criado ao abrir o banco e recriado em `clear()` e depois da troca de tabelas do rebuild.
2. **D2: falha do banco nunca derruba a tarefa.** Em `core/local_tasks/router.py:343-353`, se `status()` levanta qualquer exceção, o guard age como `exceeded` com período `daily` (o mesmo caminho do `FailedBudgetTracker`): perfil misto roda só local, perfil só de nuvem devolve `budget_exceeded` / `budget_daily`. O stderr recebe `[budget] estado do orçamento indisponível ({Tipo}); nuvem bloqueada nesta chamada.`. Em `core/local_tasks/router.py:377-385`, se `record()` levanta, o envelope volta intacto (mesmo `status`, `payload` e `cost`) e o stderr recebe `[budget] falha ao registrar custo: {Tipo}; o custo está em events.jsonl e entra no próximo 'cli.py budget --rebuild'.`. O custo não se perde porque `events.record` já gravou o envelope antes.
3. **D3: preço obrigatório com orçamento e tokens estimados sem `usage`.** `load_profile` recusa um perfil com bloco `budget` em que algum provedor `openai_compatible` tenha `price.input == 0` e `price.output == 0` (`core/local_tasks/profile.py:86-90`, mensagem `profile {name}: providers[{i}].price é obrigatório quando o perfil tem budget`). Sem `budget`, preço 0 continua aceito, e provedores `ollama` nunca precisam de preço. No cliente (`core/local_tasks/openai_compat_client.py:14-30`), um campo de `usage` ausente, não numérico, negativo ou não finito é estimado por `ceil(len(texto) / 4)`, com mínimo 1; a entrada usa `system + user` e a saída usa o texto devolvido. Cada campo é tratado à parte, e um valor válido (inclusive `0` explícito) é usado sem mudança.
4. **D4: alerta no stderr e no evento `budget.alert`, sem campo no envelope.** Depois de um `record()` bem-sucedido, `_budget_alert` (`core/local_tasks/router.py:395-420`) relê `status()` e compara com o estado lido antes da execução (`normal < warning < critical < exceeded`). Se piorou, escreve no stderr `[budget] orçamento {diário|mensal} em {estado}: US$ {gasto:.4f} de US$ {limite:.2f}.` e chama `events.publish` com `{"type": "budget.alert", "state", "period", "spent", "limit", "trace_id"}` (fan-out para os assinantes SSE). Estado igual ou melhor não alerta; sem tracker, sem estado anterior (porque `status()` falhou) ou com falha na releitura também não. Nenhum caminho levanta. O alerta é por processo: dois processos que cruzam o limite juntos podem emitir um alerta cada.
5. **D5: o rebuild pula e conta linhas inválidas.** `_rebuild_budget` (`cli.py:446-521`) pula e conta as linhas com JSON inválido, que não sejam objeto, sem `id`, sem `ts`, com `ts` fora de ISO 8601 ou com `cost` que não seja objeto. Linhas vazias e eventos que não são `task.result` com `cost` não entram na contagem. O relatório passa a ser `Reconstruído: N registros, ignoradas: M, US$ X.XXXX acumulado.`, em que `N` conta `envelope_id` únicos (o primeiro vence, como o `INSERT OR IGNORE`) e o total é a soma real do `actual_usd` reconstruído. Antes, o total vinha de uma atribuição morta.
6. **D6: o dia vira em UTC.** O `cost_log` é um registro único, consultado pela CLI e pelo MCP, e o fuso de quem consulta não pode mudar a qual dia um gasto pertence. Por isso o timestamp do envelope é convertido para UTC ao gravar, e o dia e o mês são contados em UTC (ADR-035 D1). A consequência prática é que o limite diário renova às 21h no horário de Brasília (UTC-3), não à meia-noite local.
7. **D7: adiado.** Ficam fora desta correção as tentativas que o provedor cobra mas que o cliente rejeita localmente, como um HTTP 200 com corpo malformado ou um timeout depois do envio. Hoje elas não chegam ao `cost_log`. Contá-las exige que o cliente devolva o custo junto com o erro, o que muda o contrato entre cliente e router.

## Consequências
- **Um perfil com `daily_usd: 0` que antes rodava sem limite agora bloqueia a nuvem.** É a intenção: um perfil misto passa a rodar só local, e um perfil só de nuvem devolve `budget_exceeded`.
- **Falha do banco tem custo visível, não silencioso.** Com `status()` indisponível a nuvem fica bloqueada naquela chamada; com `record()` falhando o gasto fica fora do `budget.db` até o próximo `cli.py budget --rebuild`, e o stderr diz isso.
- **Perfis com orçamento precisam declarar preço.** O perfil `kiosk` já declara e continua carregando. A estimativa por caracteres é grosseira, mas sempre maior que zero para uma resposta paga.
- **O alerta não é durável.** Ele sai no stderr e no SSE; quem não estiver ouvindo naquele momento só vê o estado ao consultar `cli.py budget` ou `get_budget_status`.
- **Provas offline:** `tests/test_budget.py` (`TestZeroLimit`), `tests/test_local_tasks.py` (`BudgetGuardRobustnessTests`, `BudgetSpendAccountingTests`, `BudgetAlertTests`), `tests/test_openai_compat_client.py` (tokens estimados) e `tests/test_budget_wiring.py` (CLI `budget`, `--history`, `--rebuild`, `_get_tracker`, MCP `get_budget_status`, `local_tasks_status` e uma ferramenta registrando custo).

## Pendências conhecidas
Itens ainda abertos depois desta branch. Podem ser tratados na onda final de correções da branch.
- **Preço negativo ou NaN é aceito.** `_price_value` (`core/local_tasks/providers.py:33-39`) converte para `float` sem conferir sinal nem finitude; um preço negativo reduziria o gasto acumulado.
- **`tests/test_local_tasks_mcp.py` grava no `.runtime` real.** O `setUp` (`tests/test_local_tasks_mcp.py:16-32`) não patcha `settings.base_dir` nem zera o tracker em cache do MCP, então cada execução grava no `.runtime/budget.db` do checkout em que roda.
- **`actual_usd` não numérico derruba o rebuild.** `_rebuild_budget` faz `float(actual_usd or 0.0)` sem tratar o erro (`cli.py:511`), então um evento com `actual_usd` em texto interrompe o `--rebuild`.

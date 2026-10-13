---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-13
related: [ADR-004, ADR-008, ADR-014]
---
# ADR-017: Tier local de tarefas, `escalate` para o chamador e núcleo com perfis

> Esta ADR trata do próprio repositório `second-brain`. Complementa o ADR-008, que define o roteamento por tier mas não tem um tier local, sem alterá-lo.

## Contexto
O ADR-008 manda tarefas simples para modelos baratos, mas todo tier continua sendo um fornecedor pago. Classificar uma nota, extrair os campos de um ADR, resumir um texto curto e validar o frontmatter de um documento são tarefas pequenas que um modelo local (Ollama, `llama3.2:3b`) faz sem custo de tokens, e o Second Brain já roda o Ollama para os embeddings.

Duas direções de produto pesam na decisão. O Second Brain passa a ser um produto autoral e agnóstico, do qual a KIOSK Brands é uma instância; todo código novo precisa nascer sem marca nem sistema da KIOSK. E cada tarefa delegada precisa ser visível em tempo real, num formato que um painel futuro consuma (o ADR-004 faz o mesmo para as chamadas MCP, com o trace).

## Alternativas Consideradas
- **Fila assíncrona com worker:** o agente enfileira e consulta depois. Descartada por ora: acrescenta processo, estado e polling para tarefas que cabem numa chamada. O envelope já comporta o modo assíncrono, e ele entra quando uma tarefa precisar.
- **Caixa de correio em arquivos:** agentes gravam pedidos numa pasta e um runtime grava as respostas. Descartada: sem contrato de entrega, sem erro imediato e com disputa de arquivos no Windows.
- **Chamar a nuvem a partir do núcleo para o que o modelo local não resolve:** descartada. O núcleo teria de guardar chave de API e escolher fornecedor, o que o torna dependente da instância e abre um caminho de custo fora do controle do chamador.
- **Repositório separado para o núcleo:** descartada por ora. O vault, o trace e os servidores MCP já estão aqui; separar agora duplicaria a configuração antes de o núcleo estabilizar.

## Decisão
1. Protocolo `brain.task/1`: envelopes `task.request`, `task.result` e `task.event`, com `status` em `ok`, `invalid`, `escalate` ou `error` e `reason` de um vocabulário fechado (`local_unavailable`, `schema_invalid`, `input_too_large`, `unknown_template`, `unknown_task`, `no_valid_label`, `profile_not_found`, `timeout`). Os schemas ficam em `core/protocol/schemas/`.
2. Quatro tarefas no tier local: `classify`, `extract`, `summarize` e `validate`. O caminho é determinístico, depois local, depois validação do schema, 1 retry e, se falhar, `escalate`. `validate` sem `source` é determinístico e não chama o modelo; com `source`, chama o modelo uma vez para conferir o documento contra a fonte. O documento pode ser Markdown com frontmatter YAML, no padrão de metadados do vault definido no ADR-014, ou um objeto JSON (como o `payload` de `extract`).
3. `escalate` devolve a tarefa ao chamador, que a refaz com o modelo que já usa. O núcleo nunca chama fornecedor pago nem lê chave de API. Uma entrada acima de `max_input_tokens` (estimativa de 4 caracteres por token) vira `escalate: input_too_large` sem chamar o modelo; um `LocalModelError` vira `escalate` com o motivo, e qualquer outra falha do cliente vira `status: error`.
4. O núcleo é agnóstico: `core/protocol/`, `core/local_tasks/`, `core/events.py`, `mcp_servers/local_tasks_mcp.py` e `profiles/example/` não citam a instância (`tests/test_agnostic_core.py`). Vocabulários, limites e preço de referência vêm de `profiles/<nome>/profile.yaml`, escolhido por `BRAIN_PROFILE`; o padrão é `settings.default_profile` em `config.py`, não o núcleo.
5. Cada chamada grava um evento em `.runtime/events.jsonl` (rotação de 5 MB × 3), com custo local e custo pago equivalente. O evento nunca contém o `payload`: só `payload_bytes`, os rótulos `type` e `team` de `classify` e `valid` de `validate`.
6. Superfícies: servidor MCP `local_tasks_mcp.py` (`classify`, `extract`, `summarize`, `validate`, `local_tasks_status`, todas com `task_id` opcional) e `cli.py task ...`, mais `cli.py task-eval` para medir a qualidade fora do gate.
7. As falhas de gravação de eventos aparecem em `local_tasks_status`, e não em `get_brain_status`, que roda em outro processo.
8. Timeout por perfil: o núcleo mantém 30 s; o perfil `kiosk` usa `timeout_seconds: 120` pela latência medida.

## Consequências
- **Latência medida** nesta máquina (CPU, `llama3.2:3b`): cerca de 20 s por chamada com o modelo carregado (17 s a 27 s no `task-eval`) e 44 s a 51 s na primeira chamada, depois de o modelo sair da memória. As chamadas MCP são síncronas e bloqueiam o agente chamador por esse tempo. Compensa quando o custo de tokens pagos ou a janela de contexto do agente pesam mais que 20 s; não compensa em tarefas interativas curtas.
- **Timeout por perfil.** Com o padrão de 30 s do núcleo, a primeira chamada a frio já estoura e vira `escalate: timeout`. Em vez de subir o padrão do núcleo, o perfil `kiosk` fixa 120 s; outra instância, com outra máquina, escolhe o seu valor.
- **Qualidade medida** por `cli.py task-eval` em 2026-10-13, com `llama3.2:3b` e 12 casos de `tests/golden_dataset_local_tasks.json`: acerto geral de 92% (11 de 12). `classify` 2 de 3 (67%), `extract` 3 de 3, `summarize` 3 de 3, `validate` 3 de 3; nenhum `escalate` nas 12 chamadas. Em `extract`, o acerto mede a validade do schema (as chaves exigidas presentes), não se os valores extraídos estão certos. Os eventos do `task-eval` saem com `from: task-eval`, separados do uso pelo CLI. Dataset e prompts não foram ajustados para subir a nota. A amostra é pequena; o limite do comando é 60% de acerto geral.
- **Fraqueza observada:** `classify` foi a única tarefa com erro (1 caso em 3); a saída do `task-eval` não identifica qual caso falhou. O 3B segue sendo a decisão; trocar o modelo fica para depois, medido com o mesmo `task-eval`.
- **Observação separada:** numa das chamadas de `classify` o modelo devolveu para `team` um rótulo fora do vocabulário, que foi descartado e gravado como texto vazio. Não há evidência de que essa seja a chamada que falhou no `task-eval`.
- A economia só existe se os agentes chamarem as ferramentas: as descrições MCP dizem quando usá-las e que `escalate` significa refazer a tarefa.
- Fica fora desta decisão: o painel em tempo real que consome `events.jsonl`, a migração do código antigo para perfis, a fila assíncrona e qualquer chamada a modelo de nuvem.
- `jsonschema>=4.0` passa a ser dependência direta no `requirements.txt`.

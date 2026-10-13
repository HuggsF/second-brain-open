# Protocolo de tarefas e runtime local — design

Data: 2026-10-13 · Escopo: núcleo agnóstico do Second Brain · Status: aguardando revisão

## 1. Intenção

O Second Brain passa a ser um produto autoral e agnóstico, do qual a KIOSK Brands é uma instância
(perfil). Este é o primeiro subprojeto dessa direção. Objetivos acordados:

1. **Agnóstico e autoral:** todo código novo nasce no núcleo, sem marca nem sistema da KIOSK.
2. **Custo de tokens:** tarefas pequenas saem dos modelos pagos e vão para um modelo local (Ollama).
3. **Visibilidade em tempo real:** cada tarefa vira um evento padronizado que um painel pode consumir.

Decisões tomadas no brainstorming:
- Mesmo repositório, com núcleo e perfis.
- Integrações específicas viram plugins do perfil.
- O código novo nasce agnóstico; o antigo migra aos poucos (strangler).
- Abordagem A: envelope versionado e ferramentas síncronas.

Critério de sucesso deste subprojeto:
- Um agente qualquer (Claude Code, Codex, Antigravity) chama `classify`, `extract`, `summarize` ou `validate`
  por MCP ou CLI e recebe um envelope `task.result` válido.
- Cada chamada aparece em `.runtime/events.jsonl` com custo local e custo pago equivalente.
- O gate de agnosticismo e a suíte de testes passam.

## 2. Fora do escopo

- Painel em tempo real que consome `events.jsonl` (subprojeto seguinte).
- Migração para o perfil de `brain_mcp`, dos gateways SRV-API e Hub, do dashboard e de cenários da Arena.
- Fila assíncrona e worker (o envelope já comporta; entra quando uma tarefa precisar).
- Chamadas a modelos de nuvem: o núcleo não guarda chave de API e não chama fornecedor pago.
- Trocar o modelo local padrão (`llama3.2:3b`).

## 3. Componentes

```
core/protocol/                 contrato, sem efeitos colaterais
  envelope.py                  monta e valida task.request / task.result / task.event
  registry.py                  carrega schemas de template por "id@versão"
  schemas/envelope.schema.json
  schemas/templates/<id>@<versão>.schema.json
core/local_tasks/              runtime
  ollama_client.py             /api/chat com `format` = JSON Schema; devolve texto, tokens e ms
  router.py                    determinístico → local → valida → 1 retry → escalate
  tasks.py                     classify, extract, summarize, validate (prompts genéricos)
  profile.py                   carrega profiles/<BRAIN_PROFILE>/profile.yaml
core/events.py                 grava envelopes redigidos em .runtime/events.jsonl, com rotação
mcp_servers/local_tasks_mcp.py ferramentas classify, extract, summarize, validate (task_id opcional)
cli.py task {classify|extract|summarize|validate}   mesmas operações na CLI
cli.py task-eval               avaliação de qualidade do modelo local (fora do gate)
profiles/kiosk/profile.yaml    vocabulários, preços e limites da instância KIOSK
```

### Perfil (`profiles/<nome>/profile.yaml`)

```yaml
name: kiosk
labels:
  type: [adr, system, architecture, product, reference, team, domain, daily, rule, playbook, demand]
  team: [logistics, erp-integrations, crm-salesforce, platform, ecommerce]
local_model: llama3.2:3b        # opcional; padrão do núcleo
timeout_seconds: 30
max_input_tokens: 6000
retries: 1
paid_reference:                 # preço usado para estimar a economia (USD por 1M tokens)
  model: reference-small
  input: 0.15
  output: 0.60
```

`BRAIN_PROFILE` escolhe o perfil (padrão `kiosk`). Um perfil inexistente faz a ferramenta responder `invalid`
com `reason: profile_not_found`, sem chamar o modelo.

### Schemas de template

Os templates de `vault/_templates/` continuam sendo o modelo para humanos. Cada template usado pelas tarefas
ganha um JSON Schema versionado em `core/protocol/schemas/templates/`. Começam `adr@1`, `system@1`,
`playbook@1`, `rule@1`, `demand@1`, `daily@1`, `handoff@1`, `classification@1` e `summary@1`. O
`handoff@1` substitui o Markdown livre de `.superpowers/handoffs/` como formato de máquina.

Um teste garante que as chaves de frontmatter de cada template em `vault/_templates/` estejam no schema
correspondente, para que template e schema não divirjam.

## 4. Envelope

```json
{
  "protocol": "brain.task/1",
  "kind": "task.request | task.result | task.event",
  "id": "uuid4",
  "trace_id": "32 hex (W3C, o mesmo do trace MCP quando houver)",
  "parent_id": "id do envelope de origem ou null",
  "from": "claude-code | codex | antigravity | cli | router | outro",
  "to": "local | caller",
  "task": "classify | extract | summarize | validate",
  "template": "adr@1",
  "payload": {},
  "status": "ok | invalid | escalate | error",
  "reason": "código curto, sem conteúdo do payload",
  "cost": {"model": "llama3.2:3b", "tier": "local", "tokens_in": 0, "tokens_out": 0, "ms": 0, "paid_equivalent_usd": 0.0},
  "ts": "ISO 8601 com fuso"
}
```

- `from` vem do `client_info.name` do MCP (como o `caller` do trace) ou de `cli`.
- `paid_equivalent_usd` = tokens reais × preço de `paid_reference` do perfil.
- `reason` usa um vocabulário fechado: `local_unavailable`, `schema_invalid`, `input_too_large`,
  `unknown_template`, `unknown_task`, `no_valid_label`, `profile_not_found`, `timeout`.

## 5. Fluxo

1. A ferramenta (MCP ou CLI) monta o `task.request` e o grava em `events.jsonl`.
2. **Passo determinístico:** tarefa e template existem, o perfil carrega e a entrada cabe em `max_input_tokens`
   (estimativa de 4 caracteres por token). Se algo falha: `invalid` ou `escalate: input_too_large`, sem modelo.
3. **Modelo local:** prompt genérico da tarefa + rótulos do perfil; `format` do Ollama = schema de saída.
4. **Validação** com `jsonschema`. Se falhar: uma nova tentativa com o erro no prompt. Se falhar de novo:
   `escalate: schema_invalid`.
5. O `task.result` volta ao chamador com `payload` completo. O `events.jsonl` recebe o envelope redigido.

Particularidades por tarefa:

| Tarefa | Entrada | Saída (`payload`) | Modelo |
|---|---|---|---|
| `classify` | texto | `{labels: {type, team, tags[]}, confidence}` (schema `classification@1`) | sim; rótulo fora do vocabulário é descartado e, se não sobrar nenhum, `escalate: no_valid_label` |
| `extract` | texto + template | objeto válido no schema do template | sim |
| `summarize` | texto + tamanho alvo | `{summary, key_points[]}` (schema `summary@1`) | sim; acima do limite faz map-reduce em blocos |
| `validate` | objeto ou Markdown + template | `{valid, missing[], errors[], review[]}` | só para campos de texto livre a conferir contra a fonte (`review`); o resto é schema |

`escalate` significa que quem chamou deve fazer a tarefa. O núcleo nunca repassa a tarefa a um fornecedor pago.

## 6. Eventos e privacidade

- `core/events.py` grava em `.runtime/events.jsonl` (fora do git), com rotação de 5 MB × 3, como o trace MCP.
- O evento leva o envelope **sem `payload`**: só `payload_bytes`, `labels` (em `classify`) e `valid` (em
  `validate`). O conteúdo nunca vai para o log.
- Se a gravação falhar, a tarefa não falha. O erro é contado e exposto em `get_brain_status` e em
  `cli.py status`.

## 7. Erros e limites

| Situação | Resultado |
|---|---|
| Ollama fora do ar, modelo ausente ou timeout (30 s) | `escalate` (`local_unavailable` ou `timeout`) |
| JSON inválido ou fora do schema duas vezes | `escalate: schema_invalid` |
| Entrada acima do limite | `summarize`: map-reduce; demais: `escalate: input_too_large` |
| Tarefa, template ou perfil desconhecidos | `invalid` |
| Falha ao gravar o evento | tarefa segue; contador de erro |

## 8. Testes

TDD para `core/` e `mcp_servers/` (CLAUDE.md §11). Os testes novos entram no comando de prova do CLAUDE.md §3.

1. `tests/test_protocol.py`: envelopes válidos e inválidos; registry por `id@versão`; cada schema contém as
   chaves de frontmatter do template correspondente.
2. `tests/test_local_tasks.py` com cliente Ollama falso: caminho feliz das 4 tarefas, nova tentativa,
   `escalate` em cada `reason`, map-reduce do `summarize`, rótulo fora do vocabulário, perfil inexistente.
3. `tests/test_events.py`: evento sem payload, rotação, falha de gravação não derruba a tarefa.
4. `tests/test_local_tasks_mcp.py`: as 4 ferramentas aceitam `task_id` (o `test_trace_servers.py` também
   passa a cobrir o servidor novo), incluindo o caminho de recusa.
5. Gate de agnosticismo: os módulos novos e `profiles/` de exemplo não citam KIOSK, as marcas ou os sistemas
   da instância (a lista de termos fica no próprio teste).
6. `cli.py task-eval` (fora do gate, exige Ollama): golden dataset pequeno por tarefa em
   `tests/golden_dataset_local_tasks.json`, com taxa de acerto e taxa de `escalate`; sai com 1 abaixo do
   mínimo configurado.

## 9. Documentação e decisões

- **ADR-017** (`scope: second-brain`): tier local de tarefas, `escalate` para o chamador e núcleo com perfis.
  Alternativas descartadas: fila assíncrona, caixa de correio em arquivos, chamar a nuvem a partir do núcleo,
  repositório separado. Complementa o ADR-008, que não tem tier local, sem alterá-lo.
- README: seção "Tarefas locais" com as 4 ferramentas e o `BRAIN_PROFILE`.
- CLAUDE.md: comando de prova com os testes novos; `profiles/` no mapa do repositório; regra de que código
  novo em `core/` não cita a instância.
- `requirements.txt`: declarar `jsonschema>=4.0`, hoje presente só como dependência transitiva.

## 10. Riscos

- **Qualidade do `llama3.2:3b` em `extract`** de templates longos (ADR, PRD) pode ser baixa. O `task-eval`
  mede isso, e o `escalate` limita o dano. Trocar o modelo é decisão posterior.
- **Estimativa de tokens por caracteres** é imprecisa. O limite é conservador, e o custo real vem dos
  contadores do Ollama (`prompt_eval_count`, `eval_count`).
- **Adoção pelos agentes:** as ferramentas só economizam se os agentes as chamarem. A descrição das
  ferramentas MCP precisa dizer quando usá-las, e o skill e o CLAUDE.md devem orientar a delegação.

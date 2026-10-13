# Discovery: Pixel Agents e o painel de agentes em tempo real — 2026-10-13

Pergunta: o que a Pixel Agents faz, como faz, e o que o Second Brain deve adotar para mostrar os agentes
trabalhando em tempo real.

Fontes: README de [pablodelucca/pixel-agents](https://github.com/pablodelucca/pixel-agents) (repositório
canônico; o listing do Marketplace/Open VSX é do publisher `pablodelucca`), o fork
[MichaelMa907/pixel-agents-codex](https://github.com/MichaelMa907/pixel-agents-codex) e o código deste repositório.
Não instalei a extensão nem li o código-fonte dela; o que segue sobre a Pixel Agents vem do README.

## 1. O que é a Pixel Agents

Extensão gratuita do VS Code (MIT) que mostra cada sessão do Claude Code como um personagem em pixel art num
escritório virtual. Também roda fora do VS Code, como servidor e CLI (Node 20+), servindo a mesma interface no
navegador.

| Recurso | Como funciona |
|---|---|
| Um personagem por sessão | Cada terminal com Claude Code ganha um personagem |
| Animação conforme a atividade | O personagem anda até a mesa, digita ao editar e lê ao buscar. A troca vem de máquinas de estado, com pathfinding em Canvas 2D |
| Espera e permissão | Balão de fala quando o agente espera input ou permissão; som opcional ao fim do turno |
| Subagentes e times | Subagentes (Task) e "Agent Teams" aparecem como personagens próprios |
| Editor de escritório | Pisos, paredes, móveis e áreas nomeadas mapeadas a pastas do workspace. O agente senta na área da pasta dele. O layout é salvo em JSON |
| Assets | Seis personagens (pacote Metro City, de JIK-A-4); manifestos de móveis; diretórios externos de assets |

### Como detecta a atividade (o que importa para nós)

1. **Modo hooks (padrão):** um script registrado nos hooks do Claude Code (`~/.claude/settings.json`) recebe
   `SessionStart`, `PreToolUse`, `PermissionRequest` e `Stop`. Ele envia o evento, autenticado, aos servidores
   da Pixel Agents registrados em `~/.pixel-agents/servers/`.
2. **Modo heurístico (fallback):** lê os transcripts JSONL em `~/.claude/projects/`. O modo hooks também os lê
   para obter detalhes que os eventos não trazem.
3. As duas fontes são normalizadas num modelo único, `AgentEvent`. Um `AgentRuntime` mantém o estado, e um
   transporte tipado (contratos AsyncAPI) entrega ao webview React.

Arquitetura: `core/` (contratos, sem efeitos colaterais), `server/` (Fastify, runtime, persistência, provider
Claude, leitura de transcripts, CLI), `adapters/vscode/` (terminais, persistência e ponte com o webview) e
`webview-ui/` (React 19 + Vite + Canvas 2D). Os testes usam Vitest, o runner do Node e Playwright.

### Limites declarados

- Só suporta Claude Code; Codex, Gemini e Cursor estão no roadmap. O fork "codex" não mostra suporte
  implementado: 0 releases, e o próprio README diz que a detecção heurística "often misfires".
- Por padrão mostra só as sessões do workspace atual ("Watch All Sessions" amplia).
- O acesso pelo navegador usa `?token=` na URL, que o próprio README trata como credencial que vaza para o
  histórico e para o log. Escutar em `0.0.0.0` expõe a interface à rede local.
- Roadmap: barras de vida para rate limit e orçamento de tokens, um escritório por projeto, personagens
  orquestradores, quadro de tarefas.

## 2. O que já temos

| Peça | Estado | O que entrega |
|---|---|---|
| Arena do Workflow Studio (`dashboard/agent-arena.js`) | Visual pronto: SVG com agentes, feixes, balões, drawer, inspetor MCP | **Atividade simulada.** São 37 passos roteirizados, com ferramentas fictícias como `generate_prd_feature`. A API só grava em `.runtime/workflow_audit.jsonl` o passo que o próprio front encenou |
| Trace das ferramentas MCP (`core/trace_middleware.py` → `.runtime/trace-log.jsonl`) | Em produção local, 46 eventos | **Atividade real e agnóstica de cliente.** Campos: `ts`, `trace_id`, `span_id`, `parent_span_id`, `server`, `tool`, `status`, `duration_ms`, `caller` (por exemplo `antigravity-client`), `args` já redigidos e `error_type` |
| BFF (`backend/server.py`) | Loopback, sessão por cookie, coletor periódico | Ponto natural para receber e servir eventos; hoje só tem `/v1/*` e `/api/workflow/*` |
| Dados locais de agentes | Existem nesta máquina | `~/.claude/projects/` (transcripts do Claude Code) e `~/.codex/sessions/AAAA/...` (sessões do Codex). Conteúdo não lido neste discovery |

A conclusão central: **o que falta não é o visual, é a fonte de eventos.** A Pixel Agents é útil como
referência justamente porque resolveu a fonte de eventos (hooks + transcripts + modelo normalizado) e tratou o
visual como uma camada substituível.

## 3. Comparação

| Capacidade | Pixel Agents | Second Brain hoje | Second Brain proposto |
|---|---|---|---|
| Atividade real | Sim (hooks + transcripts) | Não (roteiro) | Sim (trace MCP + hooks + transcripts) |
| Agentes suportados | Claude Code | — | Qualquer cliente MCP (já vemos `antigravity-client`), Claude Code e Codex |
| Subagentes | Sim | Não | Sim, via `parent_span_id` e eventos de subagente |
| Espera e permissão | Sim | Não | Sim, via hook `PermissionRequest`/`Notification` |
| Visual | Escritório pixel art, editor de layout | Arena SVG | Arena SVG em modo real (fase 1); escritório opcional (fase 4) |
| Contexto de negócio | Nenhum | Vault, grafo, evidências, Hub | Atividade ligada a notas, regras e hosts |
| Governança | Botão que lança com `--dangerously-skip-permissions` | Regras do CLAUDE.md, gateways somente leitura | Alerta visual para ferramentas que tocam produção |
| Autenticação | Token em query string | Cookie de sessão `HttpOnly` | Sessão para leitura; token em arquivo `.runtime` + header para os hooks |

## 4. Proposta: "Agent Office" no Second Brain

### Modelo de evento (inspirado no `AgentEvent`)

```json
{
  "schema_version": 1,
  "ts": "2026-10-13T09:12:03.120-03:00",
  "source": "mcp-trace | claude-hook | claude-transcript | codex-session",
  "agent_id": "claude:<session_id> | codex:<rollout_id> | mcp:<caller>",
  "client": "claude-code | codex | antigravity | outro",
  "parent_agent_id": null,
  "state": "idle | thinking | reading | writing | running | waiting_input | waiting_permission | done | error",
  "tool": "search_knowledge_base",
  "target": "vault/adrs/ADR-014-....md",
  "trace_id": "32 hex",
  "risk": "none | host-read | host-write"
}
```

Regras: só **campos em lista branca**, nunca prompt, conteúdo de arquivo, saída de comando ou argumentos
livres. Isso segue o padrão de `normalize()` do `hub_observability_mcp`. O campo `target` só leva caminho
relativo ao workspace, ou o nome do arquivo.

### Fontes (adaptadores)

1. **Trace MCP**, sem nada a instalar. É um tail do `.runtime/trace-log.jsonl`, que já tem `caller`, `tool`,
   `status` e a hierarquia. Mapa de estado: `search_*`/`get_*` → `reading`, `record_*` → `writing`,
   `srv_api_run_safe_command` → `running` com `risk: host-read`, `error` → `error`.
2. **Hooks do Claude Code.** Um script registrado em `~/.claude/settings.json` (`SessionStart`, `PreToolUse`,
   `PostToolUse`, `Notification`, `Stop`, `SubagentStop`) faz POST no BFF com um token lido de `.runtime/`, em
   header. Traz espera e permissão em tempo real.
3. **Transcripts e sessões** (`~/.claude/projects/`, `~/.codex/sessions/`), como fallback e para o Codex.
   Leitura incremental com o mesmo filtro de lista branca. O formato do Codex precisa ser verificado antes:
   não li esses arquivos.

### Entrega ao front

- O BFF ganha `/api/agents/events` (POST dos hooks, autenticado) e `/api/agents/stream`
  (Server-Sent Events, com sessão), além de um runtime em memória com o estado atual de cada agente.
- A Arena ganha um **modo real**: os nós deixam de ser os 4 papéis fixos e passam a ser os agentes vistos no
  stream. Feixes, balões, drawer e inspetor já existem e passam a mostrar eventos verdadeiros. O modo roteiro
  continua como demonstração.

### O que podemos fazer melhor que a Pixel Agents

- **Ligar a atividade ao conhecimento:** quando um agente lê `vault/adrs/ADR-014`, acender o nó no grafo e
  mostrar a evidência. A Pixel Agents não sabe o que o arquivo significa; o Second Brain sabe.
- **Governança visível:** destacar em vermelho qualquer chamada a gateway de produção. O CLAUDE.md §2 exige
  autorização humana para escrita; o painel mostraria quando e quem tentou.
- **Multiagente de verdade:** um painel para Claude, Codex e Antigravity ao mesmo tempo, porque o trace MCP é
  agnóstico. É justamente o item que a Pixel Agents ainda não entregou.
- **Rastro reproduzível:** cada personagem leva ao `cli.py trace <trace_id>`.

## 5. Riscos e cuidados

- **Transcripts carregam segredos e conteúdo de cliente.** A lista branca no servidor é obrigatória, e o front
  nunca recebe texto livre.
- **Hooks são configuração persistente** do Claude Code do usuário (`~/.claude/settings.json`). A instalação
  precisa de aprovação explícita e de um comando para remover.
- **Autenticação dos hooks:** usar token em arquivo `.runtime/` enviado em header, nunca `?token=` (o problema
  que a Pixel Agents documenta). Servidor só em `127.0.0.1`.
- **CSP do BFF:** o visual novo não pode usar estilo inline; o gate `hardcoded_values` já trava isso.
- **Assets de pixel art:** o código da Pixel Agents é MIT, mas a licença dos sprites Metro City (JIK-A-4) é
  separada e precisa ser verificada antes de qualquer reuso.
- **Não duplicar trabalho:** não há no repositório nada da tarefa dada ao GPT 6.1 Sol (nenhuma branch, commit
  ou worktree até 2026-10-13 08:40). Vale alinhar as duas frentes no contrato de evento acima antes de alguém
  construir o visual.

## 6. Roadmap sugerido

| Fase | Entrega | Esforço | Depende de |
|---|---|---|---|
| 0 | Decidir: usar a Pixel Agents como está para o Claude Code no VS Code/Antigravity, e/ou construir o painel próprio multiagente | horas | — |
| 1 | Runtime de eventos no BFF a partir do `trace-log.jsonl` + SSE + Arena em modo real | 1–2 dias | — |
| 2 | Hooks do Claude Code (estados de espera e permissão em tempo real), com instalação e remoção explícitas | 1–2 dias | aprovação para alterar `~/.claude/settings.json` |
| 3 | Adaptadores de transcript (Claude) e de sessão (Codex) com lista branca | 2–3 dias | verificar o formato do Codex |
| 4 | Visual "escritório" (Canvas 2D, áreas mapeadas a repositórios: hub-logistico, crm-hggs, second-brain) | 1 semana | licença dos sprites; fases 1–3 |
| 5 | Ligações com o vault e alertas de governança | 2–3 dias | fase 1 |

## 7. Decisões em aberto

1. Construir o painel próprio, adotar a Pixel Agents ou combinar os dois? A Pixel Agents está no Open VSX, e o
   Antigravity é um fork do VS Code, mas a compatibilidade não foi testada.
2. Visual: evoluir a Arena SVG (mais barato, já com gates de UX) ou fazer um escritório em pixel art?
3. Escopo dos dados: só sessões deste repositório, ou todos os repositórios em `C:/KIOSK`?
4. Quem conduz: esta frente ou a do GPT 6.1 Sol, com o contrato de evento da seção 4 como interface comum?

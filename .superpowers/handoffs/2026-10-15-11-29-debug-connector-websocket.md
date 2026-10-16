# Handoff — connector WebSocket do painel de debug (Hub Logístico)

Worktree: C:/KIOSK/hub-logistico-debug-ws · branch feature/debug-tap-websocket (sem push, sem upstream) · base origin/main 1bd36b6 · head fabb343
npm test: 280/280 (Windows, Node 24). Linux/Node 18-20 não verificados.
Spec: docs/superpowers/specs/2026-10-15-debug-tap-websocket-design.md · Plano: docs/superpowers/plans/2026-10-15-debug-tap-websocket.md · Operação: docs/debug-tap/README.md

Pendente para o Hugo antes do merge: push/PR; instalar ws nas duas pastas vivas do app (NÃO usar npm ci nelas) ou mudar o deploy-control.py; rodar o CI no Linux.

---

Cópia do ledger SDD (rulings e achados adiados):

# SDD ledger — plan: docs/superpowers/plans/2026-10-15-debug-tap-websocket.md

Spec: docs/superpowers/specs/2026-10-15-debug-tap-websocket-design.md
Worktree: C:/KIOSK/hub-logistico-debug-ws · branch feature/debug-tap-websocket (sem upstream) · base origin/main 1bd36b6
Commit do spec+plano: e5995a2
Baseline: npm test 116/116 passando (antes de qualquer task)

## Rulings de pré-voo

- Ruling: executar sem esperar a revisão humana do plano — o Hugo pediu para seguir trabalhando enquanto dorme — se errado, o plano/decisões podem exigir retrabalho visível na branch.
- Ruling: escrever no repositório do Hub apesar do "read-only from here" do CLAUDE.md do second-brain — pedido explícito no chat ("dar seguimento ao funcionamento do websocket"); mitigado por worktree isolada, branch feature/, sem push, sem tocar em server.js/engine.js — se errado, basta remover a worktree e a branch.
- Ruling: base em origin/main 1bd36b6 (mais recente, inclui main local e a branch revisada) — se a equipe preferir hml, um rebase resolve (só arquivos novos + package.json).
- Ruling: o zip bootstrapping-repo-claude-md é cópia mais antiga da skill já instalada (~25 linhas de diferença no SKILL.md, + backlog.md e zip interno); não usado — se errado, nada foi perdido, o zip segue em Downloads.
- Ruling: escopo = só o connector (contrato, estado, token, WS, processo) — "apenas o funcionamento do websocket"; tap no server.js, sanitizer, painel, PM2 ficam fora — se errado, as próximas fatias seguem o mesmo backlog.
- Ruling: segunda passada de regex de valor no connector adiada para a fatia do sanitizer (D12) — depende das regras de redação — custo: até lá o connector confia no produtor (que ainda não existe).
- Ruling: Origin obrigatório também para clientes não-navegador (D5) — mais simples e estrito; CLI manda Origin explícito — custo: ferramenta de terceiros sem Origin precisa configurá-lo.

## Varredura de pré-voo

| Par / task | Produz → consome | Achado |
|---|---|---|
| T1 → T2 | LIMITS, validateDatagram, isErrorEvent, toIso | Assinaturas idênticas nos dois blocos Interfaces. OK |
| T1 → T3 | LIMITS.maxSessionS (7200), defaultSessionMin (30) | CLI --ttl máx 120 min = 7200 s. OK |
| T2 → T4 | drainForFrame, discardPending, replaySnapshot, producersSummary, metrics, recordOut, rates, counters, enqueueControl | T4 usa counters.bufferOverflowDropped no auth; existe. OK |
| T3 → T4 | verifyToken(token, secret, {env, now}); signToken nos testes | OK |
| T4 → T5 | createDebugWsServer({state, secret, env, allowedOrigins, port, limits, version, log, now}) | T5 passa limits/version/log. OK |
| T3 → T5 | MIN_SECRET_LENGTH | OK |
| T1..T5 | package.json script test (append), T4 + dependência ws | Sequencial, sem conflito. OK |
| T1 fixture → T2/T4/T5 testes | primeiro válido usado como base de httpEvent | OK |
| T1 interno | fixture "200 nós" = obj+array+198 = 200 (válido); 202 inválido; 5 níveis válido/6 inválido; 8192 passa/8193 oversize | Coerente |
| T2 interno | 70 eventos → seq 6..69, overflow 6; erro + 200 sucessos → 65 no replay; taxas 3/3 e 1/3 | Coerente |
| T3 interno | ttl 120 ok / 121 falha; exp==agora expira | Coerente |
| T4 interno | sem replay → 1º ao vivo é frameSeq 2; 3 autenticadas + 4ª = 4409; ttlS 2 para 4410 | Coerente (ttlS 1 corrigido antes do commit) |
| T5 interno | spawn com cwd temporário evita ler .env | Coerente |
| Rubrica | nenhum teste sem asserção, nenhuma duplicação mandatada pelo plano | Limpo |

## Progresso
Task 1: complete (commits e5995a2..e3bc34d, review clean)
Task 1: minor (deferred): comentário de data em contract.js:88-91 promete "existir no calendário", mas Date.parse aceita 30/02 e T24 — corrigir o comentário
Task 1: minor (deferred): faltam testes de limite exato (route 200/201, path 300/301, host 100/101, contentType, sub 64/65, 30/31 headers, status 100/599/600, query 20 chaves, 201 nós)
Task 1: minor (deferred): ordem "missing → extra → inválido" e type/v ausentes sem teste próprio
Task 1: minor (deferred): teste duplicado de entradas não-Buffer (debug_contract.test.js:53-57 e :62-65)
Task 1: minor (deferred): __proto__ aceito como chave de header/query/body — consumidores não devem copiar com Object.assign (aviso levado à Task 2/4)
Task 1: minor (deferred): isErrorEvent(null) lança — documentar pré-condição
Task 1: minor (deferred): limite de caracteres conta unidades UTF-16 (astral = 2)
Task 2: Ruling: control.config descartado sem cliente deixa o painel que conecta depois sem modo/expiração/sub do tap (Important, plan-mandated) — adicionar state.configSnapshot() (último tap.state por produtor) e mandar no frame 1 [hello, heartbeat, ...config]; spec 3.2 e plano emendados no commit de docs — custo se errado: alguns eventos de config extras no frame do hello
Task 2: minor (deferred): tap.state com seq <= lastSeq ainda sobrescreve o estado e pode emitir config espúrio (moot em loopback)
Task 2: minor (deferred): enqueueControl lança com undefined/circular (callers controlados; Task 4 chama de timers dentro de try/catch)
Task 2: minor (deferred): teste "drainForFrame não pula um evento grande" não testa o título; falta caso grande-depois-pequeno na mesma fila
Task 2: minor (deferred): isErrorEvent usa LIMITS do módulo, não o limits injetado
Task 2: minor (deferred): conta de orçamento duplicada em drainForFrame/replaySnapshot (helper fits)
Task 2: minor (deferred): fixtures por índice, literais 70/6/200 não derivados de LIMITS, fuzz nunca chega a accepted
Task 2: minor (deferred): drain/replay/summary/metrics devolvem referências (Task 4 não pode mutar)
Task 2: fix round 1/5 (1 addressed, 0 open — configSnapshot para quem conecta depois; commits 6f28263..9b11cc3)
Task 2: complete (commits e3bc34d..9b11cc3, review clean)
Task 2: minor (deferred): control.config ainda na fila pode chegar duas vezes (snapshot no frame 1 + próximo frame ao vivo) — painel deve tratar config como idempotente
Task 3: minor (deferred): verifyToken aceita segredo curto (só signToken/CLI checam) — connector valida na config (Task 5)
Task 3: minor (deferred): sem checagem exp > iat (token com exp < iat assinado com o segredo passaria)
Task 3: minor (deferred): signToken com now gigante gera iat não-seguro (verify recusa com bad_claims)
Task 3: minor (deferred): erro de flag desconhecida ecoa o argumento inteiro (inclui --x=valor)
Task 3: fix round 1/5 (1 addressed, 0 open — teste de assinatura não canônica agora determinístico; commits b45d8df..38f7637)
Task 3: complete (commits 9b11cc3..38f7637, review clean)
Task 4: Ruling: brief (auth sem token → 4400) x spec 3.3 ("token ausente" → 4401) — vale o brief: auth sem campo token é mensagem fora do contrato (4400); 4401 = token presente e inválido; spec 3.3 emendado — custo se errado: painel mostra "mensagem inválida" em vez de "não autorizado" nesse caso
Task 4: Ruling: 1011 (falha interna ao atender o cliente) fica no contrato; spec 3.3 emendado — custo se errado: um código a mais para o painel tratar
Task 4: Ruling: heartbeat de 30 ms nos testes de pong (plan-mandated, risco de flake no CI) sobe para 150 ms na fix round 1 — custo: testes ~0,5 s mais lentos
Task 4: minor (deferred): log de acesso registra 1006 quando o ws fecha sozinho (1009/1002/1007); comentário em wsServer.js:200-202 diz o contrário — mapear err.code no listener de error
Task 4: minor (deferred): sockets rejeitados (4403/4409) que não respondem ficam até o closeTimeout padrão de 30 s do ws (não ocupam vaga)
Task 4: minor (deferred): checagens de segredo/env duplicadas de token.js no construtor; sendWelcome repete o formato de frame de prepareFrame
Task 4: fix round 1/5 (2 addressed, 0 open — teste de métricas espera o retrato pós-auth + teste determinístico da corrida; liveness com heartbeat de 150 ms; commits 52539eb..f03b39c)
Task 4: complete (commits 38f7637..f03b39c, review clean)
Task 5: complete (commits f03b39c..9b149b0, review clean)
Task 5: minor (deferred): listen() com porta ocupada também loga debug_ws_internal_error no stdout (handler permanente de error do httpServer em wsServer.js:502)
Task 5: minor (deferred): fiação de sinal real no debug-connector.js sem teste em processo filho (dá para cobrir só no Linux do CI)
Task 5: minor (deferred): ordem WS→UDP do close() não testada; try/finally para não vazar o socket UDP se server.close() rejeitar
Task 5: minor (deferred): debug_udp_internal_error sem limite (inalcançável hoje)
Task 5: minor (deferred): erro de config não nomeia quais origens/portas são inválidas
Task 5: minor (deferred): README sem debug_ws_internal_error/debug_udp_internal_error/debug_connector_fatal; regra do segredo na coluna "Padrão"
Task 5: minor (deferred): testes com regex frouxa /env/ e fixtures por índice

## Revisão final (1bd36b6..9b149b0, opus): With fixes — C-1, I-1, I-2, I-3 + minors
Final: Ruling: C-1 (teste de 2000 datagramas cai no Linux: lotes não cedem o event loop) — esperar o contador alcançar cada lote antes do próximo — custo se errado: teste ~ms mais lento
Final: Ruling: I-2 (connector aceita datagramas do outro ambiente) — createConnectorState recebe env; datagrama com src.env diferente conta em udpForeignSource (sem mudar os 9 totals do contrato); spec 5 e 3.2 ganham a regra — custo se errado: homolog e produção no mesmo connector exigiriam dois processos (já é o recomendado)
Final: Ruling: I-1 (deploy prepare quebra sem ws instalado no servidor) — fora desta fatia mudar scripts/deploy-control.py; documentar "antes do primeiro deploy" no README e levar ao Hugo como ação antes do merge — custo se errado: um deploy bloqueado (falha segura) até o npm ci manual
Final: Ruling: I-3 + minor triado "README sem eventos/coluna do segredo" — README ganha seção produção+homolog no mesmo host (portas/nomes/túnel distintos), --kill-timeout, usuário não-root, lista completa de eventos
Final: Ruling: incluir na mesma onda M-1 (código real no log de close), M-2 (1009/1011 no CLOSE, comentário obsoleto), M-3 (closeTimeout curto; ping antes do auth), M-4 (dotenv só com chaves DEBUG_*), M-5 (pong 500 ms, timeout no spawnSync) e as duas notas de spec 3.2 (config idempotente, __proto__) — baratos e de segurança; M-6 (Host no /healthz) fica — dado de baixo valor
Final: fix wave (commits 9b149b0..fabb343): 9 itens feitos, I-1 BLOCKED — minha ruling estava errada (npm ci --omit=dev no diretório vivo usa o lockfile antigo, não instala ws e apaga o node_modules do app rodando)
Final: Ruling: I-1 não vira instrução no README (procedimento de produção não verificado); vai para o Hugo como decisão antes do merge, com opções (npm install --no-save ws@8.22.0 no diretório vivo, copiar node_modules/ws, ou mudar o deploy-control.py para instalar dependências no staging) e o alerta de não rodar npm ci no diretório vivo — custo se errado: o primeiro deploy após o merge aborta no prepare (falha segura) até alguém instalar o ws
Final: re-review (9b149b0..fabb343, opus): todos os achados ADDRESSED, sem breakage Critical/Important
Final: parked — log pode registrar 1002/1007/1009 quando o socket já tinha caído sem close frame (input pausado no desconexão) — Ruling: fica; raro e informativo; custo: um código otimista no log de acesso
Final: parked — mapeamento 1008 e liberação de vaga no erro do ws sem teste de regressão (probe confirmou) — Ruling: fica para a próxima fatia; custo: regressão silenciosa possível
Final: parked — 1002/1007/1008 podem aparecer em debug_ws_close.code mas não estão na tabela 3.3 nem no README; comentário em wsServer.js:233 omite 1008 — Ruling: fica para a fatia do painel, que vai tratar os códigos; custo: operador vê código não documentado
Final: parked — env.js usa dotenv.config; com DOTENV_KEY definido o dotenv escreve aviso no stdout — Ruling: fica (ninguém usa DOTENV_KEY); custo: stdout do connector/CLI poluído se alguém definir

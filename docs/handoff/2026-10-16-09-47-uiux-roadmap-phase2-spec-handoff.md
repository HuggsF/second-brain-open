# Handoff Autossuficiente — UI/UX Roadmap Phase 2 (Fase 1 → Fase 2)

> **De:** Fase 1 (Discovery 3D) → **Para:** Fase 2 (Spec Gate)  
> **Data:** 16/10/2026 · **Task:** uiux-roadmap-phase2  
> **Branch:** `feature/uiux-roadmap-phase2`  
> **Pré-requisito:** PR #37 mergeada (Phase 1 concluída)

---

## 1. Contexto do Problema

Após a Fase 1 do Roadmap UI/UX (higienização, unificação visual, consolidação de duplicatas), os 3 frontends do Second Brain (Nexus, Dashboard, JEV) continuam operando como silos isolados. Cada um fala diretamente com o backend por canal próprio (WS, REST HTTP) sem coordenação inter-app:

- **Zero postMessage** — nenhum canal bidirecional entre Dashboard e seus iframes (Nexus, JEV)
- **Zero SSE implementado** — `/v1/graph-events` referenciado no código mas não existe no backend
- **Zero visualização de tool calls** — backend produz traces em `.jsonl` mas não os streama
- **Zero execução real de playbooks** — JEV é exclusivamente sistema de auditoria/evidência

---

## 2. O que foi feito nesta Fase

Investigação 3D completa com 5 subagentes de pesquisa cobrindo:

| Agente | Foco | Achados principais |
|--------|------|-------------------|
| Nexus Researcher | WS transport, adapter architecture, state management | Adapter plugável `createAdapter(mode, bindings)` — aceita qualquer transporte |
| Dashboard Researcher | Routing, iframes, graph-events, agent-arena | 3 iframes dinâmicos, SSE fallback chain, zero postMessage |
| JEV Researcher | Playbook execution, API surface, embed support | Apenas auditoria/evidência, zero execução real, tema sync via MutationObserver |
| Backend Researcher | BFF, WS server, orchestrator, broker, tools | Steps determinísticos (sem LLM), pipeline Zero-Trust completo, traces em arquivo |
| ADR Researcher | PD-OVRs, ADRs, handoffs, debts | 6 PD-OVRs vigentes, 23 ADRs, README drift, HITL spoofing pendente |

---

## 3. Evidências Produzidas

- [Evidence 3D](file:///c:/KIOSK/second-brain/docs/superpowers/evidence/2026-10-16-uiux-roadmap-phase2-evidence.md) — Relatório completo com 3 eixos, 6 hipóteses descartadas, blast radius por item

---

## 4. Decisões Tomadas

Nenhuma decisão de produto tomada nesta fase (Discovery é +0/-0). Decisões pendentes para Spec Gate:

| # | Pergunta de Decisão | Opções |
|---|---------------------|--------|
| PD-Q1 | Protocolo do barramento: SSE puro, WS compartilhado, ou BroadcastChannel? | SSE (unidirecional server→client), WS (bidirecional), BC (inter-tab, sem server) |
| PD-Q2 | postMessage: substituir iframes ou complementar com canal de mensageria? | (a) Manter iframes + postMessage bridge; (b) Remover iframes e montar components diretamente |
| PD-Q3 | Tool Call Visualizer: componente no Nexus, no Dashboard, ou em ambos? | Nexus (proximity to agents), Dashboard (central hub), Both (via BUS-02) |
| PD-Q4 | Execução de playbooks: backend runner vs frontend orchestration? | Backend (seguro, auditado), Frontend (visível, interativo) |
| PD-Q5 | Segurança WS: autenticação de sessão é pré-requisito ou paralela? | Pré-requisito (P0 bloqueante) vs Paralela (wave separada) |

---

## 5. Riscos e Dívidas

| Risco | Probabilidade | Impacto | Mitigação |
|-------|:---:|:---:|-----------|
| WS sem autenticação de sessão (NEW-02) | **Alta** | **Alto** — HITL spoofing possível | Implementar validação de `brain_session` cookie no WS handshake |
| SSE endpoint greenfield no backend | Média | Médio | Reutilizar padrão de `graph-events.js` que já tem fallback chain |
| postMessage cross-port (Nexus em :5173) | Média | Médio | `targetOrigin` explícito; em prod, servir tudo same-origin |
| EXEC-01 é feature totalmente nova | Alta | Alto | Fase 2 pode entregar apenas MON-01 + BUS-01; EXEC-01 para Fase 3 |
| Dívida DT-F1 (tema mobile) ainda aberta | Baixa | Baixo | Pode ser resolvida como parte de BUS-02 (teste integrado de iframes) |

---

## 6. Mapa de Arquivos

### Pontos de entrada investigados (leitura pura)

**Nexus:**
- `nexus/src/adapters/ws-transport.js` (128 LOC) — transporte WS plugável
- `nexus/src/adapters/simulation-adapter.js` — adapter transport-agnostic
- `nexus/src/context.jsx` (79 LOC) — hybrid React Context + external store
- `nexus/src/reducer.js` (67 LOC) — state machine com `REMOTE_EVENT`
- `nexus/src/simulation.mjs` (336 LOC) — engine determinístico puro

**Dashboard:**
- `dashboard/app.js` — routing hash-based, 3 iframes dinâmicos, NAV_GROUPS
- `dashboard/graph-events.js` — SSE → WS → simulação fallback chain
- `dashboard/agent-arena.js` — REST HTTP para workflow telemetry/audit
- `dashboard/core.js` — biblioteca funcional pura sem event emitter
- `dashboard/live-adapter.js` — REST polling para observability

**JEV:**
- `jev-app/src/lib/api.js` — cliente HTTP centralizado (8 endpoints)
- `jev-app/src/lib/theme.js` — sync de tema via parent DOM MutationObserver
- `jev-app/src/components/ExecutionDialog.jsx` — registro pós-fato de evidência
- `jev-app/src/components/PlaybooksView.jsx` — preview Liquid, sem execução

**Backend:**
- `backend/server.py` (208 LOC) — BFF com session cookie, background collector
- `backend/ws_server.py` (286 LOC) — WS server, origin check only (sem session)
- `backend/orchestrator.py` — mission runner com MISSION_PATTERNS determinísticos
- `backend/workflow_api.py` — audit log apenas, "executes nothing"
- `core/broker.py` (200 LOC) — Zero-Trust tool execution pipeline
- `core/events.py` — event log + trace append em `.jsonl`

### Nenhum arquivo modificado (saldo +0 / -0)

---

## 7. Estado dos Testes

| Suíte | Pass | Fail | Nota |
|-------|:---:|:---:|------|
| Nexus | 84/84 | 0 | Baseline inalterado |
| Dashboard | 178+/178+ | 0 | Baseline inalterado |
| JEV | 118/118 | 0 | Baseline inalterado |
| Python | — | — | Não executado (Discovery apenas) |

---

## 8. DoD — Checklist da Fase 1 (Discovery)

- [x] Eixo Vertical mapeado: topologia de rede, portas, protocolos, 6 canais documentados
- [x] Eixo Histórico mapeado: 23 ADRs catalogadas, 6 PD-OVRs, drift de README e SSE documentados
- [x] Eixo Horizontal mapeado: blast radius para BUS-01, BUS-02, MON-01/02, EXEC-01
- [x] 6 hipóteses descartadas com provas materiais
- [x] Classificação causal: 4 itens → "(b) regra omissa"
- [x] Priorização proposta com grafo de dependências
- [x] Saldo de código: +0 / -0 (nenhum arquivo de produção alterado)
- [x] Evidências em `docs/superpowers/evidence/`
- [x] Handoff autossuficiente com 10 seções

---

## 9. Queries para Spec Gate

1. **PD-Q1**: SSE é suficiente para BUS-01 ou precisamos de canal bidirecional (WS multiplexado)?
2. **PD-Q2**: Manter iframes com postMessage bridge ou migrar JEV para web component embeddable?
3. **PD-Q3**: Tool Call Visualizer deve ser componente standalone (micro-frontend) ou integrado no Nexus?
4. **PD-Q4**: EXEC-01 entra na Fase 2 ou é melhor deixar para Fase 3 dado o blast radius "MUITO ALTO"?
5. **PD-Q5**: Segurança WS (NEW-02) deve ser pré-requisito bloqueante antes de qualquer item da Fase 2?
6. **PD-Q6**: `graph-events.js` deve migrar para o novo BUS-01 ou manter independente como canal do grafo?
7. **PD-Q7**: O tema orgânico (DT-F1) deve ser testado/corrigido para mobile nesta fase?

---

## 10. Próximo Passo

**Fase 2 (Spec Gate)**: Iniciar em sessão limpa lendo exclusivamente este handoff. Declarar invariantes negativos, resolver as queries de decisão (PD-Q1 a PD-Q7), e gerar especificação formal com critérios de aceite por item. **PARAR e exigir aprovação humana antes de qualquer plano.**

---

*Handoff gerado seguindo o Manifesto Sem Retrabalho v3.0.0 — 10 seções canônicas. Saldo de código: +0 / -0.*

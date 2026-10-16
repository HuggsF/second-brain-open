# Relatório de Evidências 3D — UI/UX Roadmap Second Brain

> **Fase:** 1 — Discovery 3D (Investigação pura, saldo +0/-0)  
> **Data:** 16/10/2026  
> **Agente:** reader (leitura + coleta de evidências)  
> **Escopo:** 3 frontends (Nexus, Dashboard, JEV App)

---

## Eixo Vertical — Ingress Trace

### Pontos de Entrada Físicos

| Frontend | Entry Point | Roteamento | Call Graph Real |
|----------|------------|------------|-----------------|
| **Nexus** | `nexus/index.html` → `main.jsx` | SPA (componente único `Workspace`) | `App.jsx` → `SimulationProvider` (context.jsx) → `Workspace.jsx` → `OfficeFloor/3D` + `ActivityPanel` + `AgentDetail` |
| **Dashboard** | `dashboard/index.html` → `app.js` | Hash router (`location.hash` → 12 páginas) | `app.js:boot()` → `renderPage()` → módulos por visão (`knowledge-view.js`, `graph-scene.js`, `playbooks-ui.js`, etc.) |
| **JEV** | `jev-app/index.html` → `main.jsx` (Vite) | Tab-based (`RulesView`, `PlaybooksView`, `ExecutionsView`, `HealthPanel`) | `App.jsx` → hooks (`useRules`, `usePlaybooks`, `useExecutions`, `useHealth`) → `api.js` → Backend BFF |

### Fluxos de Dados Verificados

1. **Nexus → Backend Python**: `ws-transport.js` conecta a `ws://127.0.0.1:8848`. Protocolo de eventos com schema v1, dedup por geração, ledger otimista. Verificado em `nexus/src/adapters/ws-transport.js:15-60`.
2. **Dashboard → Backend**: `graph-events.js` conecta a SSE `/v1/graph-events` e WS `ws://127.0.0.1:8848`. Verificado em `dashboard/graph-events.js:1-80`.
3. **JEV → Backend BFF**: HTTP REST via `api.js` (`/api/rules`, `/api/playbooks`, `/api/playbooks/executions`, `/v1/observability/assessment`). Verificado em `jev-app/src/lib/api.js`.
4. **Dashboard ↔ Nexus/JEV**: Somente via `<iframe>` estático com URLs hardcoded (`127.0.0.1:5173`). **Sem comunicação bidirecional.** Verificado em `dashboard/app.js:260-265`.

---

## Eixo Histórico — ADR Drift & Código Zumbi

### Código Zumbi Identificado

| Arquivo | LOC | Status | Evidência |
|---------|-----|--------|-----------|
| `nexus/src/game/PhaserGame.jsx` | ~50 | Órfão — nunca montado | `grep -r "PhaserGame" nexus/src/` → 0 importações em componentes ativos |
| `nexus/src/game/OfficeScene.js` | 584 | Órfão — importado apenas pelo PhaserGame | `grep -r "OfficeScene" nexus/src/` → apenas `game/PhaserGame.jsx` |
| `phaser` no package.json | ~1MB | Dependência sem uso | `grep -r "from 'phaser'" nexus/src/` → 0 (apenas em `OfficeScene.js` que é órfão) |
| `zustand` no package.json | ~15KB | Dependência sem uso | `grep -r "from 'zustand'" nexus/src/` → 0. Estado é `useReducer` em `context.jsx` |
| `dashboard/agent-arena.js` | 2.428 | Simulação paralela ao Nexus | Reimplementa missões multiagente em Vanilla JS, diverge das personas Nexus |

### ADR Drift

| Documento | Expectativa | Realidade | Gap |
|-----------|------------|-----------|-----|
| `dashboard/DESIGN.md` | Paleta `#101513` / `#b8f37b`, tipografia system-ui | Nexus usa `#05050a` / `#00f0ff`, tipografia Rajdhani/Share Tech Mono | **Divergência estética completa** entre Dashboard/JEV e Nexus |
| `docs/sdd/SDD-004-nexus-frontend-contract.md` | Contrato de integração Nexus | Nexus opera como app isolada com simulação local ou WS direto | Contrato parcialmente implementado |

---

## Eixo Horizontal — Blast Radius

### Mapa de Consumidores Colaterais

```
Dashboard (iframe host)
├── Nexus (iframe em #page=nexus) → URL hardcoded 127.0.0.1:5173
├── JEV (iframe em #page=jev) → URL hardcoded jev/index.html
├── playbooks-ui.js (duplica PlaybooksView do JEV)
└── agent-arena.js (duplica simulação do Nexus)

Backend Python (ws_server.py)
├── Nexus (ws-transport.js) → ws://127.0.0.1:8848
├── Dashboard (graph-events.js) → ws://127.0.0.1:8848 + SSE
└── JEV → HTTP REST apenas (sem WS/SSE)
```

### Status da Suíte de Testes (Pós PR #36)

| Suíte | Total | Pass | Fail | Cobertura |
|-------|-------|------|------|-----------|
| Nexus (node --test) | 84 | 82 | 2 (pré-existentes) | Lógica + tipografia, zero 3D/WS real |
| Dashboard (node --test) | 178 | 178 | 0 | Completa — modelo, grafo, UX gates, a11y |
| JEV (vitest) | 118 | 118 | 0 | Completa — componentes, hooks, validação |
| Python (pytest) | 609 | 602 | 7 (pré-existentes) | test_nexus_ws.py tem mocks desatualizados |

---

## Tabela de Hipóteses Descartadas

| Hipótese | Evidência Material | Status |
|----------|-------------------|--------|
| "Nexus e Dashboard compartilham state via algum store global" | `grep -r "postMessage\|BroadcastChannel\|SharedWorker" dashboard/ nexus/` → 0 resultados | ❌ Descartada |
| "JEV tem canal WS/SSE para atualização em tempo real" | `grep -r "WebSocket\|EventSource\|SSE" jev-app/src/` → 0 resultados | ❌ Descartada |
| "Phaser é usado condicionalmente via feature flag" | `grep -r "VITE_.*PHASER\|PHASER" nexus/` → 0 | ❌ Descartada |
| "Agent Arena alimenta dados do backend real" | Leitura de `agent-arena.js:1-50` → simulação local com dados hardcoded | ❌ Descartada |

---

## Classificação dos Gaps por Causa Raiz

| Gap | Causa Raiz | Classificação |
|-----|-----------|---------------|
| 3 silos sem barramento unificado | (b) Regra omissa — nunca houve ADR de integração cross-frontend | Arquitetural |
| Personas divergentes (Nexus ≠ Arena) | (c) ADR defasada — Agent Arena foi escrita antes da definição canônica das 5 personas | Drift |
| Phaser/Zustand órfãos | (c) ADR defasada — migração para Three.js/useReducer não removeu dependências antigas | Drift |
| Playbooks duplicados | (b) Regra omissa — JEV e Dashboard evoluíram independentemente | Arquitetural |
| Aprovação HITL binária | (b) Regra omissa — protocolo de aprovação não previa feedback granular | Funcional |
| JEV sem reatividade | (b) Regra omissa — JEV foi projetado como portal de auditoria passiva | Funcional |
| Nexus não responsivo < 900px | (b) Regra omissa — DESIGN.md do Dashboard tem breakpoints, Nexus não os implementou | Visual |

---

*Evidências coletadas com saldo estrito +0/-0 em código de produção.*

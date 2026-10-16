# PR #37 — UI/UX Roadmap Phase 1: Higienização & Alinhamento Visual

## Causa Raiz / Motivação

O Second Brain opera com 3 frontends independentes (Nexus, Dashboard, JEV) que acumularam divergências visuais, código morto e features duplicadas ao longo de ciclos de desenvolvimento paralelo:

- **Nexus** carregava ~1MB de dependências mortas (`phaser` + `zustand`) e um módulo de game inteiro (`src/game/`) sem uso ativo
- **Dashboard** tinha 12 itens de navegação flat sem agrupamento e uma aba "Playbooks" com UI própria que duplicava funcionalidade do JEV
- **Agent Arena** (Dashboard) usava 6 personas genéricas desalinhadas das 5 personas canônicas do Nexus (Maia/Noah/Theo/Lia/Eva)
- **Nexus** não oferecia tema visual compatível com os tokens do DESIGN.md do Dashboard

Esta PR executa a **Fase 1 do Roadmap UI/UX**: higienização de código morto, unificação visual e consolidação de duplicatas.

---

## O que foi alterado

### Limpeza de Código Morto (CLEAN)

| Task | Descrição | Commit |
|------|-----------|--------|
| CLEAN-01/02 | Removidas dependências `phaser` e `zustand` do `package.json` do Nexus (~1MB de bundle eliminado) | `fa79d88` |
| CLEAN-03 | Módulo `nexus/src/game/` arquivado em `nexus/src/_archived_game/` (preservado para referência) | `2f61c5c` |
| CLEAN-04 | Personas genéricas do Agent Arena unificadas com as 5 canônicas (Maia/Noah/Theo/Lia/Eva) | `d3a4ab6` |

### Unificação Visual (VISUAL)

| Task | Descrição | Commit |
|------|-----------|--------|
| VISUAL-01 | Criado `nexus/src/theme-organic.css` (159 LOC) com tokens mapeados do DESIGN.md (`#101513`, `#b8f37b`, `system-ui`) | `db242d4` |
| VISUAL-02 | Alternador de tema cyberpunk↔orgânico no Header do Nexus com persistência em `localStorage` | `f8ffa20` |
| VISUAL-03 | Nomes, roles e cores da Agent Arena alinhados com `nexus/src/simulation.mjs` | `d3a4ab6` |

### Consolidação de Duplicatas (DEDUP)

| Task | Descrição | Commit |
|------|-----------|--------|
| DEDUP-01 | Aba Playbooks do Dashboard agora exibe JEV via `<iframe>` com fallback amigável | `db539a5` |
| DEDUP-02 | Navegação do Dashboard reorganizada de 12 itens flat para 6 categorias com `<details>/<summary>` nativo | `1a45307` |

### Fixes do Review Gate

| Task | Descrição | Commit |
|------|-----------|--------|
| FIX-01 | Adicionados estilos CSS para `.nav-group`/`.nav-sub` e removida tag `<script>` morta de `playbooks-ui.js` | `c7ebd14` |

---

## Evidências e Testes

### Suíte de Testes Completa: 380/380 PASS ✅

| Suíte | Resultado | Comando |
|-------|-----------|---------|
| Nexus | 84/84 PASS | `cd nexus && npm test` |
| Dashboard | 178/178 PASS | `cd dashboard && node --test` |
| JEV | 118/118 PASS | `cd jev-app && npm test` |

### Invariantes Negativos: 5/5 PASS ✅

- **INV-01**: Lógica de negócio dos agentes intocada ✅
- **INV-02**: Zero testes removidos ✅
- **INV-03**: DESIGN.md do Dashboard inalterado ✅
- **INV-04**: APIs do backend Python inalteradas ✅
- **INV-05**: Zero regressão em testes existentes ✅

### Verificações adicionais

- `npm ls phaser` → `(empty)` ✅
- `npm ls zustand` → `(empty)` ✅
- `nexus/src/game/` não existe; `_archived_game/` preservado ✅
- Zero stubs ou mocks falsos inseridos ✅

---

## Decisões e Trade-offs

| # | Decisão | Trade-off |
|---|---------|-----------|
| D1 | Baseline Nexus corrigido para 84/84 (não 82/84) | 2 testes SSR dependem de `VITE_RENDER_MODE=2d`, flag obrigatória do script `test` |
| D2 | DevOps → Theo (role secundário) | Perde granularidade DevOps vs Eng, ganha consistência cross-app |
| D3 | Nav usa `<details>/<summary>` nativo | Estilização limitada, mas keyboard nav e a11y grátis, zero deps |
| D4 | Playbooks via iframe JEV | ~200KB extra no contexto Playbooks, mas UX inline sem sair do Dashboard |

---

## Dívidas Registradas

| # | Dívida | Impacto | Fase alvo |
|---|--------|---------|-----------|
| DT-F1 | Tema orgânico não testado em breakpoints mobile | Baixo (cosmético) | Fase 2 |
| DT-F2 | `ws-transport.js` não auditado para segurança | Médio | Fase 2+ |

---

## Documentação

- **Spec:** [`2026-10-16-uiux-roadmap-spec.md`](docs/superpowers/specs/2026-10-16-uiux-roadmap-spec.md)
- **Plan:** [`2026-10-16-uiux-roadmap-plan.md`](docs/superpowers/plans/2026-10-16-uiux-roadmap-plan.md)
- **Evidence:** [`2026-10-16-uiux-roadmap-evidence.md`](docs/superpowers/evidence/2026-10-16-uiux-roadmap-evidence.md)
- **Decision Ledger:** [`2026-10-16-uiux-roadmap-plan-decisions.md`](docs/superpowers/decisions/2026-10-16-uiux-roadmap-plan-decisions.md)
- **Progress (SDD):** [`.superpowers/sdd/2026-10-16-uiux-roadmap-plan/progress.md`](.superpowers/sdd/2026-10-16-uiux-roadmap-plan/progress.md)

---

*PR gerada pelo Manifesto Sem Retrabalho v3.0.0 — Fase 6 (Finish Gate).*

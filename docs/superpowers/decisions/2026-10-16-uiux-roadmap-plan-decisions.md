# Decision Ledger — UI/UX Roadmap Phase 1 (Higienização)

> **Task:** uiux-roadmap-phase1  
> **Branch:** `feature/uiux-roadmap-phase1` · **PR:** #37  
> **Data:** 16/10/2026  
> **Spec:** [2026-10-16-uiux-roadmap-spec.md](file:///c:/KIOSK/second-brain/docs/superpowers/specs/2026-10-16-uiux-roadmap-spec.md)  
> **Plan:** [2026-10-16-uiux-roadmap-plan.md](file:///c:/KIOSK/second-brain/docs/superpowers/plans/2026-10-16-uiux-roadmap-plan.md)

---

## Decisões Registradas

### D1 — Baseline de Testes Nexus é 84/84

| Campo | Valor |
|-------|-------|
| **Contexto** | A spec original documentava o baseline Nexus como 82/84. Durante a execução, verificou-se que o comando `npm test` canônico (que define `VITE_RENDER_MODE=2d`) produz 84/84 de forma consistente. Os 2 testes que falhavam (SSR render mode) são dependentes dessa variável de ambiente, que é obrigatória no script `test` do `package.json`. |
| **Decisão** | O baseline correto é **84/84**. A spec registrava 82/84 por execução sem a flag obrigatória. |
| **Trade-off** | Nenhum. É uma correção factual do baseline. |
| **Alternativas descartadas** | Manter 82/84 como baseline → incorreto, geraria falsos positivos em CI. |

---

### D2 — DevOps consolidado em Theo (role secundário)

| Campo | Valor |
|-------|-------|
| **Contexto** | A Agent Arena do Dashboard tinha 6 personas genéricas. O Nexus usa 5 personas canônicas: Maia (Estratégia), Noah (Pesquisa), Theo (Engenharia), Lia (Criatividade) e Eva (Ética). Para unificar, a persona "DevOps" precisava ser mapeada. |
| **Decisão** | DevOps foi absorvido como **role secundário de Theo** (Engenharia), consolidando de 6 para 5 personas. |
| **Trade-off** | Perde-se granularidade entre Engenharia e DevOps, mas ganha-se consistência cross-app. |
| **Alternativas descartadas** | (a) Manter 6 personas no Dashboard → quebra unificação; (b) Criar 6ª persona no Nexus → escopo fora da Fase 1. |

---

### D3 — Navegação usa `<details>/<summary>` nativo

| Campo | Valor |
|-------|-------|
| **Contexto** | A reorganização do nav do Dashboard de 12 itens flat para 6 categorias agrupadas exigia um mecanismo de expansão/colapso para sub-menus. |
| **Decisão** | Utilizar elementos HTML nativos `<details>` e `<summary>` sem dependências JavaScript adicionais. |
| **Trade-off** | Estilização mais limitada que um componente custom, mas keyboard navigation (Tab/Enter/Escape) e acessibilidade vêm de graça. Zero dependências adicionadas. |
| **Alternativas descartadas** | (a) Accordion JS custom → mais código, mais testes, mais manutenção; (b) Biblioteca de UI → viola INV-01 (sem novas dependências de lógica). |

---

### D4 — Playbooks exibidos via iframe JEV (não redirect)

| Campo | Valor |
|-------|-------|
| **Contexto** | A aba "Playbooks" do Dashboard mostrava uma UI própria (`playbooks-ui.js`) que duplicava funcionalidade já existente no JEV. A consolidação exigia decidir entre redirect externo ou embed inline. |
| **Decisão** | Embed do JEV via `<iframe>` com fallback amigável ("Abrir JEV em nova aba") caso o iframe falhe. |
| **Trade-off** | Iframe adiciona ~200KB de carga no contexto Playbooks, mas mantém o usuário dentro do Dashboard sem navegação disruptiva. |
| **Alternativas descartadas** | (a) Redirect com `window.location` → sai do Dashboard, UX ruim; (b) Remover playbooks-ui.js completamente → violaria INV-02 (preservar arquivos existentes como referência). |

---

## Dívidas Técnicas Registradas

### Resolvidas nesta execução

| # | Dívida | Resolução | Commit |
|---|--------|-----------|--------|
| DT-R1 | CSS `.nav-group`/`.nav-sub` sem estilo de indentação | Adicionado `padding-left` e estilos em `styles.css` | `c7ebd14` |
| DT-R2 | `<script src="playbooks-ui.js">` morto no `index.html` do Dashboard | Tag removida do HTML | `c7ebd14` |

### Registradas para fases futuras

| # | Dívida | Impacto | Fase alvo |
|---|--------|---------|-----------|
| DT-F1 | Tema orgânico não testado em breakpoints mobile (320px, 480px, 768px, 1024px) | Baixo (cosmético) | Fase 2 |
| DT-F2 | `nexus/src/adapters/ws-transport.js` como ponto de entrada WS não auditado para segurança | Médio (segurança) | Fase 2+ |

---

## Invariantes Verificados (Auditoria Fase 5)

| ID | Invariante | Status |
|----|-----------|--------|
| INV-01 | Proibido alterar lógica de negócio dos agentes | ✅ PASS |
| INV-02 | Proibido remover testes existentes | ✅ PASS |
| INV-03 | Proibido alterar DESIGN.md do Dashboard | ✅ PASS |
| INV-04 | Proibido alterar APIs do backend Python | ✅ PASS |
| INV-05 | Proibido quebrar testes que passam | ✅ PASS |

---

## Resultado Final de Testes

| Suíte | Resultado | Baseline → Final |
|-------|-----------|-----------------|
| Nexus | 84/84 PASS | 84 → 84 (0 regressão) |
| Dashboard | 178/178 PASS | 178 → 178 (0 regressão) |
| JEV | 118/118 PASS | 118 → 118 (0 regressão) |
| **Total** | **380/380 PASS** | **380 → 380** |

---

*Decision Ledger gerado na Fase 6 (Finish Gate) do Manifesto Sem Retrabalho v3.0.0.*

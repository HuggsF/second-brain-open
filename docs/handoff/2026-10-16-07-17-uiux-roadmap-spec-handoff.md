# Handoff Autossuficiente — UI/UX Roadmap Phase 1

> **De:** Fase 1 (Discovery 3D) → **Para:** Fase 2 (Spec Gate)  
> **Data:** 16/10/2026 · **Task:** uiux-roadmap-phase1  
> **Branch:** `feature/uiux-roadmap-phase1`

---

## 1. Contexto do Problema

O ecossistema Second Brain possui 3 frontends (Nexus, Dashboard, JEV) que evoluíram como silos independentes. Há código morto pesando ~1MB no bundle (Phaser, Zustand), personas de IA divergentes entre apps, features duplicadas (Playbooks) e nenhuma integração cross-app além de iframes estáticos.

## 2. O que foi feito nesta Fase

Investigação 3D completa (saldo +0/-0 em código de produção):
- **Eixo Vertical**: Mapeamento de todos os pontos de entrada, roteamento e call graphs dos 3 frontends
- **Eixo Histórico**: Identificação de código zumbi (Phaser, Zustand, Agent Arena), ADR drift (estética Nexus ≠ DESIGN.md)
- **Eixo Horizontal**: Blast radius de cada frontend, consumidores colaterais, status completo de testes

## 3. Evidências Produzidas

- [Evidence 3D](file:///c:/KIOSK/second-brain/docs/superpowers/evidence/2026-10-16-uiux-roadmap-evidence.md) — Relatório completo de investigação
- [Spec](file:///c:/KIOSK/second-brain/docs/superpowers/specs/2026-10-16-uiux-roadmap-spec.md) — Especificação com invariantes negativos e critérios de aceite
- [Roadmap UI/UX](file:///C:/Users/HugoMelo/.gemini/antigravity/brain/37d175a3-1eda-4a0b-bcd0-a8df3c4be10a/roadmap-uiux-second-brain.md) — Documento completo com 30 itens em 3 fases

## 4. Decisões Já Tomadas

| # | Decisão | Justificativa |
|---|---------|---------------|
| D1 | Arquivar Phaser em `_archived_game/` ao invés de deletar | Preserva histórico para referência futura |
| D2 | Tema orgânico como opção, não substituição do cyberpunk | INV-03: DESIGN.md é fonte-de-verdade, mas Nexus tem identidade própria |
| D3 | Agent Arena mantém a estrutura, só renomeia personas | Evita reescrita do módulo de 2.428 LOC nesta fase |
| D4 | Playbooks do Dashboard redireciona para JEV via iframe melhorado | Consolidação sem reescrita — iframe é temporário até Fase 2 (postMessage bridge) |

## 5. Riscos e Dívidas

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Remoção de deps pode quebrar lockfile | Baixa | Médio | Rodar `npm install && npm test` após cada remoção |
| Tema orgânico pode ter conflito com inline styles | Média | Baixo | Usar custom properties com fallback |
| Nav reorganizada pode quebrar deep links existentes | Baixa | Alto | Manter rotas hash atuais, só mudar apresentação visual |

## 6. Mapa de Arquivos Relevantes

### Alvo de Modificação (Allowed Files)
- `nexus/package.json`
- `nexus/src/game/*` → `nexus/src/_archived_game/*`
- `nexus/src/theme-organic.css` (novo)
- `nexus/src/components/Header.jsx`
- `nexus/src/App.jsx`
- `dashboard/agent-arena.js`
- `dashboard/app.js`

### No-Touch Files
- `nexus/src/adapters/ws-transport.js` (transporte WS — Fase 2)
- `nexus/src/context.jsx` (provider/reducer — lógica intocável)
- `nexus/src/simulation.mjs` (simulação — lógica intocável)
- `dashboard/DESIGN.md` (fonte-de-verdade do design)
- `dashboard/core.js` (motor de busca/grafo)
- `jev-app/src/**` (JEV não muda nesta fase)
- Todos os arquivos Python do backend

## 7. Estado dos Testes

| Suíte | Pass | Fail | Nota |
|-------|------|------|------|
| Nexus | 82/84 | 2 pré-existentes (SSR port, progressbar) | INV-05: não pode regredir |
| Dashboard | 178/178 | 0 | Deve permanecer 178/178 |
| JEV | 118/118 | 0 | Intocado nesta fase |
| Python | 602/609 | 7 pré-existentes | Intocado nesta fase |

## 8. Definição de Pronto (DoD)

- [ ] `npm ls phaser` no Nexus → not found
- [ ] `npm ls zustand` no Nexus → not found
- [ ] `nexus/src/game/` não existe; `nexus/src/_archived_game/` existe
- [ ] Tema orgânico funcional com alternador no Header
- [ ] Agent Arena usa Maia/Noah/Theo/Lia/Eva
- [ ] Nav do Dashboard tem ≤ 6 itens de primeiro nível
- [ ] Playbooks do Dashboard mostra experiência JEV
- [ ] Nexus: 82/84 testes (sem regressão)
- [ ] Dashboard: 178/178 testes (sem regressão)
- [ ] JEV: 118/118 testes (intocado)

## 9. Queries Pendentes para Spec Gate

1. **Q1**: O alternador de tema deve afetar o modo 3D (cores das salas, bloom, emissivos) ou apenas o modo 2D?
2. **Q2**: A reorganização da nav do Dashboard deve manter as 12 rotas hash atuais ou pode consolidar algumas?
3. **Q3**: O redirecionamento de Playbooks para JEV deve ser via iframe (mesmo padrão atual) ou embed direto?

## 10. Próximo Passo

**Fase 3 (Plan Gate)**: Converter a spec aprovada em plano determinístico com briefs SDD atômicos para cada tarefa. Aguarda aprovação humana da spec.

---

*Handoff gerado seguindo o Manifesto Sem Retrabalho v3.0.0 — 10 seções canônicas.*

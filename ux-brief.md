---
name: second-brain-dashboard
date: 2026-10-13
status: building
target_user: "Hugo Melo — Tech Lead / Dev Full-Cycle, KIOSK Brands"
primary_task: "Consultar e navegar o conhecimento operacional da holding"
worst_case_error: "Sobrescrever/deletar uma nota do vault sem confirmação"
design_system: "dashboard/DESIGN.md"
---

# UX Brief — Second Brain Dashboard

> Este arquivo persiste entre sessões de agente. Atualize-o a cada decisão de design.
> Agentes: leiam este arquivo ANTES de tocar qualquer UI deste projeto.

---

## 1. Intent Discovery

### Quem usa esta interface?
- **Papel:** Tech Lead / Desenvolvedor Full-Cycle
- **Nível técnico:** Avançado (usa terminal, APIs, SQL)
- **Frequência de uso:** Diária (múltiplas vezes por dia)

### O que precisa fazer? (Tarefa primária)
- Consultar notas do vault por busca semântica
- Visualizar o grafo de relações entre sistemas
- Navegar entre times, ADRs, playbooks e systems
- Auditar integridade do conhecimento (evidence, gaps)

### Qual o pior erro possível?
- **Ação destrutiva:** Sobrescrever nota existente via ingestão; limpar auditoria
- **Mitigação definida:** Confirmação antes de reprocessar; backup automático

### Estado mais comum ao chegar?
- [x] Lista com dados (vault populado com 738 pontos)
- [ ] Primeiro uso improvável (sistema já está em produção)

---

## 2. Decisões de Hierarquia

| Nível | Ação | Justificativa |
|---|---|---|
| Primário | Busca semântica (Ctrl+K) | É a ação mais frequente — encontrar informação |
| Secundário | Navegar por vista do grafo / filtrar | Exploração estruturada |
| Terciário | Configurações / limpar auditoria / tema | Raramente usados |

**Scanning pattern:** F-pattern (listas de notas), livre (grafo)
**Densidade:** Compacto (dashboard admin — muita informação por tela)

---

## 3. Estados Cobertos

| Componente | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| Busca semântica | [x] | [x] | [ ] | [x] | [ ] |
| Grafo SVG | [x] | [ ] | [ ] | [x] | [ ] |
| Leitor Markdown | [x] | [ ] | [ ] | [x] | [ ] |
| Inspector do nó | [ ] | [x] | [ ] | [x] | [ ] |
| Ingestão/reindex | [ ] | — | [ ] | [ ] | [ ] |

> ⚠️ **Gaps identificados:** Error states e partial states praticamente ausentes.
> Issues abertas: UX-01 (navegação por relação), UX-02 (troca de vista).

---

## 4. Visual Character

| Eixo | Decisão | Token/Valor |
|---|---|---|
| Tipografia | Segoe UI, system-ui, sans-serif | `font: 15px/1.6` |
| Cor accent | Verde limão orgânico | `--accent: #b8f37b` |
| Espaçamento | Denso-médio (admin operacional) | Escala 4-48px |
| Acabamento | Bordas suaves, flat, sem sombras pesadas | `border-radius: 8-16px` |

---

## 5. Histórico de Decisões

| Data | Decisão | Justificativa |
|---|---|---|
| 2026-10-13 | Criação do DESIGN.md | Tokens extraídos do style.css existente como primeira documentação formal |
| 2026-10-13 | Criação do skill ux-engine-kiosk | 8 princípios de design para agentes, inspirado em UX Engine + XIAS + ux-pilot |
| 2026-10-13 | ADR-016 aprovada | Adoção formal de padrões de UX e design system |
| 2026-10-13 | Upgrade do skill para v2 | Product Workflow, UX Brief, Gates nomeados, Critique Mode |
| 2026-10-13 | Ação destrutiva passa por `confirmAction` (dialog, foco em Cancelar) | P0: "Limpar Auditoria em Disco" apagava o log com um clique |
| 2026-10-13 | Gates estáticos em `dashboard/tests/ux-gates.test.cjs` | Primeiro passo de automação do UX Auditor (ver `dashboard/analysis/ux-maturity-2026-10-13.md`) |
| 2026-10-13 | `--field-border` (3:1), fonte mínima 11px, reduced-motion cobre animações | Gates `non_text_contrast`, `font_min`, `reduced_motion` |

---

## 6. Findings de Audit

| # | Severidade | Finding | Arquivo | Status |
|---|---|---|---|---|
| UX-01 | P1 | Navegar por relação não reconcilia busca/evidência | `app.js:16-21` | 🟡 Aberto |
| UX-02 | P1 | Trocar vista com zero resultados mantém doc anterior | `app.js:164-167` | 🟡 Aberto |
| A11Y-01 | P2 | Contraste insuficiente em alguns elementos muted | `style.css` | 🟡 Aberto |
| MOB-01 | P1 | Layout quebra em mobile narrow | `style.css` | 🟡 Aberto |
| UX-P0-01 | P0 | Limpar auditoria sem confirmação | `dashboard/agent-arena.js` | ✅ Resolvido (sprint 1) |
| UX-MOB-02 | P1 | Entre ~650 e 900px a navegação horizontal passa por baixo da marca | `style.css` (rail ≤ 900px) | 🟡 Aberto |

---

## 7. Workflow Status

```
[x] Intent Discovery
[x] Brief Locked
[ ] Wireframe/Spec — Dashboard já existe, evolução incremental
[x] Design System Applied — DESIGN.md criado
[x] Code — Dashboard em produção
[ ] UX Audit Passed — Pendente: resolver UX-01, UX-02, A11Y-01, MOB-01
[ ] Shipped — Awaiting audit pass
```

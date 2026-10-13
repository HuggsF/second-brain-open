---
name: second-brain-dashboard
date: 2026-10-13
status: building
target_user: "Hugo Melo — Tech Lead / Dev Full-Cycle, KIOSK Brands"
primary_task: "Consultar e navegar o conhecimento operacional da holding"
worst_case_error: "Apagar o log de auditoria em disco (Limpar Auditoria) por engano"
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
- Consultar notas do vault por busca textual (Ctrl+K e Conhecimento); a busca semântica (RAG) fica na CLI e no MCP
- Visualizar o grafo de relações entre sistemas
- Navegar entre times, ADRs, playbooks e systems
- Auditar integridade do conhecimento (evidence, gaps)

### Qual o pior erro possível?
- **Ação destrutiva:** apagar `.runtime/workflow_audit.jsonl` (Limpar Auditoria) ou o histórico de consultas do navegador.
  O dashboard não escreve no vault; a sobrescrita de notas pela ingestão do Drive foi corrigida no `drive_sync.py` (ADR-015).
- **Mitigação definida:** `confirmAction` (dialog com foco em Cancelar) em toda ação que apaga dado persistido; gate `destructive_confirm`

### Estado mais comum ao chegar?
- [x] Lista com dados (snapshot com 125 fontes do vault em 2026-10-13)
- [ ] Primeiro uso improvável (sistema já está em produção)

---

## 2. Decisões de Hierarquia

| Nível | Ação | Justificativa |
|---|---|---|
| Primário | Busca textual (Ctrl+K) | É a ação mais frequente — encontrar informação |
| Secundário | Navegar por vista do grafo / filtrar | Exploração estruturada |
| Terciário | Configurações / limpar auditoria / tema | Raramente usados |

**Scanning pattern:** F-pattern (listas de notas), livre (grafo)
**Densidade:** Compacto (dashboard admin — muita informação por tela)

---

## 3. Estados Cobertos

| Componente | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| Busca textual | [x] | [x] | [ ] | [x] | [ ] |
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
| 2026-10-13 | Sobreposições são `<dialog>` modais; uma entrada por tela, Visão geral primeiro | Gates `modal_semantics` e `hierarchy` |
| 2026-10-13 | Brief corrigido: busca textual, pior erro real, findings da análise 360 a reverificar | Fatos anteriores não batiam com o código |

---

## 6. Findings de Audit

| # | Severidade | Finding | Arquivo | Status |
|---|---|---|---|---|
| UX-01 | P1 | Navegar por relação não reconcilia busca/evidência; o inspector pode abrir um nó oculto | análise 360, `vault/systems/second-brain-frontend-360.md:64-67` (linhas de um `app.js` anterior; o grafo hoje está em `graph-ui.js`) | 🔍 Reverificar |
| UX-02 | P1 | Trocar de vista com zero resultados mantém o documento anterior | análise 360, `vault/systems/second-brain-frontend-360.md:64-67` | 🔍 Reverificar |
| A11Y-01 | P1 | Selecionar um nó recria o SVG e remove o elemento com foco (teclado perde a posição); hoje só redesenha no modo foco (`graph-ui.js:66`, `:86`) | análise 360, `vault/systems/second-brain-frontend-360.md:64-67` | 🔍 Reverificar |
| MOB-01 | P1 | No celular o mapa do grafo é miniaturizado e seus textos ficam ilegíveis | análise 360, `vault/systems/second-brain-frontend-360.md:64-67` | 🔍 Reverificar |
| UX-P0-01 | P0 | Limpar auditoria sem confirmação | `dashboard/agent-arena.js` | ✅ Resolvido (sprint 1) |
| UX-MOB-02 | P1 | Entre ~650 e 900px a navegação horizontal passa por baixo da marca | `style.css` (rail ≤ 900px) | 🟡 Aberto |
| UX-A11Y-02 | P1 | Inspetor MCP e painel do agente eram divs sem foco nem Esc | `dashboard/agent-arena.js` | ✅ Resolvido (sprint 1) |
| UX-NAV-01 | P1 | Duas entradas de navegação para a mesma Arena; página padrão em 6º | `dashboard/app.js` | ✅ Resolvido (sprint 1) |

> Contraste dos tokens verificado em 2026-10-13: todos os pares de texto ≥ 4,5:1 nos dois temas (gate `contrast`);
> o A11Y-01 original não é de contraste.

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

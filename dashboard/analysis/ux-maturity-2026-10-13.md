# Maturidade de UX do Second Brain — 2026-10-13

Escopo: `.agents/skills/ux-engine-kiosk/SKILL.md` (v2, commit `94ae28c`), `resources/ux-brief-template.md`,
`ux-brief.md`, `dashboard/DESIGN.md` e o dashboard (`style.css`, `agent-arena.css`, `live.css`, `index.html`,
`app.js` e os módulos `agent-arena.js`, `product-ui.js`, `architecture-ui.js`, `teams-ui.js`).

Método: leitura dos arquivos e medições reproduzíveis: contraste WCAG dos pares de tokens, contagem de
valores fixos fora de `:root`, `font-size`, `border-radius`, `min-height`, `confirm`, `prefers-reduced-motion`,
atributos ARIA. Os números de XIAS e ux-pilot vêm do briefing; **não abri esses repositórios**, então a
comparação é com o que o briefing descreve deles.

## 1. Avaliação do que foi feito

### Radar de maturidade (0–5)

```
Eixo               Skill/Doc  Dashboard  Barra (média)
Intent Discovery      4          2       ███░░  3.0
Hierarchy             3          2       ██▌░░  2.5
States                3          2       ██▌░░  2.5
Forms                 3          3       ███░░  3.0
Affordance            3          1       ██░░░  2.0
Audit                 2          0       █░░░░  1.0
Design System         3          2       ██▌░░  2.5
Visual Character      4          3       ███▌░  3.5
                                          ─────
                                          média 2.5
```

"Skill/Doc" mede o quanto o skill, o brief e o DESIGN.md especificam. "Dashboard" mede o quanto o código
atual cumpre essa especificação.

| Eixo | Nota | Por quê |
|---|---|---|
| Intent Discovery | 4 / 2 | As 4 perguntas e o brief persistente são bons. O brief tem fatos errados: diz "busca semântica (Ctrl+K)", mas a busca do dashboard é textual (`index.html:51`, "Texto completo"). Cita "738 pontos" (só o último sync indexou 1.106 blocos). Dá como pior erro "sobrescrever nota do vault", mas o dashboard não escreve no vault; a única ação destrutiva real é "Limpar Auditoria em Disco". |
| Hierarchy | 3 / 2 | A regra está clara (1 primário por viewport). Na navegação há 10 itens. "Workflows de IA" e "Agentes em Ação" renderizam a mesma tela (`app.js:233`). A página padrão, "Visão geral", é o 6º item (`app.js:7`). |
| States | 3 / 2 | O skill exige 5 estados. O núcleo (biblioteca, busca, grafo) tem empty e error com ação (`app.js:190`, `:209-212`, `:223`). Não há skeleton em lugar nenhum. O próprio brief marca error e partial como ausentes. |
| Forms | 3 / 3 | As entradas têm label (visível ou `sr-only`). O conflito interno: o skill exige 44 px, o DESIGN.md define botão com 42 px e uma media query desce a 36 px (`style.css:9`). |
| Affordance | 3 / 1 | O toast com `role=status` existe (`index.html:47`, `app.js:43`). Nenhum `confirm` em todo o dashboard. A ação destrutiva da Arena roda direto (P0, abaixo). |
| Audit | 2 / 0 | São 12 gates, mas só como checklist em texto: nenhum script e nenhum relatório. Não há nada que rode os gates. |
| Design System | 3 / 2 | O DESIGN.md é completo e os tokens de cor passam no AA. Mas ele documenta tokens que não existem: `--r-xs`…`--r-full` não estão em nenhum CSS. Há 11 raios e 27 espaçamentos distintos em uso. E cerca de 250 estilos inline nos módulos novos ignoram o sistema. |
| Visual Character | 4 / 3 | As decisões por eixo estão explícitas e coerentes no núcleo. A Arena diverge: emojis como ícones, animações em loop e cores do tema escuro fixas em `rgba()`. |

### Comparação com os benchmarks (conforme o briefing)

| Capacidade | ux-engine-kiosk v2 | XIAS | ux-pilot |
|---|---|---|---|
| Regras/gates | 12 gates em texto | 50 gates automatizados | 376 regras |
| Execução dos gates | manual | automática | relatório HTML |
| Brief persistente | sim (`ux-brief.md`) | — | sim (`ux-brief.md`) |
| Crítica | checklist no próprio agente | sub-agente `/critique` | — |
| Evidência visual | nenhuma | — | screenshots multi-breakpoint |
| Design systems | 1 (este dashboard) | 138 | — |
| Componentes catalogados | 6 tipos no DESIGN.md | 52 | — |

O v2 já alcança o ux-pilot no **brief persistente** e o XIAS na **nomeação de gates**. A distância está
inteira na **execução**: nada roda sozinho, nada gera evidência.

## 2. Gap analysis

**O que falta para equiparar:**
1. Gates executáveis: script que roda e falha.
2. Relatório de auditoria com evidência (screenshots em 375/768/1150/1500 px).
3. Crítica isolada do autor: o mesmo agente que gera também critica.
4. Tokens como fonte única: o DESIGN.md e o CSS divergem hoje.
5. Catálogo de componentes com estados (hoje só há classes soltas).

**Quick-wins (alto impacto, baixo esforço):**
- Confirmação em "Limpar Auditoria em Disco" (uma função).
- `prefers-reduced-motion` também para `animation` (uma regra CSS).
- Corrigir o brief (3 fatos errados, findings com referências antigas).
- Alinhar DESIGN.md ↔ CSS: criar os tokens de raio no `:root` ou tirá-los do doc; decidir 42 ou 44 px.
- `font-size` mínimo de 11 px nas 15 ocorrências abaixo disso.
- Gates estáticos em `node --test` (contraste de tokens, hex fora de `:root`, fonte < 11 px, `outline:none`, animação sem reduced-motion). Cabem no gate atual do CLAUDE.md.

**Moon-shots (alto impacto, alto esforço):**
- Migrar os cerca de 250 estilos inline dos módulos novos para classes com tokens. Isso também libera a CSP do `serve.py` de `'unsafe-inline'`.
- Tema claro funcional na Arena (hoje usa cores do tema escuro fixas).
- Auditoria em navegador com screenshots por breakpoint e relatório HTML em `dashboard/analysis/`.
- Tokens em JSON como fonte única, gerando o `:root` do CSS e a tabela do DESIGN.md.
- Skill agnóstico: separar o método (genérico) dos tokens do Second Brain (projeto). Isso se alinha com o modelo agnóstico de templates e workflows que vocês planejam.

## 3. Auditoria do dashboard (os 8 skills aplicados)

| # | Sev. | Gate | Achado | Onde |
|---|---|---|---|---|
| 1 | P0 | `destructive_confirm` | "Limpar Auditoria em Disco" apaga `.runtime/workflow_audit.jsonl` com um clique, sem confirmação nem desfazer. É também o "pior erro" real do produto. | `dashboard/agent-arena.js:1802` |
| 2 | P1 | `reduced_motion` (novo) | `prefers-reduced-motion` desliga só `transition`; as animações infinitas da Arena (`pulse-ring`, `beam-flow`) continuam (WCAG 2.2.2/2.3.3). | `style.css:16`; `agent-arena.css:162`, `:208` |
| 3 | P1 | `modal_semantics` (novo) | O inspetor MCP é uma `div` comum: sem `role=dialog`, sem foco inicial, sem Esc (o Esc global só fecha `<dialog open>`, `app.js:248`). O teclado fica preso atrás do modal. | `agent-arena.js:2050` |
| 4 | P1 | `hierarchy_inverted` | Dois itens de navegação para a mesma tela; a página padrão aparece em 6º lugar. | `app.js:7`, `:233` |
| 5 | P1 | `target_size` | Botões com 36 px em uma media query; checkbox com 18 px (`.check-label input`). O DESIGN.md diz 42, o skill diz 44. | `style.css:9`, `style.css:8` (`.check-label input`) |
| 6 | P1 | `non_text_contrast` (novo) | Borda de campo `--border` sobre `--panel` com 1,53:1 (escuro) e 1,57:1 (claro); a WCAG 1.4.11 pede 3:1 para o contorno de um campo. | `style.css:2-3` (`:root`) |
| 7 | P1 | `theme_hardcoded` (novo) | A Arena fixa as cores do tema escuro: `rgba(24,32,27,.94)` (o `--panel` escuro) e `rgba(184,243,123,…)` (o `--accent` escuro). Não há regra `data-theme=light` em `agent-arena.css`. | `agent-arena.css:224`, `:62-69`, `:157`, `:347` |
| 8 | P1 | `state_missing` | Nenhum skeleton; a página inicial mostra só o texto "Carregando conhecimento…". O brief marca error e partial ausentes no grafo, no leitor e no inspector. | `index.html:44`; `ux-brief.md` §3 |
| 9 | P2 | `font_min` (novo) | 15 ocorrências abaixo de 11 px (mínimo do DESIGN.md): 8 em `style.css`, 4 em `live.css`, 3 em `agent-arena.css`; a menor é 8 px. | `style.css:6-7`, `:14-15`; `live.css:5`; `agent-arena.css:372`, `:578`, `:825` |
| 10 | P2 | `hardcoded_values` | Cerca de 250 estilos inline nos módulos (Arena 85, Produto 85, Arquitetura 65, Times 18), 31 `rgba()` e 8 hex fora de `:root` na Arena. | `agent-arena.js`, `product-ui.js`, `architecture-ui.js`, `teams-ui.js`, `agent-arena.css` |
| 11 | P2 | `spacing_inconsistent` | 27 valores distintos de espaçamento e 11 de raio; o DESIGN.md lista 15 "níveis" de espaçamento, o que já não é uma escala. | `style.css` |
| 12 | P2 | `doc_drift` (novo) | DESIGN.md documenta `--r-xs`…`--r-full` como CSS, mas eles não existem; diz que o skip link aponta para `#content`, e ele aponta para `#main`. | `DESIGN.md:144-151`, `:278`; `index.html:32` |
| 13 | P2 | copy desatualizado | A ajuda e a Visão geral dizem que a execução "exige backend, ainda não conectado"; a API de workflow já existe no BFF e no `serve.py`. | `index.html:53`; `app.js:175` |
| 14 | P2 | `focus_visible` | `.graph-surface .node:focus{outline:none}`. Confirmar que o nó tem outro indicador de foco; senão o foco de teclado some no grafo. | `style.css:9` |
| 15 | P3 | `emoji_as_icon` | Ícones da navegação, botões e cenários da Arena são emojis ou glifos (`🔀`, `⚡`, `◐`, `⌕`); a renderização varia por SO. | `app.js:7`; `index.html:42`; `agent-arena.js` |
| 16 | — | brief incorreto | Findings do brief apontam para linhas de um `app.js` antigo (o código do grafo está hoje em `graph-ui.js`), e o A11Y-01 foi reescrito como "contraste em muted". O original é "seleção recria o SVG e perde o foco". Os tokens `--muted` passam no AA (≥ 6,0:1). | `ux-brief.md` §6 vs `vault/systems/second-brain-frontend-360.md:64-67` |

Sobre os achados herdados da análise 360 (UX-01, UX-02, A11Y-01, MOB-01): o código do grafo mudou de arquivo
e a seleção só redesenha o SVG no modo foco (`graph-ui.js:66`, `:86`). Pela leitura do código, não dá para
afirmar que estão abertos ou resolvidos; precisam ser reverificados no navegador antes de entrar no roadmap.

## 4. Roadmap

**Sprint 1 — esta semana (quick-wins)**
1. P0: confirmação (com `<dialog>`) em "Limpar Auditoria em Disco".
2. Reduced-motion cobrindo `animation`; inspetor MCP como `<dialog>` com foco e Esc.
3. Corrigir `ux-brief.md`: busca textual, pior erro real, contagem atual, findings com referência e significado corretos.
4. Alinhar o DESIGN.md com o CSS (tokens de raio, 42 ou 44 px, skip link) e subir `--border` para ≥ 3:1 nos campos.
5. Unificar "Workflows de IA" e "Agentes em Ação" e pôr "Visão geral" no topo.
6. Primeiro teste `dashboard/tests/ux-gates.test.cjs` com os gates estáticos (seção 5).

**Sprint 2 — próximas 2 semanas (skill v3 com product workflows)**
1. Workflow proporcional ao tamanho da mudança (ver diff abaixo).
2. Skill dividido: `SKILL.md` curto com o método, mais `resources/gates.md`, `resources/states.md` e `resources/critique.md`.
3. Crítica num sub-agente separado, que recebe só a tela e o brief, não o raciocínio do autor.
4. Migração dos estilos inline módulo a módulo, começando pela Arena, junto com o tema claro dela.
5. Novo template do brief (seção 5).

**Sprint 3 — mês seguinte (gates automatizados e relatório)**
1. Gates de runtime no navegador: alvo de toque, labels, foco, overflow em 375 px.
2. Screenshots em 375/768/1150/1500 px nos dois temas, e relatório HTML em `dashboard/analysis/`.
3. Gates no comando de prova do CLAUDE.md §3.

**Backlog**
- Tokens em JSON como fonte única (gera `:root` e o DESIGN.md).
- Catálogo de componentes com os 5 estados de cada um.
- Skill agnóstico, com um DESIGN.md por interface (Análise 360, CRM).
- Design-as-code via MCP (open-pencil) e regressão visual.

## 5. Evolução do skill

### Diff proposto para `SKILL.md`

```diff
@@ Product Workflow (Fluxo Obrigatório) @@
-Toda feature de UI DEVE seguir estas 8 etapas em ordem:
+Escolha o nível pelo tamanho da mudança e siga as etapas desse nível:
+
+| Nível | Exemplo | Etapas |
+|---|---|---|
+| Ajuste | cor, texto, espaçamento | 4 Design System → 5 Code → 6 Gates estáticos |
+| Componente | botão, card, modal | 1 Intent (no brief) → 4 → 5 → 6 → 7 Critique |
+| Tela/feature | nova página, fluxo | todas as 8 |
@@
-### Regra de ouro
-> **Não pule etapas.** Se pedido for "faz um botão", o workflow inteiro ainda
-> se aplica — só que cada etapa leva 30 segundos em vez de 30 minutos.
+### Regra de ouro
+> Nenhuma etapa do nível escolhido é pulada, e o nível é registrado no brief.
@@ 6. UX Auditor @@
-| Sev. | Gate | Critério |
-|---|---|---|
+| Sev. | Gate | Critério | Como verificar |
+|---|---|---|---|
+| 🔴 P0 | `destructive_confirm` | Ação destrutiva sem confirmação | estático: label destrutivo sem `<dialog>`/confirm |
+| 🟡 P1 | `reduced_motion` | `animation` sem `prefers-reduced-motion` | estático (CSS) |
+| 🟡 P1 | `modal_semantics` | Sobreposição que não é `<dialog>` ou não trata foco/Esc | estático + runtime |
+| 🟡 P1 | `non_text_contrast` | Contorno de campo ou ícone < 3:1 | estático (tokens) |
+| 🟡 P1 | `theme_hardcoded` | Cor de um tema fixa fora de `:root` | estático |
+| 🟢 P2 | `font_min` | `font-size` < 11px | estático |
+| 🟢 P2 | `doc_drift` | Token citado no DESIGN.md que não existe no CSS | estático |
@@
-| 🟡 P1 | `target_size` | Elemento clicável < 44px |
+| 🟡 P1 | `target_size` | Alvo < 24px (WCAG 2.5.8, P1) ou < 44px em toque primário (P2) | runtime |
@@ 7. Design System @@
-**Regra: NUNCA invente valores — use os tokens do DESIGN.md.**
+**Regra: use os tokens do DESIGN.md.** Estilo vai em classe CSS, nunca em `style=` inline:
+o BFF serve o dashboard com CSP `style-src 'self'`.
@@ Tokens do Dashboard Second Brain (Referência Rápida) @@
-```css
-/* Dark */
-...
-```
-> Para referência completa: [`dashboard/DESIGN.md`](file:///c:/KIOSK/second-brain/dashboard/DESIGN.md)
+Tokens e escalas ficam só no `DESIGN.md` do projeto (aqui: `dashboard/DESIGN.md`).
+Este skill não repete valores, para não divergir e para valer em qualquer projeto.
@@ Checklist de Validação Final @@
-- [ ] **Workflow:** Todas as 8 etapas seguidas
+- [ ] **Workflow:** nível registrado no brief e etapas do nível seguidas
+- [ ] **Gates:** `node --test dashboard/tests/ux-gates.test.cjs` verde (anexar saída)
+- [ ] **Evidência:** screenshots 375/768/1150/1500 nos dois temas (tela/feature)
```

### Template de `ux-brief.md`

A proposta acrescenta ao template atual: restrições técnicas, nível da mudança, estados com `N/A`, resultado
dos gates e evidências. Também separa os fatos verificados das suposições.

```markdown
---
name: {{projeto}}
date: {{AAAA-MM-DD}}
status: discovery | briefed | building | auditing | shipped
design_system: {{caminho do DESIGN.md | none}}
---
# UX Brief — {{projeto}}

## 1. Intent
- Quem usa (papel, nível técnico, frequência):
- Tarefa primária:
- Pior erro possível **nesta interface** (ação que ela realmente executa):
- Estado mais comum ao chegar:
- Suposições não confirmadas (marcar quando o usuário confirmar):

## 2. Restrições técnicas
- Servidores/CSP: {{ex.: BFF com style-src 'self' → sem estilo inline}}
- Offline / sem fontes externas / navegadores-alvo:
- Breakpoints obrigatórios: 375 · 768 · 1150 · 1500

## 3. Hierarquia
| Nível | Ação | Por quê |
|---|---|---|

## 4. Estados por componente
| Componente | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| {{nome}} | ok / falta / N/A | | | | |

## 5. Gates
| Data | Gate | Resultado | Comando ou evidência |
|---|---|---|---|

## 6. Findings
| # | Sev. | Achado | Arquivo:linha | Status | Verificado em |
|---|---|---|---|---|---|

## 7. Decisões
| Data | Nível (ajuste/componente/tela) | Decisão | Alternativa descartada |
|---|---|---|---|
```

### Gates a portar primeiro

Estes são os que cabem em `node --test`, sem navegador, e cobrem os achados P0 e P1 acima. Ao portar do
XIAS, mapeie cada um para o gate equivalente de lá. Não verifiquei os nomes que o XIAS usa.

1. `destructive_confirm`: botões com rótulo destrutivo (limpar, apagar, excluir, resetar dados persistidos) devem passar por `<dialog>`.
2. `reduced_motion`: toda `animation` precisa estar dentro de, ou ser anulada por, `prefers-reduced-motion`.
3. `contrast` e `non_text_contrast`: pares de tokens dos dois temas (o cálculo usado neste relatório).
4. `theme_hardcoded` e `hardcoded_values`: hex e `rgba()` fora de `:root`; contagem de `style:` inline que só pode cair.
5. `font_min`: nenhum `font-size` < 11px.
6. `doc_drift`: todo `--token` citado no DESIGN.md existe no CSS.

Depois, no navegador: `target_size`, `label_missing`, `modal_semantics` (foco e Esc) e overflow em 375 px.

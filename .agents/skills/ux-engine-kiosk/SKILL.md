---
name: ux-engine-kiosk
description: >-
  Skill de UX/Design para interfaces KIOSK Brands. Ative sempre que
  o agente precisar criar, auditar ou refatorar uma interface de usuário
  (HTML, CSS, JS). Aplica raciocínio de design sênior: intent discovery,
  hierarquia de informação, state completeness, form UX, feedback/affordance,
  auditoria visual, design system e visual character.
---

# UX Engine KIOSK — Design Reasoning para Agentes

> Inspirado no UX Engine by designmotionhq. Adaptado para o stack e os
> padrões da KIOSK Brands (Antigravity, vanilla JS, Second Brain dashboard).

---

## Quando usar

- Sempre que criar ou alterar UI (HTML, CSS, JS)
- Antes de entregar qualquer componente visual
- Quando auditoria de UX for solicitada
- Para criar ou atualizar DESIGN.md

---

## Os 8 Skills de Design

### 1. Intent Discovery (Obrigatório antes de codar UI)

Antes de escrever qualquer markup, responda:

1. **Quem** usa esta tela no dia-a-dia? (papel, nível técnico, frequência)
2. **O que** esta pessoa precisa **fazer** aqui? (tarefa primária)
3. **Qual o pior erro** que pode cometer nesta tela? (ação destrutiva)
4. **Qual o estado mais comum** ao chegar? (vazio? lista longa? erro?)

> Se o usuário não responder, faça suposições razoáveis e documente-as.

### 2. Information Hierarchy

Classifique cada ação/elemento na tela:

| Nível | Exemplo | Tratamento visual |
|---|---|---|
| **Primário** | Buscar, Criar pedido | Botão `primary`, posição dominante |
| **Secundário** | Filtrar, Exportar | Botão com borda, menor destaque |
| **Terciário** | Deletar, Configurações | Overflow menu ou link discreto |

Regras:
- Máximo **1 ação primária** por viewport
- Scanning pattern: F-pattern para listas, Z-pattern para landing
- Densidade: admin denso pode ter mais info; público precisa de respiro

### 3. State Completeness

Todo componente DEVE ter implementado:

```
[ ] Loading (skeleton ou spinner contextual)
[ ] Empty (ilustração + CTA claro)
[ ] Error (mensagem humana + retry)
[ ] Success (confirmação + próximo passo)
[ ] Partial (dados incompletos, indicador visual)
```

- NÃO use `alert()` para erros
- Loading deve preservar layout (skeleton > spinner)
- Empty state deve ter ação: "Nenhum pedido encontrado. [Criar pedido]"

### 4. Form UX

- **Labels**: Sempre acima do campo, nunca placeholder-only
- **Agrupamento**: Campos relacionados em fieldsets visuais
- **Validação**: Inline, ao sair do campo (não apenas no submit)
- **Smart defaults**: Preencha o que for previsível
- **Progressive disclosure**: Oculte campos avançados atrás de "Mais opções"
- **Min-height de targets**: 44px para botões e inputs (touch-friendly)

### 5. Feedback & Affordance

- Feedback visual em **< 100ms** para cliques
- Ações destrutivas: **confirmação obrigatória** (modal ou typed confirmation)
- Clickable **parece** clickable: cursor pointer, hover state, underline em links
- Toast/notice para operações assíncronas bem-sucedidas
- Disabled explica POR QUÊ (tooltip ou texto adjacente)

### 6. UX Auditor

Ao auditar uma tela, use esta checklist ranqueada por severidade:

| Severidade | Critério |
|---|---|
| 🔴 P0 | Ação destrutiva sem confirmação |
| 🔴 P0 | Zero feedback em operação (botão não muda) |
| 🟡 P1 | Estado faltando (loading/empty/error) |
| 🟡 P1 | Hierarquia invertida (delete em destaque, busca escondida) |
| 🟢 P2 | Inconsistência de espaçamento ou tipografia |
| 🟢 P2 | Contraste insuficiente (< 4.5:1 para texto) |
| ⚪ P3 | Micro-animações ausentes |
| ⚪ P3 | Feedback tátil/hover faltando |

### 7. Design System

Se o projeto tiver `DESIGN.md`, leia-o antes de gerar qualquer UI.
Se não tiver, ofereça-se para criar um com base nos tokens existentes.

O DESIGN.md deve conter:
- **Cores**: Paleta completa com variáveis CSS
- **Tipografia**: Família, tamanhos, pesos, line-heights
- **Espaçamento**: Escala (4, 8, 12, 16, 20, 24, 32, 40, 48...)
- **Bordas**: Radius (8px, 9px, 10px, 14px, 16px...)
- **Sombras**: Tokens de elevação
- **Componentes**: Botões, inputs, cards, pills, callouts

### 8. Visual Character

Para cada interface, tome UMA decisão por eixo:

| Eixo | Pergunta | Não aceitar |
|---|---|---|
| **Tipografia** | Qual a família? Tamanhos? | Default do browser |
| **Cor** | Qual a cor accent? Background? | Framework palette genérica |
| **Espaçamento** | Denso ou arejado? | Padding aleatório |
| **Acabamento** | Bordas arredondadas? Sombras? Blur? | Sem decisão explícita |

---

## Tokens do Dashboard Second Brain (Referência)

```css
/* Dark (padrão) */
--bg: #101513;
--rail: #111813;
--panel: #18201b;
--panel2: #1d2720;
--border: #334038;
--text: #edf3ed;
--muted: #aab9ae;
--accent: #b8f37b;
--accent-ink: #1d3019;
--good: #9bdeb3;
--warn: #f4c583;
--blue: #9bc8fa;
--violet: #cbb3ef;
--danger: #ffb3ac;

/* Light */
--bg: #f5f7f3;
--panel: #fff;
--text: #1b291e;
--accent: #39671f;
--accent-ink: #fff;

/* Typography */
font: 15px/1.6 "Segoe UI", system-ui, sans-serif;
h1: 32px/1.2 weight 640, letter-spacing -1px
h2: 19px/1.4 letter-spacing -0.35px
h3: 16px/1.5

/* Spacing scale */
4, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 40, 44, 48px

/* Border radius */
Buttons/inputs: 8-9px
Cards/panels: 14px
Dialogs: 16px
Pills: 20px
Full round (nav items): 9px → full

/* Min touch target */
42-44px (buttons, inputs, nav items)
```

---

## Validação

Após gerar UI, verifique mentalmente:

- [ ] Intent discovery feito (quem, o quê, pior erro)
- [ ] 1 ação primária por viewport
- [ ] Todos os 5 estados cobertos
- [ ] Labels visíveis (não apenas placeholder)
- [ ] Ações destrutivas com confirmação
- [ ] Tokens do DESIGN.md aplicados
- [ ] Decisão explícita por eixo visual
- [ ] Contraste ≥ 4.5:1
- [ ] Touch targets ≥ 44px

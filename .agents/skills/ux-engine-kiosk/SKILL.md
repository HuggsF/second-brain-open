---
name: ux-engine-kiosk
description: >-
  Skill de UX/Design para interfaces KIOSK Brands. Ative sempre que
  o agente precisar criar, auditar ou refatorar uma interface de usuário
  (HTML, CSS, JS). Aplica raciocínio de design sênior com product workflow
  completo, 8 skills de design, gates automatizáveis e UX brief persistente.
  Inspirado em plugin87/ux-ui-agent-skills (XIAS) e Sakaax/ux-pilot.
---

# UX Engine KIOSK — Design Reasoning para Agentes

> Skill de UX/Design adaptado para o stack KIOSK Brands (Antigravity, vanilla JS).
> Benchmarks: [XIAS](https://github.com/plugin87/ux-ui-agent-skills) (1.6k⭐, 50 gates),
> [ux-pilot](https://github.com/Sakaax/ux-pilot) (376 regras).

---

## Product Workflow (Fluxo Obrigatório)

Toda feature de UI DEVE seguir estas 8 etapas em ordem:

```
1. Intent Discovery  → Quem/O quê/Pior caso
2. Brief Lock        → ux-brief.md preenchido e commitado
3. Wireframe/Spec    → Estrutura antes de visual
4. Design System     → DESIGN.md lido/aplicado
5. Code              → Markup + Styles + Logic
6. UX Audit          → Gates + checklist
7. Critique          → Arguir pela rejeição
8. Ship              → Merge com evidências
```

### Regra de ouro
> **Não pule etapas.** Se pedido for "faz um botão", o workflow inteiro ainda
> se aplica — só que cada etapa leva 30 segundos em vez de 30 minutos.

---

## UX Brief Persistente

Antes de tocar qualquer UI, verifique se existe `ux-brief.md` na raiz do projeto.

- **Se existir:** Leia-o. Suas decisões devem ser consistentes com o brief.
- **Se não existir:** Crie-o usando o template em
  [resources/ux-brief-template.md](./resources/ux-brief-template.md)
- **A cada sessão:** Adicione uma entrada no "Histórico de Decisões" do brief.

O brief persiste entre sessões e é a memória de UX do projeto.

---

## Os 8 Skills de Design

### 1. Intent Discovery (OBRIGATÓRIO antes de codar)

Responda antes de escrever qualquer markup:

1. **Quem** usa esta tela? (papel, nível técnico, frequência)
2. **O que** precisa fazer aqui? (tarefa primária)
3. **Qual o pior erro** possível? (ação destrutiva)
4. **Qual o estado mais comum** ao chegar? (vazio? lista longa? erro?)

Se o usuário não responder, faça suposições razoáveis e registre-as no brief.

### 2. Information Hierarchy

| Nível | Tratamento visual |
|---|---|
| **Primário** | Botão `primary`, posição dominante, máximo 1 por viewport |
| **Secundário** | Botão com borda, menor destaque |
| **Terciário** | Overflow menu, link discreto, ou oculto em "..." |

- Scanning: F-pattern (listas), Z-pattern (landing)
- Ação destrutiva (Delete) NUNCA é primária — vai para overflow ou terciário

### 3. State Completeness

Todo componente DEVE implementar todos os 5 estados:

| Estado | Requisito | Anti-pattern |
|---|---|---|
| **Loading** | Skeleton preservando layout | Spinner genérico no centro |
| **Empty** | Ilustração/ícone + CTA claro | Tela em branco |
| **Error** | Mensagem humana + retry | `alert()` ou console.error |
| **Success** | Confirmação + próximo passo | Nenhum feedback |
| **Partial** | Indicador de dados incompletos | Dados truncados sem aviso |

### 4. Form UX

- **Labels**: Sempre acima do campo, nunca placeholder-only
- **Agrupamento**: Campos relacionados em fieldsets visuais
- **Validação**: Inline ao sair do campo (não apenas no submit)
- **Smart defaults**: Preencha o que for previsível
- **Progressive disclosure**: "Mais opções" para campos avançados
- **Min-height**: 44px para botões e inputs (touch-friendly)

### 5. Feedback & Affordance

- Feedback visual em **< 100ms** para cliques
- Ações destrutivas: **confirmação obrigatória** (modal ou typed confirmation)
- Clickable **parece** clickable: cursor pointer, hover, underline
- Toast/notice para operações assíncronas bem-sucedidas
- Disabled explica POR QUÊ (tooltip ou texto adjacente)

### 6. UX Auditor

Ao auditar, use esta checklist com severidade:

| Sev. | Gate | Critério |
|---|---|---|
| 🔴 P0 | `destructive_confirm` | Ação destrutiva sem confirmação |
| 🔴 P0 | `feedback_zero` | Zero feedback em operação (botão não muda) |
| 🔴 P0 | `contrast` | Contraste < 4.5:1 para texto normal |
| 🟡 P1 | `state_missing` | Estado faltando (loading/empty/error) |
| 🟡 P1 | `hierarchy_inverted` | Delete em destaque, busca escondida |
| 🟡 P1 | `target_size` | Elemento clicável < 44px |
| 🟢 P2 | `spacing_inconsistent` | Valores de espaçamento fora da escala |
| 🟢 P2 | `hardcoded_values` | Cor/tamanho hardcoded (deve usar token) |
| 🟢 P2 | `label_missing` | Input sem label visível |
| ⚪ P3 | `animation_missing` | Micro-animações ausentes |
| ⚪ P3 | `hover_missing` | Feedback hover faltando |
| ⚪ P3 | `emoji_as_icon` | Emoji usado como ícone (use SVG) |

### 7. Design System

Se o projeto tiver `DESIGN.md`, leia-o antes de gerar qualquer UI.
Se não tiver, ofereça-se para criar um.

O DESIGN.md deve conter:
- Paleta completa com variáveis CSS (dark + light)
- Escala tipográfica (família, tamanhos, pesos, line-heights)
- Escala de espaçamento (4, 8, 12, 16, 20, 24, 32...)
- Border radius por contexto
- Sombras e elevação
- Componentes base (botões, inputs, cards, pills, callouts)

**Regra: NUNCA invente valores — use os tokens do DESIGN.md.**

### 8. Visual Character

Para cada interface, tome UMA decisão explícita por eixo:

| Eixo | Pergunta | Não aceitar |
|---|---|---|
| **Tipografia** | Qual família? Tamanhos? | Default do browser |
| **Cor** | Qual accent? Background? | Framework palette genérica |
| **Espaçamento** | Denso ou arejado? | Padding aleatório |
| **Acabamento** | Radius? Sombras? Blur? | Sem decisão explícita |

---

## Critique Mode (Arguir pela Rejeição)

Após gerar UI, ative o modo crítico e tente **rejeitá-la**:

1. Renderize mentalmente a tela
2. Encontre 3 problemas que um designer sênior apontaria
3. Pergunte: "Se eu fosse um user testando isso pela primeira vez, o que me frustraria?"
4. Verifique: "O empty state parece uma tela quebrada?"
5. Verifique: "O loading parece disabled?"
6. Verifique: "O toast confirma algo que não mudou na tela?"

Se encontrar problemas, corrija ANTES de entregar.

---

## Tokens do Dashboard Second Brain (Referência Rápida)

```css
/* Dark */
--bg:#101513; --panel:#18201b; --border:#334038;
--text:#edf3ed; --muted:#aab9ae; --accent:#b8f37b;
--good:#9bdeb3; --warn:#f4c583; --danger:#ffb3ac;

/* Typography */
font: 15px/1.6 "Segoe UI", system-ui, sans-serif;
h1: 32px/640; h2: 19px; h3: 16px;

/* Spacing: 4,8,10,12,14,16,18,20,22,24,28,32,40,44,48 */
/* Radius: 4,8,9,10,14,16,20,9999 */
/* Min touch: 42-44px */
```

> Para referência completa: [`dashboard/DESIGN.md`](file:///c:/KIOSK/second-brain/dashboard/DESIGN.md)

---

## Checklist de Validação Final

Após gerar UI, verifique:

- [ ] **Workflow:** Todas as 8 etapas seguidas
- [ ] **Brief:** `ux-brief.md` atualizado
- [ ] **Intent:** Quem/o quê/pior erro documentados
- [ ] **Hierarchy:** 1 ação primária por viewport
- [ ] **States:** 5 estados cobertos (loading/empty/error/success/partial)
- [ ] **Forms:** Labels visíveis, validação inline, min 44px
- [ ] **Feedback:** Confirmação em ações destrutivas, < 100ms
- [ ] **Tokens:** DESIGN.md aplicado, zero hardcoded
- [ ] **Character:** Decisão explícita por eixo
- [ ] **Contrast:** ≥ 4.5:1 para texto
- [ ] **Targets:** ≥ 44px em interativos
- [ ] **Critique:** 3 problemas buscados e resolvidos

---

## Referências Open-Source

- [plugin87/ux-ui-agent-skills](https://github.com/plugin87/ux-ui-agent-skills) — 50 gates, 138 DS, MIT
- [Sakaax/ux-pilot](https://github.com/Sakaax/ux-pilot) — 376 regras, brief persistente, MIT
- [ibelick/ui-skills](https://github.com/ibelick/ui-skills) — Registry modular de skills
- [open-pencil/open-pencil](https://github.com/open-pencil/open-pencil) — Design-as-Code com MCP

# DESIGN.md — Second Brain Dashboard

> Design System do dashboard do Second Brain KIOSK Brands.
> Fonte de verdade para decisões visuais. Consultado por agentes de IA
> antes de gerar ou alterar qualquer interface.
>
> Última atualização: 2026-10-13

---

## 1. Visual Character

| Eixo | Decisão |
|---|---|
| **Tipografia** | "Segoe UI", system-ui, sans-serif — funcional, nativa, sem download |
| **Cor** | Verde orgânico (#b8f37b accent) sobre fundo escuro profundo (#101513) |
| **Espaçamento** | Denso-médio — painel operacional com informação rica |
| **Acabamento** | Bordas arredondadas suaves (8-16px), sem sombras pesadas, border sutil |
| **Identidade** | Dashboard técnico-operacional — clareza > decoração |

---

## 2. Paleta de Cores

### Dark Mode (padrão)

```css
:root {
  --bg:         #101513;   /* Fundo principal */
  --rail:       #111813;   /* Sidebar/rail */
  --panel:      #18201b;   /* Superfície de cards */
  --panel2:     #1d2720;   /* Superfície elevada */
  --border:     #334038;   /* Bordas e divisores */
  --text:       #edf3ed;   /* Texto primário */
  --muted:      #aab9ae;   /* Texto secundário */
  --accent:     #b8f37b;   /* Cor de destaque (verde limão) */
  --accent-ink: #1d3019;   /* Texto sobre accent */
  --good:       #9bdeb3;   /* Status positivo */
  --warn:       #f4c583;   /* Status de alerta */
  --blue:       #9bc8fa;   /* Info, citações */
  --violet:     #cbb3ef;   /* Infra, categorias */
  --danger:     #ffb3ac;   /* Erros, destrutivo */
  --shadow:     0 20px 60px #0004;
  color-scheme: dark;
}
```

### Light Mode

```css
:root[data-theme=light] {
  --bg:         #f5f7f3;
  --rail:       #eef2e9;
  --panel:      #fff;
  --panel2:     #f1f5ee;
  --border:     #c6d2c4;
  --text:       #1b291e;
  --muted:      #4c6251;
  --accent:     #39671f;
  --accent-ink: #fff;
  --good:       #246942;
  --warn:       #835210;
  --blue:       #2f6095;
  --violet:     #714d96;
  --danger:     #9f352d;
  --shadow:     0 20px 60px #1a341512;
  color-scheme: light;
}
```

### Semântica das cores

| Token | Uso |
|---|---|
| `--accent` | CTAs, links, ícones de destaque, bordas de seleção |
| `--good` | Operação OK, status saudável, confirmações |
| `--warn` | Atenção, pendências, alertas não-críticos |
| `--danger` | Erros, ações destrutivas, falhas |
| `--blue` | Informação, citações, referências |
| `--violet` | Categorias de infraestrutura |

---

## 3. Tipografia

```css
/* Base */
body { font: 15px/1.6 "Segoe UI", system-ui, sans-serif; }

/* Escala */
h1   { font-size: 32px; font-weight: 640; letter-spacing: -1px; line-height: 1.2; }
h2   { font-size: 19px; letter-spacing: -0.35px; line-height: 1.4; }
h3   { font-size: 16px; line-height: 1.5; }

/* Utilitários */
.eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 1.7px; }
.small   { font-size: 12px; }
.muted   { color: var(--muted); }
```

### Regras tipográficas
- **Nunca** usar font-size abaixo de 11px
- Labels: 13px, cor `--muted`
- Corpo: 14-15px
- Stats/números grandes: 32px, weight 600, letter-spacing -1px
- Markdown content: 14px, line-height 1.85, max-width 80ch

---

## 4. Espaçamento

### Escala base (em px)

```
4 — micro (gap de ícones)
8 — tight (gap entre pills, checks)
10-12 — compact (padding de pills, meta)
14-16 — default (padding de cards, gap de grids)
18-20 — comfortable (margin entre seções)
22-24 — spacious (padding de painéis maiores)
28-32 — section (margin entre grandes blocos)
40-44 — landmark (padding de landmarks, min-height de targets)
48 — max (padding de empty states)
```

### Padrão de aplicação

| Contexto | Padding/Gap |
|---|---|
| Botão | 8px 14px (min-height 42px) |
| Input | 10px 12px (min-height 44px) |
| Card/Panel | 22px |
| Dialog | 24px |
| Rail | 32px 20px |
| Main content | 30px 32px |
| Stat card | 19px 20px |

---

## 5. Bordas e Arredondamento

```css
/* Border radius scale */
--r-xs:   4px;    /* Código, tags pequenas */
--r-sm:   8px;    /* Inputs, textareas */
--r-md:   9px;    /* Botões, nav items */
--r-lg:   10px;   /* Cards de resultado, small panels */
--r-xl:   14px;   /* Painéis principais */
--r-2xl:  16px;   /* Dialogs */
--r-pill: 20px;   /* Pills, badges */
--r-full: 9999px; /* Botões circulares (icon-button) */
```

### Bordas
- Cor padrão: `var(--border)` (#334038 dark, #c6d2c4 light)
- Largura: 1px solid
- Active/selected: `var(--accent)` com stroke-width 2.5

---

## 6. Sombras e Elevação

```css
/* Nível 1: Diálogos e notices */
--shadow: 0 20px 60px #0004;

/* backdrop de dialog */
dialog::backdrop { background: #08100acf; backdrop-filter: blur(4px); }
```

> O dashboard é propositalmente flat. Sombras são reservadas apenas
> para elementos sobrepostos (dialogs, notices, tooltips).

---

## 7. Componentes

### Botões

| Variante | Classe | Background | Border | Texto |
|---|---|---|---|---|
| Default | `button` | `--panel2` | `--border` | `--text` |
| Primary | `.primary` | `--accent` | `--accent` | `--accent-ink` |
| Subtle | `.subtle` | transparent | `--border` | `--text` |
| Active | `.active` | `--panel2` | `--accent` | `--accent` |
| Icon | `.icon-button` | transparent | — | `--text` |
| Disabled | `:disabled` | — | — | opacity 0.7 |

Todos: min-height 42px, border-radius 9px, font-weight 550

### Pills/Badges

```css
.pill {
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: 20px;
  font-size: 11px;
  font-weight: 550;
}
/* Variantes: .good, .warn, .blue, .violet, .accent */
```

### Cards/Panels

```css
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px;
}
```

### Callouts

```css
.callout {
  padding: 13px 16px;
  background: var(--panel2);
  border-left: 3px solid var(--accent);
  border-radius: 0 8px 8px 0;
  font-size: 13px;
}
/* Variantes: .warn (border --warn), .error (border+color --danger) */
```

### Inputs

```css
input, select, textarea {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  min-height: 44px;
}
```

---

## 8. Layout

### Estrutura principal
```
┌──────────────────────────────────────────┐
│  Rail (224px, fixed left)                │
│  ┌────────────────────────────────────┐  │
│  │ Brand + Nav                        │  │
│  └────────────────────────────────────┘  │
├──────────────────────────────────────────┤
│  Shell (margin-left: 224px)              │
│  ┌────────────────────────────────────┐  │
│  │ Topbar (86px, search + actions)    │  │
│  ├────────────────────────────────────┤  │
│  │ Main (#main, padding 30px 32px)    │  │
│  ├────────────────────────────────────┤  │
│  │ Footer                             │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### Breakpoints

| Breakpoint | Comportamento |
|---|---|
| ≥ 1500px | Max-width 1600px, padding aumentado |
| ≤ 1150px | Rail 192px, grids colapsam |
| ≤ 900px | Rail vira topbar sticky, layout 1-col |
| ≤ 650px | Rail estática, tudo compacto, mobile-first |

---

## 9. Acessibilidade

- **Focus visible**: outline 3px solid `--accent`, offset 4px
- **Skip link**: Pula para `#content`
- **Reduced motion**: Remove todas as transitions
- **Min touch target**: 42-44px em todos os interativos
- **sr-only**: Classe disponível para texto oculto visualmente
- **Contraste mínimo**: 4.5:1 para texto, 3:1 para elementos grandes
- **Labels**: Todo input deve ter label visível (nunca placeholder-only)

---

## 10. Regras para Agentes

1. **Leia este arquivo** antes de gerar qualquer UI para o Second Brain
2. **Use as variáveis CSS** existentes — nunca invente cores hardcoded
3. **Siga a escala de espaçamento** — não use valores arbitrários
4. **Mantenha o visual character** — denso-operacional, verde orgânico, flat
5. **Teste nos 4 breakpoints** antes de entregar
6. **Sempre implemente todos os 5 estados** (loading, empty, error, success, partial)
7. **Min-height 44px** em todo elemento interativo

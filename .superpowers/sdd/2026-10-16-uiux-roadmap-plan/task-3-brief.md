# Task 3 Brief — VISUAL-01: Criar tema orgânico para o Nexus

## Objetivo
Criar `nexus/src/theme-organic.css` com CSS custom properties mapeadas do DESIGN.md do Dashboard, permitindo ao Nexus renderizar com a paleta técnico-orgânica.

## Allowed Files
- `nexus/src/theme-organic.css` (novo)

## No-Touch Files
- `nexus/src/cyberpunk.css` (tema atual — preservar intacto)
- `dashboard/DESIGN.md` (fonte-de-verdade — apenas leitura)

## Referência: Tokens do DESIGN.md
```css
/* Paleta */
--bg: #101513;
--bg-card: #19201d;
--bg-field: #121915;
--accent: #b8f37b;
--accent-dim: #7aad3f;
--text: #d9e5d0;
--text-secondary: #8fa388;
--border: #2a3530;

/* Tipografia */
font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;

/* Espaçamento */
--space-xs: 4px;
--space-sm: 8px;
--space-md: 16px;
--space-lg: 24px;
--space-xl: 32px;
--space-2xl: 48px;
```

## Passos
1. Ler `dashboard/DESIGN.md` para extrair tokens exatos
2. Criar `nexus/src/theme-organic.css` com seletor `[data-theme="organic"]`
3. Mapear cada variável cyberpunk para o equivalente orgânico
4. Incluir override de font-family para system-ui
5. Verificar que o arquivo compila (sem erros de sintaxe CSS)

## Critério de Aceite
- Arquivo existe em `nexus/src/theme-organic.css`
- Contém seletor `[data-theme="organic"]` com todas as variáveis de cor mapeadas
- Não altera nenhum arquivo existente

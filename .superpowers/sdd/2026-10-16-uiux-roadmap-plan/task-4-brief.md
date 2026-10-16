# Task 4 Brief — VISUAL-02: Alternador de tema no Header

## Objetivo
Adicionar botão de alternância de tema (cyberpunk ↔ orgânico) no Header do Nexus com persistência em localStorage.

## Allowed Files
- `nexus/src/components/Header.jsx`
- `nexus/src/App.jsx` ou `nexus/index.html` (para import do CSS e data-theme inicial)

## No-Touch Files
- `nexus/src/context.jsx`
- `nexus/src/simulation.mjs`
- `nexus/src/cyberpunk.css`

## Passos
1. Importar `theme-organic.css` em `App.jsx` ou `index.html` (ambos carregados, tema ativo por `data-theme`)
2. No `Header.jsx`, adicionar botão com ícone (ex: Palette do Lucide)
3. onClick: alternar `document.documentElement.dataset.theme` entre `'cyberpunk'` e `'organic'`
4. Persistir em `localStorage.setItem('nexus-theme', theme)`
5. No load, ler `localStorage.getItem('nexus-theme')` e aplicar
6. Rodar testes: `cd nexus; node --test` → 82 pass

## Critério de Aceite
- Botão visível no Header
- Clique alterna as cores da interface
- Reload preserva escolha
- Testes não regridem (82/84)

# Task 6 Brief — DEDUP-02: Reorganizar nav do Dashboard

## Objetivo
Agrupar os 12 itens de navegação do Dashboard em ≤ 6 categorias de primeiro nível com sub-menus expansíveis, mantendo todas as rotas hash existentes.

## Allowed Files
- `dashboard/app.js` (nav rendering section only)

## No-Touch Files
- `dashboard/core.js`
- `dashboard/DESIGN.md`
- Qualquer arquivo de módulo/visão (`knowledge-view.js`, `graph-scene.js`, etc.)

## Agrupamento Proposto
```
📊 Visão Geral          → #page=overview
🧠 Conhecimento         → sub: #page=knowledge, #page=graph, #page=queries
📋 Operação             → sub: #page=playbooks, #page=workflows
🏗️ Arquitetura          → sub: #page=architecture, #page=product, #page=teams
📡 Observabilidade      → #page=observability
🤖 Agentes              → sub: #page=nexus, #page=jev
```

## Passos
1. Localizar a seção de renderização do nav em `app.js` (procurar `renderNav` ou array de pages)
2. Agrupar itens em categorias com `<details>/<summary>` ou similar
3. Manter todas as 12 rotas hash funcionais
4. Preservar keyboard nav (Tab/Enter/Escape)
5. Rodar testes: `cd dashboard; node --test` → 178 pass

## Critério de Aceite
- Nav mostra ≤ 6 itens de primeiro nível
- Todas as 12 rotas hash continuam acessíveis
- Testes não regridem (178/178)
- Keyboard navigation funciona (Tab entre categorias, Enter para expandir)

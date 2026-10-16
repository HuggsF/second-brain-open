# Knowledge Product — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Transformar showcase e grafo em explorador legível e útil, informado por pesquisa oficial.
**Architecture:** Modelo puro + renderer SVG + UI isolada, exportados para HTML standalone a partir do mesmo snapshot.
**Tech Stack:** JavaScript UMD/SVG/CSS, Python stdlib, node:test.
**Spec:** `.superpowers/specs/2026-10-15-07-30-knowledge-product.md`.

## Global Constraints
Preservar mudanças existentes; nenhum segredo, execução de ferramentas, alteração do vault ou publicação. DESIGN.md, português claro, produto em desenvolvimento e sem atividade fictícia. Não modificar allowlists. Catálogo permanece canônico e somente leitura.

## Review Focus
- Busca por título não vira evidência de corpo; fontes breves/ausentes visíveis.
- Panorama pequeno e foco preservam direção, ID, relações paralelas e contagem honesta.
- Leitor/salvos funcionam offline, inclusive storage negado e texto hostil.
- Interrupção/reduced motion/resize/dispose não deixam RAF/listeners pendentes.
- Exportação usa os mesmos módulos, nenhuma dependência de rede e não contém fechamento de script injetável.

### 1. Pesquisa e auditoria
- [ ] Relatório oficial comparativo, limitações, oportunidades e níveis de maturidade.
- [ ] Auditoria de dados atuais e desenho da primeira jornada real.

### 2. Modelo e movimento (tarefas independentes)
- [ ] `knowledge-model.js` + testes: build/search/overview/focus; projeção imutável e rótulos honestos.
- [ ] `knowledge-motion.js` + testes: layout/mount/update/select/zoom/fit/dispose; panorama e foco com transição.

### 3. Interface e entrega
- [ ] `knowledge-view.js`, `knowledge.css` e testes DOM: busca, categorias, fonte, percurso, salvos e roadmap.
- [ ] Integrar `app.js`/`index.html`, conservar experiência técnica e atualizar ux-brief.
- [ ] Gerador Python e testes: página local e showcase standalone, backup do original.

### 4. Verificação
- [ ] Testes novos, suíte JS, build_graph, exportação, diff check e revisão independente.
- [ ] Registrar limitações de browser e maturidade, situação do Git e instruções de uso local.

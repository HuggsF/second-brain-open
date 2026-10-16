# Grafo de órbitas e camadas — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Implementar os dois layouts no dashboard existente com documentação da ontologia e transição animada.
**Architecture:** Projeção e coordenadas puras; renderizador SVG com estado por ID; integração no explorador existente.
**Tech Stack:** JavaScript UMD, SVG, CSS local, node:test, Python.
**Spec:** `.superpowers/specs/2026-10-15-12-00-grafo-orbitas-camadas.md`.

## Global Constraints
Offline; sem alteração do catálogo/vault; sem execução de comandos pelo browser; preservar relações dirigidas, evidências e IDs. Usar DESIGN.md e atualizar ux-brief.md. Não alterar trabalho preexistente alheio. Implementação no checkout indicado pelo usuário, branch `feature/knowledge-graph-dashboard`.

## Review Focus
- Grafo vazio ou filtrado: nenhum NaN e estado vazio utilizável.
- Ciclos, paralelas e nós isolados: preservar topologia e direção.
- Cliques rápidos: animação parte do frame atual, sem saltos por recriação do SVG.
- Teclado, movimento reduzido e navegação: foco persistente e cancelamento de trabalho pendente.
- Densidade/mobile: lista equivalente e controle de zoom; nenhuma promessa de performance sem benchmark.

### Task 1: Projeção e layouts (delegação independente)
**Files:** criar `dashboard/graph-layout.js` e `dashboard/tests/graph-layout.test.cjs`.
**Interfaces:** `BrainGraphLayout.project(data, {domainLabels}) -> scene`, `radial(scene) -> Map<id, {x,y}>`, `layered(scene,{focusDomain,orientation}) -> Map<id,{x,y}>`; scene contém nodes (kind core/category/entity, entityId para entidades), edges reais e links visuais.
- [x] Escrever testes e observar falha antes de implementar.
- [x] Implementar layouts determinísticos, imutáveis e finitos; foco ordena categoria primeiro; orientação transposta.
- [x] Rodar os testes da tarefa e revisar contratos.

### Task 2: Renderização e integração
**Files:** criar `dashboard/graph-scene.js` e testes; modificar `graph-ui.js`, `index.html`, `style.css`, `app.js`.
**Interfaces:** `BrainGraphScene.mount(svg, {onNode,onEdge,onFrame}) -> {update(scene,positions,options),select(nodeId,edgeIds),dispose()}`; update anima nós/arestas/guias, reutilizando elementos.
- [x] Escrever testes comportamentais de animação/seleção antes do código.
- [x] Integrar controles, categorias clicáveis, lista e inspector sem trocar a estrutura semântica.
- [x] Validar clique radial/camadas, interrupção, orientação, zero resultados, zoom, teclado e descarte.

### Task 3: Documentação e verificação
**Files:** criar `dashboard/analysis/graph-architecture.md`, `dashboard/graph-model.d.ts`; atualizar `ux-brief.md`.
- [x] Documentar decisões, modelo tipado, equações, segurança e execução local; distinguir implementado de evolução.
- [x] Rodar `node --test --test-isolation=none dashboard/tests/*.test.cjs` e `.venv/Scripts/python.exe dashboard/tests/test_build_graph.py`; comparar falhas com baseline.
- [x] Revisão independente dos arquivos alterados. Navegador indisponível: política recusou abertura da origem local; nenhuma inspeção visual foi feita.
- [x] Reportar entregas, provas e limitações; sem commit/push/merge solicitado.

## Resultado
23/23 testes novos; suíte JS 139/142, mesmas três falhas do baseline; build_graph 5/5. Revisão final independente sem achados pendentes. Detalhes em `.superpowers/ledger/2026-10-15-12-00-grafo-orbitas-camadas.md`.

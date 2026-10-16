# Ledger — plano: .superpowers/plans/2026-10-15-12-00-grafo-orbitas-camadas.md

Task 1: complete — projeção/layouts puros e 11 testes. Task 2: complete — renderer animado (4 testes), integração/UI (8 testes). Task 3: complete — análise arquitetural, contratos v1/v2, exemplo tipado, UX brief e revisão independente.

Ruling: manter checkout `C:/KIOSK/second-brain`, branch preexistente `feature/knowledge-graph-dashboard` — usuário indicou dashboard em andamento; não deslocar trabalho do Antigravity nem modificar arquivos alheios. Sem commit, push ou merge.

Ruling: SVG e JS locais, sem migrar para React/D3 — integração com stack offline existente. Catálogo e vault não alterados. V2, Dijkstra e execução CLI apenas documentados; ferramentas futuras permanecem sujeitas ao broker/policy do servidor.

Ruling: panorama pode miniaturizar rótulos em grafos densos. Foco automático em categoria usa escala máxima 12/11, preservando rótulos de 12 unidades com pelo menos 11px CSS no viewport calculado; restante por pan/zoom/lista. Enquadrar sempre considera todos os nós. Acrescentado seletor de categoria em tamanho normal.

## Evidências
- RED → GREEN: renderer ausente; integração ausente; foco sem enquadramento próprio; foco denso ilegível; Enquadrar móvel recortava nós; ResizeObserver desfazia foco. Testes observados falhando antes das respectivas implementações/correções.
- `node --test --test-isolation=none dashboard/tests/graph-ui.test.cjs dashboard/tests/graph-scene.test.cjs dashboard/tests/graph-layout.test.cjs`: 23/23 passam; revisão independente repetiu o resultado.
- `node --test --test-isolation=none dashboard/tests/*.test.cjs`: 142 testes, 139 passam, 3 falham. Baseline anterior: 119 testes, 116 passam, mesmas 3 falhas.
- Falha preexistente `generated snapshot validates and environments have distinct sources`: fonte de deployment não comprova SHA declarado (`integration.test.cjs:12`).
- Falha preexistente `modal_semantics`: divs modais em `jev-ui.js` (`ux-gates.test.cjs:45`).
- Falha preexistente `hardcoded_values`: 265 estilos inline, teto 253 (`ux-gates.test.cjs:99`). Contagem não aumentou.
- `.venv/Scripts/python.exe dashboard/tests/test_build_graph.py`: 5/5 passam fora da sandbox; tentativa inicial foi impedida ao criar subpastas das fixtures temporárias.
- `node --check dashboard/graph-model.d.ts` e `git diff --check`: passam. TypeScript semântico não executado (tsc não disponível), contrato é documentação.
- Revisão independente identificou persistência de graphMode e ResizeObserver: ambos corrigidos e revalidados; revisão final sem achados de alta confiança.
- Após a revisão, um processo externo criou `graph-events.js` e acrescentou efeitos de pulse a `graph-scene.js`. Preservados os acréscimos; fixture DOM dos testes passou a incluir `document.head` e badge foi ajustado de 9px para o mínimo de 11px do DESIGN.md. Os efeitos de eventos não fazem parte desta entrega nem da revisão independente anterior.
- Revalidação após essa edição simultânea: 23/23 testes novos, suíte completa 139/142 com somente as mesmas três falhas do baseline. Hashes de UI/scene/layout/index/CSS ficaram estáveis durante a execução final.

## Limitação de inspeção
Browser Use recusou abertura de `http://127.0.0.1:8851` pela política de acesso à origem. Sem inspeção em navegador real, screenshot ou benchmark. Não houve tentativa de contornar essa recusa. Servidor HTTP estático usado para tentativa encerrado ao concluir.

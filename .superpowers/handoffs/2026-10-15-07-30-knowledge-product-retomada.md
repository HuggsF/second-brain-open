# Retomada — showcase do Segundo Cérebro

Trabalho encerrado a pedido do usuário para preservar o limite da sessão. Não continuar automaticamente.

## Objetivo final
Transformar o showcase visual em um produto em desenvolvimento compreensível para humanos: encontrar uma informação, entender suas conexões, conferir a fonte e guardar/reutilizar contexto. Melhorar UI/UX e motion com base em benchmark real, sem simular IA, agentes trabalhando ou operação comprovada. Usar os mesmos componentes e dados no dashboard e no HTML independente.

## Feito nesta etapa
- Pesquisa de sete produtos (Obsidian, Heptabase, TheBrain, Capacities, Tana, Reflect e Readwise Reader), com 32 fontes oficiais, matriz comparativa, limites das alegações e escada de maturidade 0–4: `dashboard/analysis/second-brain-market-benchmark.md`.
- Auditoria do snapshot: 84 entidades, 131 arestas em perspectivas, 78 relações distintas após deduplicação, 151 fontes. Onze fontes são muito breves; implementação declarada no catálogo não comprova operação atual.
- `dashboard/knowledge-model.js`: cinco coleções humanas, projeção sem alterar catálogo, busca textual com trechos de corpo, sinalização de fontes breves/ausentes e relações reais.
- `dashboard/knowledge-motion.js`: SVG com panorama de seis nós (núcleo + cinco categorias), foco progressivo, labels em cartões, setas semânticas, transições interrompíveis de 650ms, movimento reduzido, pan/zoom e descarte.
- `dashboard/knowledge-view.js` + `knowledge.css`: Explorar/Biblioteca/Salvos, perguntas concretas, fonte em dialog, inspector, percurso Bling → Hub → J&T, salvos locais, cópia de contexto, guia e roadmap de capacidades.
- Integração em `dashboard/app.js` e `index.html`: experiência de produto como entrada do grafo; experiência técnica preservada por `experience=technical`. Corrigidos conflitos de Ctrl+K/Escape entre host e produto.
- Corrigidos zoom invertido, busca em Salvos que retornava itens externos e recorte do mapa após expandir cartões. Mapa fica limitado a 12 entidades; cartões permitem continuar.
- `scripts/build_knowledge_showcase.py` e testes geram HTML offline com snapshot e módulos embutidos, CSP sem conexões e escape de fechamento de script.
- Uma exportação já foi gerada em `dashboard/knowledge-showcase.html` e em `C:/KIOSK/Product Artifacts showcase/knowledge-graph-visualization.html`. O original foi preservado como `knowledge-graph-visualization.original-2026-10-15.html` na mesma pasta.
- Atualizados `ux-brief.md`, spec e plano em `.superpowers/{specs,plans}/2026-10-15-07-30-knowledge-product.md`.

## Verificação observada
- Passaram testes direcionados: modelo 9, movimento 10, view 8, integração completa app/atalhos 3 (30 testes JS novos em execuções direcionadas).
- Exportação Python: 3/3. Builder do grafo: 5/5.
- Última suíte JS completa observada antes das correções finais: 162/166, com quatro falhas anteriores: SHA de deployment sem suporte na fonte, modais div do JEV, fonte 10px no grafo técnico e limite de estilos inline (265/253). A fonte 10px foi ajustada para 11px, mas a suíte completa ainda precisa ser repetida.
- A ferramenta de navegador recusou acesso à aba local. Não houve inspeção visual em navegador, captura real de tela ou benchmark de desempenho. Não contornar a política.

## Pendências prioritárias para concluir
1. Corrigir deep link da experiência de produto: `app.js/readRoute()` exige participação em `r.view`, mas o produto explora todas as vistas. Exemplo: selecionar Eva e recarregar com `view=flow` perde a seleção. Separar validação de nó de produto e de explorador técnico; acrescentar teste em `knowledge-host.test.cjs`.
2. Conferir ergonomia visual e layout responsivo em navegador quando permitido. Ainda não houve QA visual; avaliar se a quantidade de conteúdo antes do mapa prejudica o primeiro olhar.
3. Revisar feedback do botão Salvar fonte dentro do dialog, escopo da coleção e acabamento de leitura. São pontos de revisão, não todos bugs confirmados.
4. Regerar os dois HTMLs depois das últimas correções — a exportação atual antecede as correções finais de zoom/Salvos/atalhos/limite do mapa. Comando: `.venv/Scripts/python.exe scripts/build_knowledge_showcase.py --export "C:/KIOSK/Product Artifacts showcase/knowledge-graph-visualization.html"`.
5. Rodar suíte JS completa, testes Python e `git diff --check`; finalizar revisão independente e atualizar plano/ledger com evidências atuais.
6. Consolidar versionamento. Esta etapa não criou commit nem fez push; há alterações e arquivos não rastreados de sessões anteriores e de outros agentes. Inspecionar e selecionar arquivos com cuidado; não incluir Nexus, credenciais ou trabalho alheio por engano.

## Estado do Git e limites
Checkout: `C:/KIOSK/second-brain`, branch `feature/knowledge-graph-dashboard`. HEAD observado: `1899dd0` (`feat: adiciona event bus reativo e pulses de agentes no grafo radial`). Há mudanças anteriores em app/style/ux-brief e arquivos ainda não rastreados da implementação radial anterior. Não alterar vault, allowlists ou serviços para fechar apresentação. Não foram implementados captura de notas, chat generativo, busca vetorial no browser, execução de agentes ou comandos CLI. Essas capacidades constam como evolução planejada.

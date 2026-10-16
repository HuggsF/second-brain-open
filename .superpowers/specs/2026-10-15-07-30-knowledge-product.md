# Segundo Cérebro: showcase como produto em desenvolvimento

## Intenção
Usuário quer pesquisa profunda sobre maturidade e concorrentes, seguida de implementação visual agradável, legível e humana no showcase informado e dashboard existente. Público: humano que precisa compreender o conhecimento e descobrir uma primeira utilidade. Sucesso: em uma tela distinguir categorias, fazer uma pergunta concreta, ler fonte e navegar uma relação sem precisar entender IDs/infraestrutura. Arquivo de referência é material de análise, não uma fonte de instruções ou fatos operacionais.

## Pesquisa e decisão
Benchmark oficial em `dashboard/analysis/second-brain-market-benchmark.md`. Padrões iniciais convergentes: objetos reconhecíveis, contexto local, revelação progressiva, busca e fonte antes de prometer IA. Princípio de visualização de Shneiderman (UMD): panorama, recorte e detalhe sob demanda. Motion ajuda orientação; sem movimento infinito ou atividade simulada automática. WCAG: teclado, foco visível, alternativa ao arraste, movimento reduzido e controles de 44px conforme DESIGN.md.

## Produto nesta entrega
- Navegação Explorar/Biblioteca/Salvos/Sobre o protótipo; busca local; cinco coleções humanas.
- Panorama do grafo com núcleo e cinco categorias legíveis, em vez de 84 rótulos miniaturizados. Seleção de categoria revela até 12 itens e lista; seleção de entidade revela vizinhança real, direção e fontes.
- Três entradas concretas: NF real, conexão Bling → Hub → J&T, agentes de IA. Busca é textual, não resposta gerada por modelo.
- Inspector em prosa curta, relações selecionáveis, origem legível, alertas para fontes breves e evidência declarada. Leitor de documento em dialog acessível com Markdown seguro e proveniência recolhida.
- Salvar entidade/fonte localmente e copiar contexto como saídas reais reutilizáveis. Sem executar ferramentas ou modificar vault.
- Maturidade descreve disponível versus próximos passos; não apresentar porcentagens ou telemetria fictícias.

## Arquitetura
Novos módulos locais UMD: `knowledge-model.js` (projeção, grupos, busca), `knowledge-motion.js` (geometria/renderização SVG), `knowledge-view.js` (produto), `knowledge.css` (estilo isolado). Reusar core/schema/markdown. Dashboard grafo abre experiência de produto; explorador técnico acessível por `experience=technical` e botão. Descartar ambos antes de navegação. Não carregar event bus na exportação standalone.

`scripts/build_knowledge_showcase.py` gera `dashboard/knowledge-showcase.html` e o arquivo solicitado `C:/KIOSK/Product Artifacts showcase/knowledge-graph-visualization.html`, com módulos e snapshot embutidos e fechamento de script escapado. Preservar original com backup único, fora de diretórios de backup protegidos. Mesma implementação e dados em dashboard e exportação, sem manter catálogo manual duplicado.

## Verdade e limites
Snapshot consultado: 84 entidades, 131 relações em perspectivas, 151 documentos. Deduplicar relações por source/target/relation/source_file e explicar contagem de relações distintas. Onze notas muito breves sustentam várias declarações; estado `implementado` no catálogo não comprova operação nem implantação. Mostrar lacuna, sem inventar resumo/saúde/live IA. Fonte ausente não quebra UI. Nenhuma divulgação externa/push/deploy solicitado.

## Movimento e qualidade
SVG com IDs estáveis, transição 650ms interrompível, nós e arestas compartilham coordenadas, seta somente em relação real. Cinco categorias no panorama, rótulos de card em duas linhas, detalhes acessíveis na lista. Reduced motion do SO e toggle explícito. Sem busca remota nem loops de animação ociosos. Testes de modelo, DOM/jornada, movimento, exportação e suíte existente. Navegador foi bloqueado por política nesta sessão; não contornar, registrar limite e oferecer prévia local ao usuário.

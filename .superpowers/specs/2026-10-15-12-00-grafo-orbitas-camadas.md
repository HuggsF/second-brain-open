# Segundo Cérebro: órbitas e camadas

## Objetivo e escopo
Evoluir `dashboard/` existente, em sua branch de trabalho, para alternar entre órbitas radiais e camadas horizontais/verticais. Clique numa categoria foca sua hierarquia com animação interrompível. Manter filtros, lista acessível, inspector, fontes e caminhos existentes. Referências do Instagram não foram fornecidas; seguir o comportamento descrito e o DESIGN.md local.

## Decisão de arquitetura
Manter JavaScript modular UMD + SVG nativo, sem dependências remotas, coerente com o dashboard offline. Layouts são funções puras e determinísticas; uma projeção visual acrescenta núcleo/categorias sintéticas sem alterar o catálogo. Renderizador SVG indexa elementos por ID e interpola coordenadas compartilhadas por nós, arestas e câmera via requestAnimationFrame. React/D3 seria uma migração desnecessária neste boilerplate; Cytoscape é alternativa para análise interativa ampla e WebGL para escalas medidas em profiling.

## Dados e semântica
Catálogo atual permanece v1, somente leitura. O grafo de conhecimento é um multigrafo orientado, com IDs, source/target, relation, evidência, fonte e vista. A floresta de apresentação agrupa entidades por domínio. Seus links de pertencimento são visuais, sem seta, fora de BFS/Dijkstra e sem significado de permissão. Documentar contrato ontológico v2 tipado com predicates estáveis, custo não negativo, proveniência, políticas e referências de ações. Não migrar dados, inventar permissões ou habilitar execução CLI nesta entrega.

## Comportamento e matemática
Órbitas: núcleo central; categorias distribuídas por ângulo; entidades em anéis locais. Raios consideram cardinalidade; ordenar por IDs usando comparação binária para repetibilidade. Camadas: núcleo, categorias e entidades em três níveis; categoria focada primeiro e restante preservado como contexto. Alternar orientação transpondo coordenadas. Layout não impõe DAG às relações de conhecimento: ciclos e arestas paralelas permanecem.

Interpolação p(t)=(1-e(t))*p_atual+e(t)*p_destino, e(t)=t²(3-2t), duração 650 ms. Um novo comando parte do último frame, cancela o anterior, e mantém IDs/elementos. Respeitar prefers-reduced-motion, desconexão do DOM e dispose ao navegar. Ajustar câmera à área disponível; no celular manter zoom legível e oferecer lista, arraste e enquadramento.

## Interface, falhas e validação
Controles Órbitas/Camadas/Lista, orientação, voltar ao núcleo, zoom e enquadrar; teclado Enter/Espaço/Escape; status anunciável, legendas diferenciando agrupamento e relação, fontes preservadas. CSS usa tokens existentes, sem CDN ou HTML injetado. Estados vazios e erro de layout visíveis; listas permitem explorar grafos densos.

Provar projeção imutável, determinismo sob permutação, coordenadas finitas, foco e orientação, ciclos/desconexão, animação interrompida/reduced-motion e integração clique/navegação. Executar suíte JS, teste build_graph e inspeção real no navegador quando disponível. Baseline antes da alteração: 116/119 JS passam; falhas preexistentes `generated snapshot validates and environments have distinct sources`, `modal_semantics`, `hardcoded_values` (265 estilos inline / limite 253). Não ampliar essas falhas nem alterar módulos alheios.

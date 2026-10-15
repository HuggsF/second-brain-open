# Grafo do Segundo Cérebro: arquitetura, ontologia e movimento

Data: 2026-10-15. Escopo: evolução do dashboard existente; catálogo e vault preservados.

As quatro entregas são a decisão de arquitetura, o contrato de dados tipado, a matemática dos layouts/transições e a integração funcional no explorador. A referência de comportamento é a [especificação de órbitas e camadas](../../.superpowers/specs/2026-10-15-12-00-grafo-orbitas-camadas.md); os tokens e critérios de interação vêm de [DESIGN.md](../DESIGN.md) e [ux-brief.md](../../ux-brief.md).

## 1. Arquitetura e escolha do motor

O [catálogo v1](../graph-catalog.json) possui 84 entidades e 131 relações distribuídas por oito perspectivas no snapshot consultado. A perspectiva `ontology` reúne as 84 entidades e 53 dessas relações. Essas contagens descrevem os dados, sem constituir benchmark. O [bundle gerado](../graph-data.js) continua derivado do vault; alterar uma posição visual não altera uma nota, uma relação ou sua evidência.

Mantemos JavaScript modular UMD e SVG nativo. A decisão minimiza a mudança sobre HTML/CSS/JS já disponíveis, conserva o funcionamento offline e permite testar projeção, layout e animação de forma isolada. Não há fundamento medido nesta entrega para afirmar um limite de nós, um FPS garantido ou superioridade de desempenho sobre outra biblioteca.

| Opção | Capacidade relevante | Decisão neste projeto |
|---|---|---|
| JavaScript + SVG local | Elementos e interações sob controle dos módulos existentes; texto e foco ligados ao DOM | Adotado para o escopo atual. O custo é manter layout, seleção, câmera e acessibilidade no projeto. |
| D3 | Ferramentas modulares para dados, hierarquias, formas, seleção e transição, sobre padrões web | Poderia fornecer módulos pontuais, inclusive sem React. A troca agora adicionaria outra abstração ao trabalho já delimitado; não é requisito para órbitas determinísticas. [Documentação oficial](https://d3js.org/what-is-d3). |
| Cytoscape.js | Biblioteca de visualização e análise de redes, com layouts, algoritmos e viewport animável | Candidata se análise de grafos, extensões e exploração geral se tornarem a maior parte do produto. Exige adaptar renderer, eventos, estilos e alternativa acessível. [Documentação oficial](https://js.cytoscape.org/). |
| React Flow | Componentes para interfaces de nós em React | Mais pertinente a um editor visual de fluxos dentro de uma aplicação React. Introduzir React e seu ciclo de vida seria uma migração maior do que a alteração atual. [Site oficial](https://reactflow.dev/). |
| WebGL | Renderização 2D/3D com aceleração de hardware em um canvas | Investigar após medir gargalos reais de renderização. Exige decisões próprias sobre picking, labels, foco e alternativa textual; a tecnologia não resolve a semântica nem a política de acesso. [Referência da API](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API). |

As capacidades das alternativas acima vêm de suas documentações; a escolha para este repositório é uma avaliação de integração e manutenção. Qualquer futura migração deve usar o mesmo snapshot e ações de usuário para medir tempo de layout, duração dos frames, quantidade de elementos, memória e legibilidade em desktop e celular.

### Separação de responsabilidades

```text
vault → build_graph.py → graph-data.js (snapshot v1)
                              ↓ filtros existentes
                       graph-layout.project
                              ↓ cena visual
                 radial(scene) / layered(scene)
                              ↓ Map<id,{x,y}>
                       graph-scene.update
                              ↓ SVG / seleção / frames
               graph-ui.js → inspector, lista e câmera
```

- [graph-layout.js](../graph-layout.js): funções puras; não consulta DOM, não executa ações e não modifica o catálogo.
- [graph-scene.js](../graph-scene.js): ciclo de vida SVG e posições do frame atual; elementos indexados por ID.
- [graph-ui.js](../graph-ui.js): filtros, intenção do usuário, estado de seleção, lista equivalente, fontes e controles da câmera.
- [core.js](../core.js): busca, vizinhança e caminho sobre relações reais; não recebe links sintéticos do layout.
- [app.js](../app.js): navegação e descarte do explorador antes de substituir sua árvore DOM.

O contrato de integração é:

```js
const scene = BrainGraphLayout.project(data, { domainLabels });
const positions = BrainGraphLayout.radial(scene);
// Alternativa: layered(scene, { focusDomain, orientation: 'horizontal' })
const renderer = BrainGraphScene.mount(svg, { onNode, onEdge, onFrame });
renderer.update(scene, positions, { layout: 'radial', animate: true, duration: 650 });
renderer.select(nodeId, edgeIds);
// Antes de remover a tela:
renderer.dispose();
```

`update` aceita `layout` (`radial`/`layered`), `focusDomain`, `animate` e `duration`. `onNode` distingue núcleo/categoria/entidade: uma categoria solicita foco de apresentação; uma entidade abre o inspector existente. `onEdge` referencia a relação documental original. `onFrame({positions,progress,options})` informa as posições correntes e o progresso já suavizado, que a câmera usa no mesmo ciclo. `dispose()` cancela trabalho pendente e impede novas atualizações de layout; o descarte da tela remove sua árvore DOM.

## 2. Ontologia e contratos de dados

### Preservar o multigrafo v1

O grafo semântico é um multigrafo orientado: cada relação tem ID próprio, `source`, `target`, verbo livre `relation`, `view`, `evidence` e `source_file`. Várias relações entre o mesmo par são válidas. Uma conexão inversa não é criada automaticamente; ciclos, componentes desconectados e nós sem arestas não são erros de layout.

As posições antigas em `node.views[view]` permanecem no catálogo. A participação na perspectiva continua sendo determinada por `views`; as novas órbitas/camadas calculam sua própria geometria. O schema v1 permanece `version: 1`, sem migração silenciosa de `type`, `relation` ou IDs.

O catálogo de entrada e o snapshot de runtime são contratos diferentes. `CatalogV1` contém `version`, `views`, `nodes` e `edges`, como [graph-catalog.json](../graph-catalog.json). O builder acrescenta `documents`, `teams`, `protocols`, `templates`, `built_from`, `snapshot_id` e `built_at`, formando `SnapshotV1`, carregado em `window.KIOSK_GRAPH`. As fontes são entradas do mapa `documents`, com texto, título, categoria, SHA-256, linhas e data de modificação; não existe uma coleção `sources` na saída v1. O campo `sources` impresso pelo build é somente uma contagem diagnóstica. O schema atual também aceita evidência `local` e aliases, mesmo sem ocorrências desses campos/valores no catálogo consultado.

A projeção cria uma hierarquia de apresentação de três profundidades:

```text
@core
  └─ @domain:<domain>  (kind: category)
       └─ entidade real (kind: entity; entityId preserva o ID canônico)
```

`@core` e as categorias são sintéticos. Os links entre esses três níveis são de agrupamento, sem seta e visualmente distintos das relações documentadas. Não entram em BFS, custo de caminho, inferência de conhecimento, concessão de acesso ou decisão de execução. A estrutura visual é uma árvore nesta projeção; o modelo futuro admite uma floresta. IDs sintéticos pertencem à cena e não são gravados no catálogo.

### Proposta v2 tipada, sem alterar a entrada atual

[graph-model.d.ts](../graph-model.d.ts) descreve a entrada atual (`CatalogV1`), seu snapshot gerado (`SnapshotV1`) e uma proposta independente (`KnowledgeGraphV2`). O arquivo é documentação TypeScript; o browser não o carrega, e TypeScript sozinho não valida JSON recebido em runtime.

| Aspecto | Contrato proposto |
|---|---|
| Entidade | União discriminada por `kind`, com campos próprios para sistema, serviço, agente, ferramenta, política, gate, skill, banco, ambiente, infraestrutura, integração, protocolo, frontend, pipeline, projeto, template, domínio, entidade de negócio, contrato e documento |
| Relação | União por `predicate` estável; `source`/`target` continuam IDs escalares; arestas paralelas conservam IDs distintos |
| Vocabulário | `depends_on`, `contains`, `runs_in`, `hosted_on`, `calls`, `reads_from`, `writes_to`, `produces`, `consumes`, `implements`, `governed_by`, `uses_tool`, `delegates_to`, `validates`, `evidenced_by`, `related_to` |
| Regras ontológicas | Registro versionado de predicates com conjuntos de kinds de origem e destino; mudar texto de exibição não renomeia o predicate |
| Evidência | Estado discriminado; fatos reportados/documentados/implementados incluem proveniência; verificação exige instante e referência do verificador |
| Proveniência | Fonte, SHA-256 do documento, método (`curated`, `extracted`, `observed`), seção/linhas e instantes de declaração/observação |
| Apresentação | `hierarchyParent` opcional, `layout.order` e `layout.rank`; independentes de `contains` e do grafo de conhecimento |
| Caminho | `cost` finito e não negativo, com significado e unidade definidos pelo caso de uso; não equivale a evidência, probabilidade ou autoridade |
| Contexto de segurança | `tenantId`, `classification` e `policyRefs` descritivos; servidor calcula acesso efetivo |
| Ações | Apenas `{actionRef,label}` no nó. Nenhum shell, segredo ou autorização embutidos no grafo |

Não há mapeamento automático entre os textos livres da v1 e esse vocabulário. Uma migração futura exige revisão humana das equivalências, fontes e regras de origem/destino, além de manter IDs/revisões rastreáveis. A proposta não instala um validador ou uma API v2.

### Exemplo de instância v2 tipada

O objeto abaixo usa somente dados **hipotéticos** e estado `proposed`, sem afirmar existência, implantação ou acesso real. `satisfies` verifica o contrato em TypeScript; o valor serializado é JSON. `sources` vazio é compatível com a ausência explícita de evidências neste exemplo.

```ts
import type { KnowledgeGraphV2 } from '../graph-model';

const scope = { tenantId: 'tenant:example', classification: 'internal' } as const;
const proposed = {
  status: 'proposed', explanation: 'Exemplo hipotético; sem verificação operacional.'
} as const;
const example = {
  schemaVersion: 2, ontologyVersion: 'draft-1', snapshotId: 'example-only',
  generatedAt: '2026-10-15T00:00:00Z', ...scope,
  views: [{ id: 'demo', label: 'Exemplo hipotético' }],
  predicates: [{
    id: 'reads_from', label: 'Lê de', sourceKinds: ['system'],
    targetKinds: ['data_store'], description: 'Leitura declarada de um repositório.'
  }],
  sources: [],
  nodes: [{
    id: 'example:system', kind: 'system', label: 'Sistema de exemplo',
    domainId: 'demo', views: ['demo'], lifecycle: 'planned', ...scope,
    hierarchyParent: null, layout: { order: 0, rank: 0 }, evidence: proposed
  }, {
    id: 'example:store', kind: 'data_store', label: 'Repositório de exemplo',
    domainId: 'demo', views: ['demo'], storage: 'document', ...scope,
    hierarchyParent: 'example:system', layout: { order: 1, rank: 1 },
    evidence: proposed
  }],
  edges: [{
    id: 'example:read', predicate: 'reads_from', source: 'example:system',
    target: 'example:store', views: ['demo'], cost: 1, ...scope,
    evidence: proposed
  }]
} satisfies KnowledgeGraphV2;

const json = JSON.stringify(example); // Dados; não executar como instruções.
```

`hierarchyParent` organiza a apresentação; a aresta `reads_from` registra uma proposta semântica separada. O custo `1` é uma unidade ilustrativa de percurso, sem significado de confiança. Mesmo com o mesmo tenant e classificação, o exemplo não concede permissão de leitura ou execução.

### Validação necessária antes de adotar v2

1. Validar versão, campos discriminados e IDs únicos dentro de cada coleção. IDs de entidades e arestas são estáveis; não usar label ou posição como identidade.
2. Rejeitar endpoints, views, predicates, fontes e referências internas inexistentes. Conferir os kinds de origem/destino contra o registro do predicate.
3. Rejeitar `NaN`, infinito, custos negativos e metadados numéricos inválidos. Validar datas, hashes, linhas inteiras positivas e intervalos coerentes.
4. Conferir `hierarchyParent`: pai existente, no máximo um pai por nó, sem autorreferência e sem ciclos estruturais. Validar também o escopo autorizado do pai. Uma visita DFS com cores ou ordenação topológica pode comprovar essa floresta.
5. Detectar e reportar ciclos semânticos sem apagá-los. Relações de referência cruzada e arestas paralelas continuam permitidas; somente uma regra explícita de um predicate pode proibir determinado ciclo.
6. Validar proveniência e consistência de tenant/classificação no servidor antes da entrega do snapshot. Filtrar apenas no browser não protege dados já enviados.

### BFS e Dijkstra têm objetivos diferentes

O `BrainCore.shortestPath` existente usa BFS, considera direção quando `directed:true` e filtra a perspectiva quando `view` é informada. Minimiza **saltos**, sem pesos. O desempate atual segue a ordem de arestas do snapshot: é repetível para a mesma entrada, mas não oferece invariância sob permutação. `directed:false` permite exploração nos dois sentidos; a seta e o verbo exibidos continuam sendo os documentados.

Para um algoritmo futuro independente da ordem de entrada, ordenar cada adjacência por comparação binária de `(nextId, predicate, edgeId)`, marcar cada nó ao enfileirar e guardar o predecessor e o ID da aresta. O resultado de BFS minimiza `hops(P)=|E(P)|`; arestas de agrupamento ficam fora dessa adjacência.

Para minimizar custos, a proposta é Dijkstra sobre:

```text
cost(P) = Σ cost(e), para e ∈ E(P), com todo cost(e) finito e >= 0
```

Usar fila de prioridade, relaxamento e predecessor por aresta. Definir desempate estável por `(custo acumulado, saltos, sequência de IDs de arestas)`, com comparações binárias e atualização apenas quando essa tupla melhora. O desempate por saltos evita preferir percursos adicionais de custo zero. Peso negativo invalida a premissa e deve ser recusado antes da busca. Arestas paralelas participam individualmente; a ausência de rota retorna `found:false`. Não substituir custo por “confiança” nem escolher pesos arbitrários para aparentar certeza.

BFS ordenado e Dijkstra são evolução documentada; esta entrega mantém o algoritmo de caminhos existente. O layout ser determinístico não altera essa distinção.

## 3. Matemática da geometria e da transição

### Órbitas com anéis locais

Sejam `m` categorias, `nᵢ` entidades da categoria `i`, centro `c=(0,0)` e IDs ordenados binariamente. A disposição radial usa duas escalas: uma órbita das categorias ao redor do núcleo e anéis de entidades ao redor de cada categoria. Os centros das categorias recebem setores proporcionais ao espaço local necessário, em vez de ângulos sempre iguais.

```text
cᵢ = c + R (cos θᵢ, sin θᵢ)
φᵢⱼ = -π/2 + 2π j / k         (k entidades no anel corrente)
pᵢⱼ = cᵢ + r (cos φᵢⱼ, sin φᵢⱼ)
```

O passo entre entidades é `s=176`. Até 12 entidades, usar um anel com `r=max(164, s/[2 sin(π/max(2,nᵢ))])`. Acima disso, os raios locais são múltiplos de `s`; cada anel comporta `floor(π/asin(s/[2r]))` centros. Essa regra deriva da corda `2r sin(π/k) >= s` e limita a ocupação do anel; o código inclui uma tolerância numérica na operação de piso.

Cada grupo reserva um disco de extensão `aᵢ=max(96,r_externo+hypot(68,22))+32`, incluindo a meia diagonal do card de entidade e margem. O raio comum `R` deve satisfazer `Σ 2 asin(aᵢ/R) <= 2π`, com limite inferior `max(aᵢ)+120`; [graph-layout.js](../graph-layout.js) resolve isso por 48 passos de bisseção. Definindo `αᵢ=asin(aᵢ/R)` e `g=(2π-Σ2αᵢ)/m`, os ângulos seguem `θ₀=-π/2` e `θᵢ₊₁=θᵢ+αᵢ+αᵢ₊₁+g`.

O caso `nᵢ=0` não calcula ângulos de entidades; sem categorias, só o núcleo tem posição. Esses espaçamentos consideram as dimensões atuais dos cards, sem garantia geral de ausência de colisão de labels externos ou de arestas em dados arbitrários.

A ordem não depende da ordem do array de entrada nem da ordenação linguística da máquina. O motor compara os IDs binariamente. Entidades preservam identidade entre layouts e entre filtros; esconder uma entidade não a remove do catálogo.

### Camadas da taxonomia visual

As profundidades são `d=0` para o núcleo, `d=1` para categorias e `d=2` para entidades. Categoria focada recebe primeiro lugar; as demais permanecem como contexto e mantêm a ordem relativa estável. Não executar uma ordenação topológica sobre as relações semânticas para construir essas camadas.

Na orientação horizontal, o núcleo começa em `x=0`, categorias em `x=280` e entidades em `x=560`. Para evitar uma única coluna muito alta, cada grupo distribui suas entidades em uma grade ordenada com `rows=ceil(sqrt(nᵢ))`, `row=j mod rows`, `col=floor(j/rows)` e passo `s=176` nos dois eixos:

```text
xᵢⱼ = 560 + col·s
yᵢⱼ = centro_da_faixaᵢ + (row - (rows-1)/2)·s
altura_da_faixaᵢ = max(144, (rows-1)·s + 144)
```

As faixas são separadas por 64 unidades; a categoria ocupa o centro da faixa, e o núcleo fica no centro vertical do conjunto. Há três profundidades **lógicas**; entidades adicionais podem ocupar colunas à direita da posição inicial do terceiro nível. A orientação vertical transpõe todas as coordenadas:

```text
p_horizontal = (x, y)
p_vertical   = (y, x)
```

Os espaços são parâmetros visuais do motor. Focar uma categoria reorganiza essa taxonomia; não cria uma dependência nem filtra automaticamente as relações de outras categorias. A apresentação continua compatível com ciclos e referências cruzadas do conhecimento.

### Transição interrompível de 650 ms

Para cada ID presente na cena, obter posição inicial `p₀` do **último frame desenhado**, destino `p₁` do layout e tempo normalizado `t`:

```text
t = clamp((agora - início) / 650 ms, 0, 1)
e(t) = t²(3 - 2t)
p(t) = (1 - e(t)) p₀ + e(t) p₁
```

Esse smoothstep tem velocidade nula nas extremidades. A interpolação é cartesiana; não interpolar índices de nós nem ângulos que possam atravessar a descontinuidade de `2π`. Um clique durante a animação cancela o agendamento anterior e usa as posições correntes como novo `p₀`. Reutilizar os elementos por ID conserva a continuidade de seleção/foco.

Em cada frame, recalcular caminhos, marcadores e labels de arestas a partir das **mesmas posições** usadas nos nós. Uma relação continua orientada de `source` para `target`. Curvas de arestas paralelas precisam deslocamentos estáveis por ID para permitir distinguir conexões; o offset é apresentação, nunca um endpoint diferente. Guias e links de agrupamento também acompanham a geometria corrente.

A câmera representa o `viewBox=(x,y,width,height)` do SVG. Na troca de layout, cada um desses quatro componentes segue `v(t)=(1-e(t))v₀+e(t)v₁`, usando o mesmo progresso suavizado entregue por `onFrame`. O panorama inicial considera o conjunto projetado; ao focar uma categoria nas camadas, o enquadramento automático usa somente a categoria e suas entidades visíveis. As outras categorias continuam na cena e podem ser alcançadas por arraste ou pelo controle de categoria.

Enquadrar calcula limites com margem, preserva a proporção da superfície e mantém dimensões positivas. O botão **Enquadrar** considera novamente todo o conjunto, em vez de apenas o ramo focado. No foco automático, o limite de escala é `12/11`: labels SVG de 12 unidades conservam tamanho projetado de pelo menos 11 pixels CSS nas dimensões de superfície usadas pelo cálculo. Se o ramo exceder a área legível, centrar a categoria com deslocamento de 280 unidades no sentido da profundidade e explorar o restante por arraste, zoom ou lista. Isso preserva legibilidade à custa de não mostrar necessariamente todo o ramo de uma vez.

Pan e zoom interrompem o acompanhamento automático e modificam a câmera, sem alterar coordenadas canônicas do catálogo. O panorama radial inicial e **Enquadrar** ajustam todos os pontos retidos à superfície, inclusive no celular; em um panorama denso, labels podem ficar pequenos. O controle **Foco de categoria**, fora do SVG e em tamanho normal, permite aproximar um ramo sem localizar seu rótulo no mapa. Somente o foco automático aplica o limite de escala `12/11`. A avaliação visual dessas regras precisa ocorrer em navegador real.

Com `prefers-reduced-motion: reduce`, aplicar o destino sem o percurso animado. Ao navegar, desconectar o SVG ou chamar `dispose()`, cancelar o frame pendente e impedir novas escritas na árvore removida. A geometria final e as fontes disponíveis devem ser as mesmas com ou sem animação.

## 4. Frontend funcional e operação local

O explorador usa os controles de Órbitas, Camadas e Lista, orientação horizontal/vertical, categoria, voltar ao núcleo, zoom e enquadramento. Categoria clicável ou escolhida no controle aciona foco de camadas e aproxima sua hierarquia; entidade e relação mantêm o inspector e a fonte original. Os filtros existentes determinam o subconjunto antes da projeção. A lista é uma forma equivalente de chegar às entidades e relações, inclusive quando o mapa está denso.

Em telas móveis, a entrada padrão continua sendo Lista, salvo modo explícito na rota. A escolha de mapa/lista é persistida. Encontrar caminho limpa o foco de categoria e os filtros de exploração para exibir o percurso entre domínios na perspectiva atual; a busca continua usando somente as relações semânticas registradas.

Aplicar os tokens de [DESIGN.md](../DESIGN.md), foco visível, labels de controles e alvos de toque. Enter/Espaço ativam itens; Escape retorna ao contexto de núcleo. Status anunciável deve informar contagens e mudanças; a legenda distingue relação documental com seta de agrupamento sem seta. Seleção oculta por filtro deve ser reconciliada, e zero resultados ou falha de layout precisam de mensagem utilizável com acesso à lista/filtros.

Na raiz do repositório, usar o script já existente:

```powershell
python dashboard/serve.py --port 8847
# Ou, com o ambiente local do projeto:
.\.venv\Scripts\python.exe dashboard\serve.py --port 8847
```

Abrir [o grafo na perspectiva Ontologia](http://127.0.0.1:8847/#page=graph&view=ontology). Usar apenas um dos comandos; interromper o servidor local com Ctrl+C. O script escuta em loopback e também conserva suas rotas locais existentes. A visualização do snapshot não depende de iniciar BFF, Qdrant, Ollama ou Docker. Nenhum desses serviços é iniciado por esta documentação.

### Ações e CLI: limite de confiança

Não foi implementada execução CLI a partir de nós ou arestas. Conteúdo documental, labels, `actionRef`, parâmetros, IDs de tenant e classificação são entrada não confiável. Uma relação como `governed_by` descreve conhecimento; não concede autoridade para executar uma ferramenta.

Uma extensão futura pode enviar `ActionIntent` com `actionRef`, `targetId`, `snapshotId`, parâmetros estruturados e chave de idempotência. O servidor autentica a identidade, carrega o alvo e a ação autorizados, valida o schema, aplica isolamento por tenant/classificação e nega por padrão. Resolve `actionRef` para um `commandRef` de registro confiável; nunca aceita texto de shell do grafo.

O comando resolvido teria formato estruturado, por exemplo conceitual:

```json
{
  "commandRef": "catalog.validate",
  "argv": ["--snapshot", "snapshot-autorizado"],
  "targetId": "entidade-autorizada",
  "snapshotId": "snapshot-autorizado",
  "taskId": "tarefa-autenticada"
}
```

Esse exemplo não registra nem disponibiliza um comando. Um adapter futuro resolve executável, diretório, argumentos fixos, timeout e limites de saída no servidor; valida argumentos e usa processo com vetor de argumentos e shell desativado. Segredos são resolvidos fora do grafo. Aprovação humana, quando exigida pela política, fica vinculada à intenção/versão/hash exatos; nenhum booleano fornecido pelo cliente basta para aprovar.

Toda chamada das ferramentas da plataforma deve continuar passando por [`core/broker.py`](../../core/broker.py), cuja interface existente é `call(identity, tool, args, task_id, *, approved=False, ...)`. O broker consulta [`core/policy/`](../../core/policy/), recusa ou escala conforme o veredito e registra rastros. A allowlist permanece em `core/policy/`, sem cópia no dashboard. Uma ferramenta ou rota de execução v2 precisaria ser registrada e validada nesse fluxo; o exemplo de `commandRef` não acrescenta suporte ao broker atual.

### Verificação e limites

Comandos do repositório para validação integrada:

```powershell
node --test --test-isolation=none dashboard/tests/*.test.cjs
.\.venv\Scripts\python.exe dashboard\tests\test_build_graph.py
```

Verificar projeção imutável, determinismo sob permutação, posições finitas, foco/orientação, ciclos e desconexão, interrupção de animação, movimento reduzido e descarte. No navegador, percorrer alternância de layouts, cliques rápidos, teclado, fontes, zero resultados, navegação e os breakpoints do design system. Os comandos aqui são instruções de reprodução; o relatório da entrega deve registrar os resultados efetivamente observados.

A especificação registra um baseline anterior de 116/119 testes JS, com falhas em `generated snapshot validates and environments have distinct sources`, `modal_semantics` e `hardcoded_values`. Comparar o resultado atual com esse baseline, sem atribuir aprovação a uma suíte com falhas e sem alterar módulos alheios apenas para tornar o relatório verde. O catálogo v1, o contrato v2 proposto e uma futura integração de execução permanecem etapas distintas.

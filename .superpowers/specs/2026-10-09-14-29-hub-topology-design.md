# Passo 2: mapa operacional do Hub

Status: desenho aprovado por Hugo; autorização para spec, plano e execução concedida em 2026-10-09 ("considere tudo aprovado").

## Objetivo e alcance

Mostrar a topologia interna do Hub em produção e homologação na tela existente de Observabilidade. O dono autorizou execução em ciclos multiagentes. Somente leitura dos dados já coletados: sem sistemas externos, novos coletores, execução de testes pela tela, Neo4j, alteração no Hub, deploy, serviços ou escrita remota.

O vault e as decisões ADR-004/005 permanecem intactos. Este passo acrescenta uma projeção visual dos contratos existentes; não muda a arquitetura de coleta nem registra novos fatos de implantação.

## Desenho escolhido e alternativas

Escolhida: mapa dentro de Observabilidade, duas faixas por ambiente, junto aos indicadores já existentes. Alternativas: nova perspectiva no Grafo documental (mistura conhecimento e saúde) ou página própria (navegação/manutenção adicionais). Topologia permanece visível com BFF indisponível; estados sem observação são desconhecidos.

Os quatro aspectos de cada Hub: process (Hub / processo PM2), internal (HTTP interno), external (HTTP público), database (SQLite / fila). Endpoints são caminhos de acesso ao mesmo processo, não serviços independentes. Worker e emissão são atributos/políticas, não nós separados. Arestas dirigidas: internal -> process e external -> process (atendido pelo Hub); process -> database (usa SQLite). Fontes locais: hub-logistico/server.js:25, hub-logistico/health.js:19 e hub-logistico/scripts/post-deploy-check.js:61. Nenhuma aresta entre ambientes.

Ao selecionar um aspecto: motivo do estado, data/idade, verificações, última tentativa, depende de e quem depende dele, fonte das relações. Mapa com nós acionáveis por teclado, lista equivalente e rótulos textuais; cor nunca é a única indicação. Desktop com dois ambientes lado a lado; celular empilha.

## Contrato do modelo puro

Novo dashboard/hub-topology.js: UMD sem dependências, window.BrainHubTopology e module.exports.

- project(environment, latest, nowSeconds = Date.now()/1000) -> model.
- dependencies(model, nodeId) -> {dependsOn: node[], dependents: node[]} (diretas, dirigidas).
- environment permitido: production | hml. latest é o envelope atual de /v1/observability; nenhuma busca no modelo.
- model: {environment, nodes, edges, observation, collection, summary}.
- node: {id, label, status, reason, checks, observedAt, ageSeconds}; status: green | yellow | red | unknown; checks é uma lista de {label, value, expected, ok}, usando somente indicadores agregados conhecidos e sem payload.
- edges: {source, target, relation, sourceRef}.
- observation: null ou {id, collectedAt, source}. collection: {status, lastAttemptAt}; status ok | failed | missing. summary: {status, reason}.
- IDs de aspectos são locais ao ambiente; a UI usa environment para IDs DOM únicos.

## Regras de estado

Verde exige observação válida, recente e sinais do aspecto presentes/normais nas DUAS amostras. Nunca usar report.ok sozinho para colorir todos os aspectos. Sinal ausente, tipo inválido, ambiente divergente do envelope ou data inválida não é sucesso. Divergência real de ambiente/revisão/política reportada por um endpoint deve aparecer como verificação falha, com motivo explícito.

Vermelho significa verificação diretamente falhou na janela, não necessariamente queda: processo observado fora de online; reinício entre amostras; HTTP error/unavailable ou resposta incompatível; banco não legível; erros terminais/pendências logísticas/falhas de fila crescentes quando atribuíveis aos campos existentes. Campo PM2 ausente significa desconhecido, não queda.

Amarelo significa alerta identificado (como rate limiting), avaliação agregada com causa insuficiente, dado vencido ou coleta atual indisponível. report.ok=false com sinais normais não transforma todos os nós em vermelho; warning_count>0 não é verde agregado. Expor o motivo e preservar diferença entre saúde, política e observação.

Cinza/unknown: nunca coletado ou evidência insuficiente. Não atribuir estado do Hub a banco, endpoint ou ambiente que não foi observado.

Coleta nominal já existente: 60 s após a rodada sequencial. Vencimento: idade >180 s, não >=180. Calcular envelhecimento também no navegador para uma coleta em cache não ficar verde indefinidamente. Validar timestamps e, quando at da amostra estiver presente, considerar sua idade, sem tratar amostra antiga recém-recebida como atual.

Falha de coleta é independente da saúde. Conservar a última observação, horário e último estado; sinalizar que não comprova saúde atual. Estado observado antigo vermelho passa a histórico com amarelo, não continua anunciando falha atual. Sem dado anterior continua unknown. Não persistir relatórios em localStorage.

Política hml: workerEnabled=false e emissionEnabled=false são esperados. Produção espera workerEnabled=true e emissionEnabled=true conforme o coletor. Revisão esperada vem de expected_sha do relatório validado; nunca substituir automaticamente pela revisão recebida.

Latência está explicitamente fora deste ciclo aprovado: não há latência do Hub no contrato. duration_ms do MCP inclui transporte e coleta e não será apresentado como latência HTTP.

## Interface e atualização

Novo dashboard/hub-topology-ui.js: renderiza um model com utilitários existentes U.el/U.button, sem innerHTML. API render(model, U, options={}) -> elemento DOM. Detalhes e seleção permanecem locais ao mapa, sem buscar no grafo geral. Lista e mapa representam os mesmos quatro aspectos e dependências.

Integração em observability-ui.js: manter mapas estáticos mesmo offline; consultar os dois ambientes independentemente, para uma falha não apagar o outro. Preservar última resposta válida em memória do render. Poll da UI mantém frequência atual de 15 s, coletor não muda. dispose impede timers e respostas tardias de reativarem render antigo; cancelar/ignorar respostas de navegação anterior. Mensagens de erro fixas, sem inserir texto arbitrário do servidor.

Preservar indicadores/histórico existentes quando disponíveis. Nova visualização é aditiva e não altera o grafo documental, seus hashes, vault ou schema existente. Carregar novos scripts antes de observability-ui; estilos em live.css.

## Verificação e segurança

TDD para modelo e UI: executar e observar falha antes de implementar; registrar RED/GREEN. Testes de limites 180/181 s, ambos os ambientes, sinais ausentes/inválidos, duas amostras, políticas hml, falha real seguida de perda de coleta, cache vencido, um ambiente indisponível, teclado/dependências e descarte de respostas tardias. Testes não reproduzem somente o texto do código.

A suíte antiga tem teste de integração Qdrant com possível criação de coleção. Isolar no próprio teste usando QdrantClient em memória, sem iniciar daemon nem mudar produto, para que a suíte completa rode em clone limpo sem .env ou variáveis do projeto. Testar a criação/consulta reais do cliente local em memória; não trocar asserts por skips/mocks vazios.

Revisão final independente; corrigir Critical/Important com regressão RED/GREEN. Gates: Python completo indicado no CLAUDE, Node completo, builder tests e cli.py evidence --lint com armazenamento temporário quando necessário. Clone limpo local via --no-local, sem .env/.runtime nem variáveis de configuração; não usar o vault do checkout original.

Nunca escrever credenciais, commitar .env/.runtime/.brain_hashes.json, modificar env, iniciar serviços reais, escrever em produção/homologação ou executar push/merge/remoto. Commits locais em português (Conventional Commits), branch temática. PR será preparado com causa raiz/correção/evidências; publicação requer ordem específica de Hugo.

---
type: system
status: active
date: 2026-10-09
---
# Auditoria 360 do frontend do Second Brain

Data de referência: **08/10/2026**, America/Sao_Paulo. Escopo: dashboard local em `C:\KIOSK\second-brain\dashboard`, sua geração de dados e os contratos já existentes de consulta ao conhecimento. O usuário escolheu plataformas web de agentes e RAG como recorte para selecionar referências no GitHub.

Esta é uma **auditoria documental de baseline**, feita antes das waves de melhoria. O score de **37/100 é provisório**: resulta da inspeção de funções e limitações do código, e não de pesquisa com usuários, medição Lighthouse ou ensaio completo das três plataformas concorrentes. Ele não demonstra superioridade sobre outro produto. As recomendações de arquitetura são propostas; não equivalem a serviços implantados.

## 1. Baseline e evidência verificável

O frontend inspecionado era uma aplicação estática sem framework ou dependências JavaScript externas: `index.html`, `style.css`, `app.js` e um bundle `graph-data.js` gerado por `build_graph.py`. O catálogo continha **19 nós, 16 relações, 3 vistas e 8 documentos**. As vistas tinham 6 nós de fluxo logístico, 6 de infraestrutura e 7 de entidades/contratos.

Os hashes SHA256 registram os arquivos de origem auditados; as linhas citadas neste documento se referem a esse baseline e podem mudar após as waves.

| Arquivo de origem | SHA256 |
|---|---|
| `index.html` | `d9cc1dec3c707fa2b398a1f039b355994aec6bd1755a06bdc68163b3fc19f142` |
| `app.js` | `c5b06a9986b6e1887898d07a626c0b66542c92bed1c2e81a12adcb5f851a3aa4` |
| `style.css` | `30bce6251cd507cbc820e48944d0550b4d5079f361da314e2a1aeb5d7fd79b52` |
| `graph-catalog.json` | `c42bc150fcb9dc1fc66458b27be2065714bfdee3c778014d2059d239217459d1` |
| `build_graph.py` | `81958ba671166264c213606b624bac8f7d1c1cc17976a139f9fb940e511ffdf3` |

### Bases que vale preservar

- Posições determinísticas tornam o mapa pequeno previsível e evitam uma simulação que reorganize nós durante a leitura.
- Documentos são inseridos com `textContent`, sem interpretação de HTML do vault (`app.js:85–121`). O build escapa `<` ao gerar o bundle (`build_graph.py:38–39`).
- O build verifica a contenção de caminhos no vault, existência de arquivos, referências de nós e participação nas vistas (`build_graph.py:17–35`).
- Os controles têm labels e os nós aceitam Enter/Espaço (`index.html:13–19`, `app.js:64–79`).
- O inspector oferece tipo, domínio, evidência, documento e relações. Fontes de produção e homologação já são distintas.
- Implementado, parcial, proposto e relatado são estados separados. Essa distinção é útil e deve ganhar significado temporal e ambiental mais preciso.

## 2. Pessoas e jornadas

As personas abaixo são hipóteses de trabalho derivadas do uso solicitado; ainda precisam ser validadas com usuários reais.

| Pessoa | Pergunta ou tarefa | Resultado esperado |
|---|---|---|
| Responsável por engenharia | “O que está comprovado em produção e o que continua pendente?” | Resumo com ambiente, validade, fonte, decisões e demandas; sem exigir leitura de todo o grafo. |
| Operação/suporte | “Qual regra explica este comportamento do pedido?” | Encontrar sistema/regra, seguir relações e abrir a evidência específica em poucos passos. |
| Analista de conhecimento | “Quais fontes sustentam esta entidade? O que está contraditório ou desatualizado?” | Provenance por afirmação/relação, datas, lacunas e trilha de revisão. |
| Desenvolvedor/revisor | “Qual contrato ou adapter preciso alterar?” | Navegar entidade → contrato → adapter → sistema → fonte, preservando contexto e histórico. |
| Operador de agentes, na futura plataforma | “O que cada agente executou, com quais ferramentas e por que falhou?” | Execução persistida, timeline, dependências, fontes utilizadas e artefatos; cancelamento e retomada claros. |

Roteiros para comparar o baseline, cada wave e as referências externas:

1. Abrir a aplicação e localizar o comportamento de produção, sem conhecer o nome exato do documento.
2. Buscar um termo com acento, filtrar evidência e abrir uma entidade de outra vista.
3. Seguir uma relação, abrir sua fonte e retornar à posição e seleção anteriores.
4. Localizar uma DEM específica e a decisão associada, sem percorrer o backlog inteiro.
5. Ler uma tabela, lista e bloco de código no documento usando teclado e tela estreita.
6. Formular uma pergunta de conhecimento e inspecionar as fontes/caminhos realmente recuperados.
7. Distinguir fatos implementados, evidência antiga e contratos ainda propostos.
8. Na futura execução real de agentes, acompanhar, cancelar e reabrir uma tarefa preservando seu histórico.

Conclusão de tarefa, erros, passos, tempo e satisfação podem ser medidos com esse roteiro. Qualquer meta de tempo definida nas waves é um **critério de aceite a medir**, não resultado já observado.

## 3. Problemas do baseline

| ID | Prioridade | Problema e efeito | Evidência do baseline |
|---|---|---|---|
| UX-01 | P1 | Navegar por relação não reconcilia busca/evidência; o inspector pode abrir um nó oculto no grafo. | `app.js:16–21`, `:147–149` |
| UX-02 | P1 | Trocar de vista com zero resultados só renderiza o mapa e mantém o documento anterior. | `app.js:164–167` |
| A11Y-01 | P1 | A seleção recria o SVG inteiro e remove o elemento com foco, interrompendo o uso do teclado. | `app.js:31`, `:154` |
| MOB-01 | P1 | O layout empilha os painéis, mas miniaturiza o mapa inteiro; seus textos ficam ilegíveis no celular. | `index.html:19`, `style.css:450–462` |
| DATA-01 | P1 | Hub, HML, job e intenção de emissão seguem rotulados como `local`, traduzido como “sem deploy”, embora o deploy tenha sido concluído na tarefa anterior. | `graph-catalog.json:71`, `:163`, `:236`, `:250`; `app.js:7` |
| SEARCH-01 | P2 | Pesquisa apenas label/tipo/ID/DEM dentro da vista atual; ignora documentos, descrições e relações, sem normalização de acentos. | `app.js:16–21` |
| SEARCH-02 | P2 | Digitar seleciona automaticamente o primeiro resultado; a fonte muda sem uma escolha explícita. | `app.js:172–184` |
| GRAPH-01 | P2 | Zoom depende da roda; não existem pan, botões de zoom, atalhos de enquadramento ou alternativa em lista. | `app.js:188–197`, `index.html:20` |
| DOC-01 | P2 | Markdown é convertido parcialmente: links ficam literais, listas viram parágrafos e tabelas viram uma sequência de `pre`. | `app.js:94–116` |
| DOC-02 | P2 | Todos os botões de DEM abrem o mesmo backlog inteiro sem localizar a demanda selecionada. | `app.js:133–136` |
| STATE-01 | P2 | Sem URL de estado, histórico, favoritos ou restauração de seleção; todo início abre o hub. | `app.js:8`, `:198–199` |
| A11Y-02 | P2 | Metadados pequenos têm contraste insuficiente. Labels, controles e badges também precisam de tamanho e alvo de toque adequados. | `style.css:15`, `:97`, `:287`, `:302`, `:317` |
| STATE-02 | P2 | Catálogo ausente, vistas vazias ou remoção do nó `hub` podem interromper o bootstrap sem mensagem de recuperação. | `app.js:3`, `:8`, `:199` |
| SCALE-01 | P3 | Cards de 180×84 e coordenadas manuais não escalam bem; procura de nós durante edges é linear e o SVG é reconstruído em cada interação. | `app.js:31`, `:42–43`, `:64–73` |
| CSS-01 | P3 | CSS tem regras antigas, seletor de canvas inexistente e overrides repetidos, aumentando o custo de manutenção. | `style.css:199`, `:438–462` |

Medições derivadas diretamente dos valores do código:

- Contraste de `#64748b` em `#111724`: **3,77:1**; em `#0d121c`: **3,94:1**. Esses valores não chegam ao alvo de 4,5:1 para texto pequeno.
- O SVG tem largura lógica de 1180. Ajustá-lo em 375px reduz uma label de 15px para aproximadamente **4,77px**, e um badge de 9px para **2,86px**. É uma consequência geométrica do fit do SVG, não um teste de percepção com usuários.

## 4. Rubrica congelada para evolução

| Dimensão | Peso | Baseline provisório | Justificativa |
|---|---:|---:|---|
| Navegação e orientação | 14 | 5 | Vistas e relações existem; falta histórico/deep link e há inconsistência de seleção. |
| Grafo legível e explorável | 18 | 10 | Mapa pequeno, estável, contagens e destaque; sem pan, foco progressivo ou lista. |
| Leitura e provenance | 16 | 8 | Fonte segura e evidência textual; sem âncoras, citações específicas ou formatação semântica completa. |
| Pesquisa e descoberta | 12 | 4 | Busca de metadados e filtro; sem busca global por conteúdo e snippets. |
| Acessibilidade | 14 | 4 | Labels e Enter/Espaço; foco perdido, contraste e controles insuficientes. |
| Mobile | 10 | 2 | Painéis empilhados; mapa miniaturizado e ilegível. |
| Persistência e recuperação | 8 | 0 | Ausentes. |
| Estados e feedback | 8 | 4 | Contagens, vazio e fonte ausente; bootstrap e contexto sem recuperação robusta. |
| **Total** | **100** | **37** | **Avaliação documental provisória.** |

Regras de pontuação:

- Usar os mesmos pesos, tarefas e evidências para todos os candidatos. Registrar versão, data, configuração e limitações de acesso.
- Reconhecer funcionalidade apenas quando implementada e demonstrável. Recomendação arquitetural ou botão decorativo não gera ponto de execução.
- Não pontuar “GraphRAG real” quando houver apenas busca textual, mapa manual ou expansão determinística local sem integração com recuperação/geração.
- Não pontuar “multiagentes reais” por uma timeline simulada. A execução precisa existir, produzir eventos e persistir seus resultados.
- Estrelas selecionam referências, mas não representam qualidade de UX. Registrar o recorte e a contagem consultada na data da pesquisa.
- Avaliação documental pode sustentar comparação documental. Para declarar superioridade de usabilidade, executar os mesmos roteiros nos produtos e publicar os resultados comparáveis.
- Se a wave entrega frontend local, concluir sobre esse recorte. Avaliar maturidade de backend, GraphRAG e execução de agentes separadamente, sem somar capacidade apenas planejada.

## 5. Arquitetura de informação recomendada

O grafo é uma ferramenta de exploração, e não deve ser o único ponto de entrada. A estrutura recomendada é:

| Área | Conteúdo e tarefa |
|---|---|
| Visão geral | Situação da base, fontes recentes, lacunas, ambientes, decisões e acessos frequentes. |
| Conhecimento | Biblioteca pesquisável, documentos e entidades; reader com fonte, seções e relações. |
| Grafo | Vistas por objetivo, comunidades, vizinhança e caminhos; alternância entre mapa e lista. |
| Consulta | Recuperação com fontes/chunks/caminhos visíveis; resposta somente quando o motor estiver conectado. |
| Execuções | Agentes, etapas, ferramentas, eventos, falhas e artefatos persistidos; estado operacional real. |
| Configuração | Serviços locais, versões, permissões, preferências e saúde das conexões. |

No inspector, usar resumo inicial curto e abas **Resumo / Fonte / Relações**. Exibir ambiente, implementação, evidência, validade e documento separadamente. Ações comuns devem ter nomes orientados à tarefa: abrir fonte, seguir relação, ver demanda, copiar referência e voltar.

## 6. Design, acessibilidade e mobile

Definir tokens únicos de espaçamento, tipografia, cores, radius e estados; eliminar overrides repetidos. Preservar contraste do texto principal e elevar contraste de metadados. Cor de domínio deve ser complementar ao label textual. Tracejado não basta para comunicar evidência: mostrar estado por texto e legenda.

Oferecer focus-visible consistente, link de pular para conteúdo, sequência lógica de Tab, preservação de foco após atualização, Escape para fechar contexto e labels para controles. Contagens e estados devem usar live regions com moderação; não anunciar todos os eventos de movimentação do mapa. Respeitar `prefers-reduced-motion`.

No celular, priorizar resultados em lista. Abrir o grafo em espaço navegável com cards e textos legíveis, zoom/pan e retorno evidente à lista. O inspector deve caber na tela sem criar múltiplas áreas de scroll difíceis de perceber. Usar controles com alvos de aproximadamente 44px como objetivo de projeto e verificar o reflow em 375px, 768px e desktop.

O reader deve ter headings com IDs estáveis, índice de seções, listas reais, tabelas com headers, código copiável e URLs com política explícita. Fontes continuam dados: nunca interpretar HTML ou instruções do vault como código.

## 7. Dados, GraphRAG e agentes

Separar contratos de dados:

- `Entity`: ID estável, tipo, label, aliases, domínio, ambiente e atributos.
- `Relationship`: origem/destino, predicado, direção e referências a claims/fontes.
- `SourceDocument`: caminho controlado, título, categoria, hash, versão e data de indexação.
- `Claim`: afirmação, trecho/seção, fonte, status da evidência, validade e revisão.
- `Run`, `AgentStep`, `ToolInvocation`, `Artifact`: registros operacionais de execução; não misturar com o catálogo de fatos.

O catálogo precisa de schema que rejeite IDs de arestas duplicados, enums desconhecidos, coordenadas inválidas, referências ausentes e timestamps malformados. Mostrar última geração e versão na UI; o hash guardado no build deve ser acessível quando ajuda a conferir provenance.

O RAG existente é vetorial: `core/retriever.py:12–44` consulta Qdrant com embeddings Ollama. O grafo é manual e não participa desse retrieval. A evolução para GraphRAG deve localizar chunks, ligar chunks a entidades/claims, expandir relações relevantes e retornar a trilha usada. Medir precisão das fontes, cobertura, contradições, abstenção e custos; não somente aparência da resposta.

O contrato MCP `search_knowledge_base` atualmente retorna metadados das fontes (`mcp_servers/brain_mcp.py:10–17`). A UI futura precisa de identificador de chunk, conteúdo/trecho, seção, hash e vínculo navegável à fonte. O browser não deve falar diretamente com MCPs que guardam credenciais.

## 8. Desempenho, segurança e observabilidade

Para o catálogo pequeno, SVG e vanilla JS são adequados. Antes de trocar de stack, separar funções de estado, seleção, dados, câmera, reader e adapters. Indexar nós por ID e relações por origem/destino; buscar documentos separadamente e atualizar apenas elementos afetados. Testar com fixtures maiores antes de afirmar escalabilidade. Considerar virtualização da lista e carregamento de fontes sob demanda quando o volume justificar.

No futuro backend local: endpoints definidos, validação por schema, eventos SSE, armazenamento de execuções e idempotência. Estados de run devem incluir `queued`, `running`, `waiting`, `completed`, `failed` e `cancelled`. Cancelamento, timeout e retomada precisam ser verificáveis.

Prioridades de segurança antes de qualquer publicação:

1. Servir somente assets aprovados, nunca o diretório completo do Second Brain. O bundle atual contém o texto integral das fontes selecionadas.
2. Credenciais e ferramentas remotas permanecem no backend; autorização por usuário/agente/ferramenta e auditoria de ações.
3. Resolver e validar caminhos no backend. `get_system_architecture` constrói caminho diretamente de `system_name` (`brain_mcp.py:37–42`) e precisa de allowlist/contenção antes de exposição web.
4. Texto recuperado é conteúdo não confiável. `core/retriever.py:62–70` concatena contexto ao prompt; definir fronteiras de confiança e impedir que instruções das fontes concedam ferramentas/permissões.
5. Para links e Markdown, admitir apenas protocolos definidos; bloquear JavaScript/data/file; usar `noopener noreferrer`; não carregar imagens remotas sem política explícita.
6. Registrar falhas e degradação sem exibir segredos, prompts sensíveis ou dados de cliente de forma indiscriminada.

Métricas úteis: build/version freshness, erro de carregamento, consultas sem resultado, consulta sem evidência, falhas de serviço, tempo de retrieval, tempo de render e eventos de execução. O painel deve apresentar “desconectado”, “indisponível” ou “demonstração” com precisão; ausência de backend não pode aparecer como execução bem-sucedida.

## 9. Waves e critérios de aceite

### Wave 1 — Orientação, reader e acessibilidade

Entregar navegação clara, busca global com resultados explícitos, alternativa em lista, inspector organizado, Markdown seguro/semântico, seções por URL e preferências locais versionadas. Corrigir UX-01, UX-02, A11Y-01, MOB-01 e contraste. Incluir zoom por botões e recuperação de catálogo inválido.

Aceite: busca → seleção → relação → voltar mantém contexto; filtros não produzem inspector stale; teclado preserva foco; 375px permite ler e operar a lista; conteúdo malicioso não cria script/imagem executável; links perigosos são recusados; recarregar restaura estado válido sem falhar com IDs removidos.

### Wave 2 — Grafo progressivo e provenance confiável

Entregar foco em vizinhança de 1–2 saltos, vista por domínio/objetivo, filtros de tipo/ambiente, breadcrumb, caminho entre entidades e legenda textual. Separar evidência, validade e implantação. Abrir fonte específica da relação/DEM.

Aceite: schema rejeita relações órfãs; seleção está visível ou recebe aviso claro; caminho é reprodutível; fonte exibida corresponde à relação; prod/HML não compartilham significado indevido; informações sem revalidação permanecem marcadas com data e limite.

### Wave 3 — Recuperação local rastreável

Entregar recuperação lexical/vetorial com expansão de relações e fontes por afirmação. Exibir o modo real de operação. Se apenas recuperação determinística estiver disponível, nomeá-la assim. Registrar query, filtros, chunks, scores, catálogo e caminhos.

Aceite: resultados reproduzíveis em perguntas conhecidas; sem evidência produz abstenção; fontes conflitantes não são fundidas silenciosamente; documento obsoleto é identificado; nenhuma função simulada recebe pontuação de GraphRAG/LLM real.

### Wave 4 — Execuções reais e prontidão web

Entregar contratos/API local, armazenamento e eventos de execuções, timeline, artefatos, cancelamento e autorização por ferramenta. Só depois considerar publicação multiusuário, com isolamento de dados e credenciais.

Aceite: criar/cancelar/reabrir tarefa preserva timeline; falha é falha; ferramenta negada permanece negada; retomada não duplica efeitos; segredos não aparecem no frontend; indisponibilidade de modelo/MCP fica evidente. Publicação não faz parte das waves locais autorizadas.

## 10. Riscos e limites da conclusão

- **Score otimizado para si mesmo:** congelar rubrica e revisar por agente/revisor que não implementou a UI. Não alterar pesos para ultrapassar concorrentes.
- **Comparação desigual:** referências podem exigir login, setup ou serviços inacessíveis. Marcar pontos sem evidência como não verificados e não como zero arbitrário.
- **Escopo confundido:** frontend local, GraphRAG e plataforma multiagente têm maturidades distintas. Separar demonstração, recuperação e execução operacional.
- **Catálogo desatualizado:** manualidade exige revisão de claims e ambientes; atualizar documentos não atualiza automaticamente o estado semântico das entidades.
- **Expansão visual sem escala:** widgets extras podem aumentar densidade. Cada nova área precisa responder a uma jornada e ter progressive disclosure.
- **Código e documentos sensíveis:** um futuro servidor HTTP aumenta exposição. Validar rotas, diretório servido e controles antes de disponibilizar a terceiros.
- **Falsa promessa de conclusão:** resultado local superior numa rubrica documental não significa produto universalmente melhor, seguro ou pronto para produção.

Esta auditoria estabelece baseline, problemas e aceites. O relatório final de cada wave deve distinguir implementado, testado, observado no navegador e ainda proposto, com evidências e limites explícitos.

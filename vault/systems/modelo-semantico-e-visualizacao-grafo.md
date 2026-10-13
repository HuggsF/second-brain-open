---
type: system
status: active
date: 2026-10-09
---
# Modelo semântico e visualização do grafo

Data: 2026-10-08
Status: catálogo e dashboard implementados localmente; domínio em evolução.
Escopo: organização do Second Brain e dashboard local. Adapters, domínio e persistência devem refletir relações reais; sua existência não é pré-requisito para um layout legível.

## Diagnóstico do dashboard anterior

dashboard/index.html carrega app.js. Este define onze nós, relações e HTML dos documentos diretamente no código; o painel mostra docContent, sem buscar o arquivo indicado em docPath. Consequentemente, atualizar o vault não atualiza automaticamente o dashboard.
A inicialização distribui nós em círculo; a simulação usa repulsão, molas e atração de todos os nós ao mesmo centro. Não há ancoragem por domínio nem prevenção explícita de colisão entre rótulos. Regras e gaps aparecem como etapas entre sistemas; a relação duplicidade_fix -> jt representa uma regra como participante operacional.
A inspeção foi do código, sem validação visual no navegador nesta revisão.

## Entidades e relações canônicas propostas

Identidade estável, nome, aliases e tipo devem ser separados de domínio, ambiente e estado de implementação.
Tipos: Sistema, Adapter, Contrato, EntidadeDeDominio, Regra, Ambiente, Banco, Demanda e Evidencia.
Entidades de domínio iniciais: Pedido, Loja, Job, Remessa, Volume, Etiqueta, Rastreio e OrdemDeSeparacao. Remessa/Volume/OrdemDeSeparacao ainda dependem de definição operacional; nomes não significam contratos implementados.
Vocabulário de relações: recebe_evento_de, consulta, implementa, traduz, possui, seleciona, emite, atualiza, hospeda, utiliza, afeta e validado_por.
AdapterBling traduz resposta do Bling em PedidoUniversal; AdapterJT traduz intenção de emissão para J&T; AdapterCorpem deverá traduzir OrdemDeSeparacao para Corpem. Sistemas continuam sendo sistemas, adapters são componentes, contratos descrevem dados e regras governam ações.

## Relações iniciais e proveniência

| Origem | Relação | Destino | Estado e fonte |
| --- | --- | --- | --- |
| Hub | recebe_evento_de | Bling | Implementado: server.js, rota /webhook/bling |
| AdapterBling | traduz | PedidoUniversal | Implementado: adapters/bling.js |
| Pedido | possui | Loja | Implementado: universalOrder.store |
| Loja | seleciona | ConectorTransportadora | Implementado: engine.js, connector_id com fallback |
| Loja | sobrescreve | Remetente | Implementado: engine.js, remetente por loja |
| MotorFila | reutiliza | Rastreio | Implementado com limites: DEM-09, DEM-10, DEM-15 |
| AdapterJT | emite_em | J&T | Implementado: generateLabel; emissão externa real depende da configuração |
| Hub | envia_para | Corpem | Parcial: POST opcional com payload de exemplo |
| AdapterCorpem | implementa | ContratoWMS | Proposto: DEM-12 |
| DEM-11 | afeta | Homologacao | Achado no seed; estado remoto não confirmado |
| Shopify | encaminha_checkout_para | Yampi | Relatado no discovery; não validado por este checkout |
| Yampi | cria_pedido_em | Bling | Fluxo relatado; falhas e causas permanecem em investigação |

Toda aresta deve guardar ID, source, relation, target, source_file, source_section, código/commit quando aplicável, valid_at, ambiente e evidence_status. Distinguir observado no código, relatado pela operação, hipótese e proposto.
Não inferir pagamento/faturamento a partir de orders_queue.status ou tratar Atendido como prova de NF-e emitida.

## Vistas para leitura limpa

1. Fluxo logístico como vista inicial: Bling -> Hub -> J&T e Hub -> Corpem, com Shopify/Yampi em um contexto de entrada recolhível. Ordem visual da integração atual não define a sequência futura de picking/packing.
2. Infraestrutura separada: Actions -> SRV-API -> instâncias prod/hml -> respectivos bancos. Isso evita arestas de infraestrutura cruzando o fluxo de pedidos.
3. Modelo de domínio: Pedido -> Remessa -> Volume -> Etiqueta, com Loja e OrdemDeSeparacao; relações ainda indefinidas ficam tracejadas e identificadas como propostas.
4. Pendências como badges no sistema/aresta afetados, expandindo demandas sob demanda. DEM-08 deve anotar Yampi -> Bling, sem ocupar o caminho da integração.
5. Adapters e regras aparecem ao expandir Hub, evitando exibir detalhes de implementação na visão executiva.

## Layout e navegação

Usar posições determinísticas por camada e domínio como padrão; manter o modo livre como alternativa. Calcular rotas para ciclos/arestas de retorno, separar rótulos e respeitar a dimensão real do texto.
Mostrar apenas conexões do nó selecionado e um ou dois saltos quando solicitado. Incluir busca, filtros por tipo/ambiente/evidência, recolher grupos, enquadrar seleção e legenda compacta.
Cor representa domínio; formato ou ícone representa tipo; badge representa implementação/evidência. Verde não deve significar garantia financeira nem estado remoto sem validação.
Contagem de nós é calculada a partir da vista, eliminando onze nós fixos no HTML.

## Fonte única e recuperação de conhecimento

Gerar um manifesto do grafo a partir de um catálogo versionado do vault; validar IDs, relações e referências documentais. O dashboard lê o manifesto e os documentos reais ou conteúdo gerado do mesmo build, evitando HTML editorial duplicado em app.js.
O indexador atual extrai título/seção/categoria e armazena vetores no Qdrant; metadados semânticos e relações exigem evolução explícita de chunker, armazenamento e recuperação. Um grafo visual e o RAG vetorial atuais não constituem GraphRAG com travessia.
Atualizar Markdown, índice vetorial e manifesto são etapas distintas, cada uma com confirmação própria.

## Critérios de aceite

Reabrir o dashboard preserva organização estável; rótulos não se sobrepõem na janela alvo; seleção destaca uma vizinhança legível; filtros não deixam arestas órfãs; todas as referências levam a fontes existentes; regras/gaps não interrompem o fluxo de sistemas; propostas e integrações parciais têm identificação visível; alteração no vault chega ao painel pela geração documentada do manifesto.

## Implementação local em 2026-10-08

O diagnóstico acima descreve a versão anterior. graph-catalog.json agora define IDs, tipos, domínios, evidência e fonte das relações. build_graph.py valida IDs/vistas/arquivos e gera graph-data.js com texto e hash dos documentos reais.
Três vistas SVG com posições estáveis: fluxo, infraestrutura e entidades/contratos. Busca por nó/DEM, filtros de evidência, zoom e relações selecionáveis; gaps aparecem como badges. O painel exibe conteúdo do vault sem executar HTML.
Comando de atualização, na pasta second-brain: .venv/Scripts/python.exe dashboard/build_graph.py. Gerar novamente após editar notas ou catálogo. O dashboard funciona por arquivo local ou HTTP em localhost; sem dependências externas de runtime.
Catálogo inicial: 19 nós, 16 relações, sete fontes. Modelo curado e visual; extração automática e travessia ainda não foram adicionadas ao recuperador vetorial.

Validação visual e funcional: breakpoint de desktop e viewport estreito, três vistas, filtro de propostas (dois nós e uma relação), busca e seleção de fontes. Painel renderiza títulos, parágrafos e código como elementos DOM com textContent; HTML da fonte não é executado.

 
## Frontend Second Brain: quatro waves locais

Atualização de 08/10/2026: o diagnóstico anterior é histórico. O dashboard agora possui biblioteca de todo o vault, navegação por áreas, busca com acentos e siglas, favoritos, fontes com hash/linhas, renderer sem HTML executável, filtros de entidades/relações, vizinhança e caminhos. Posições são compactas e estáveis por perspectiva; há lista equivalente como padrão móvel.

A consulta usa texto e catálogo curado local, sem embeddings ou resposta LLM. Planos são validados/exportados, sem executar agentes. Código e implantação são dimensões separadas; prod/HML usam documentos distintos. Fontes são snapshots manuais: executar dashboard/build_graph.py e recarregar para refletir o vault. Ver [[second-brain-frontend-waves]] e [[second-brain-graphrag-multiagent]].

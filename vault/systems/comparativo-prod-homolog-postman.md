# Comparativo do fluxo logístico em produção e homologação

Verificação em 08/10/2026, às 10:34:55 de Brasília. A produção automatiza somente a loja Espírito Santo; HML está sem conectores e não reproduz hoje um fluxo completo de emissão. A collection Postman contém divergências que impedem usá-la como prova desse fluxo.

Este comparativo separa configuração observada, comportamento previsto pelo código implantado e comportamento da PR #9 ainda sem deploy. XPTO é um pedido fictício usado para explicar estados; nenhum pedido foi criado ou enviado aos sistemas externos nesta análise. A compra e a tela do Bling não foram exercitadas ao vivo.

## Estado observado dos ambientes

| Item | Produção atual | Homologação atual |
| --- | --- | --- |
| Processo PM2 | hub-logistico, online | hub-homolog, online |
| Diretório | /home/ti-kiosk/hub | /home/ti-kiosk/hub-homolog |
| Porta HTTP | 3000 | 3001 |
| Banco consultado em modo somente leitura | /home/ti-kiosk/hub/hub.db | /home/ti-kiosk/hub-homolog/hub-homolog.db |
| Revisão | Sem SHA de checkout recuperável; hashes de engine e adapter Bling correspondem a 992f2a9 | Checkout b28898558b71e16402bf7d52d22c8d9aa964dea7 |
| Configuração de ambiente inspecionada | PORT, DB_PATH, HUB_ENV e NODE_ENV não encontrados nas fontes inspecionadas; database.js usa ./hub.db | PORT=3001, DB_PATH=./hub-homolog.db; HUB_ENV/NODE_ENV não encontrados |
| Conectores | 1 ERP ativo, 2 carriers ativos; nenhum WMS | Nenhum |
| Lojas automáticas | Só Espírito Santo (206085936); conector próprio 2 | Todas desligadas |
| Recife | Automação desligada; conector próprio 3 | Automação desligada; sem conector próprio |
| Yampi e Shopify | Automação desligada | Automação desligada |
| Fila na amostra | 759 success; 5.810 ignorado_loja; 123 cancelado; 16 failed; 1 processing; 0 pending | Vazia |
| GET /healthz local | 404 | 404 |
| Reserva atômica, guarda HML e intenção durável da PR #9 | Ausentes nos arquivos observados | Ausentes nos arquivos observados |
| Tabela jt_emissions | Ausente | Ausente |

A amostra não diagnostica o job processing como travado: seria necessário acompanhar duração e evolução. PM2 online indica processo disponível, não conclusão correta dos pedidos. Os hashes comprovam os arquivos no diretório do processo; sem healthz da nova revisão, não há atestação de SHA carregado em memória. Contadores são uma fotografia do momento, não uma comparação de throughput.

Evidência: [snapshot sanitizado](../../../hub-logistico/docs/evidencias/comparativo-prod-hml-2026-10-08.json).

## O que a collection realmente cobre

Arquivos locais auditados: postman/Hub_Logistico_API.postman_collection.json e postman/Hub_Logistico_HML.postman_environment.json. São 14 requisições: 7 do Hub, 4 do Bling e 3 da J&T. Não há chamada Corpem, ambiente PROD, login do Hub ou scripts de teste pós-resposta. Existe apenas um pre-request script de assinatura para addOrder. Portanto, a descrição “collection completa para testes unitários e integração” não corresponde à cobertura atual.

| Requisição na collection | Contrato atual do código | Efeito da divergência |
| --- | --- | --- |
| POST /api/webhook/bling, Atendido | POST /webhook/bling, com X-Bling-Signature-256 calculado sobre os bytes enviados | Caminho atual da collection tende a 404; corrigido o caminho, falta assinatura e recebe 401 |
| POST /api/webhook/bling, Cancelado | Mesmo webhook; body.event deve ser order.updated e data.situacao.id=12 | Além de caminho/assinatura, falta event; com os demais pontos corrigidos, sem event o código ignora a situação 12 e não aciona cancelamento |
| POST /api/enviar com ids | Body esperado: erpIds; sessão do Hub obrigatória | Sem sessão: 401. Com sessão e body atual: 400, nenhum pedido selecionado |
| GET /api/pedidos?limite=50&pagina=1, descrito como fila | Lista pedidos Atendido consultados no Bling, acrescentando filaStatus local; filtros dataInicial/dataFinal/idLoja | Não retorna a fila completa nem seus contadores. limite/pagina enviados não são usados por essa rota |
| GET /api/etiqueta/1/pdf | GET /api/print/etiqueta/:queueId, sessão e job success | Caminho da collection tende a 404; o ID 1 é fixo e não seleciona o pedido do cenário |
| GET /api/lojas, “alternar automático/manual” | GET somente consulta; PUT /api/lojas/:idBling/automatico altera a flag; ambos exigem admin | A collection só lista. Sem sessão: 401; perfil sem permissão: 403 |
| GET /api/logs?tipo=erro&limite=50 | Não há essa rota; GET /api/dashboard retorna logs e stats | Caminho da collection tende a 404; dashboard retorna só os 15 logs mais recentes, sem esse filtro de tipo |
| GET Bling /pedidos/vendas/18353 | Endpoint usado no adapter, mas ID deve ser o pedido de teste controlado | Exemplo com ID fixo; não correlaciona automaticamente com o job |
| GET Bling /pedidos/vendas?idsSituacoes[]=9 | Consulta externa Atendido; o adapter também filtra a resposta pelo id de situação | Consulta isolada, sem comprovar processamento no Hub |
| GET Bling /logisticas/objetos/987654 | Objeto é obtido de transporte.volumes[0].id do pedido | ID fixo pode consultar outro objeto |
| PUT Bling /logisticas/objetos/987654, só rastreamento | Adapter faz GET do objeto, preserva outros campos no PUT e confirma por novo GET | A requisição simplificada não reproduz o contrato do adapter nem verifica persistência |
| POST J&T /addOrder | Chamada externa real, com assinatura e dados de endereço/NF do pedido | Exemplo é diferente do payload do adapter e cria nova identidade TESTE-timestamp a cada execução; não comprova idempotência nem persistência da fila |
| POST J&T /getOrders | Adapter usa assinatura do corpo e headers digest/timestamp em todas as chamadas | Collection tem apiAccount, mas falta a assinatura/headers completos; billCode fixo |
| POST J&T /printOrder | Mesmo esquema de assinatura | Mesma lacuna; billCode fixo |

O Hub espera **Authorization: token_da_sessao**, sem prefixo Bearer. O login correto é POST /api/login com username/password; o token retornado existe apenas na memória do processo e se perde em restart. As chamadas diretas ao Bling usam seu próprio Bearer access_token, que não substitui a sessão do Hub.

O ambiente HML configura hub_url para https://hub-hml.touticosmetics.com.br. As URLs do Bling e da J&T estão fixas na collection e não mudam ao selecionar HML. Uma chamada direta addOrder/PUT Bling contorna o motor, o bloqueio HML da PR #9 e as gravações do Hub. O nome do ambiente não comprova sandbox da conta externa. Não foi executada nenhuma dessas operações.

Exemplo de contrato para envio manual, após autenticar e escolher um ID de teste aprovado:

```http
POST {{hub_url}}/api/enviar
Authorization: {{hub_token}}
Content-Type: application/json

{"erpIds":["ID_ERP_DO_PEDIDO_DE_TESTE"]}
```

O webhook Atendido precisa de data.id e data.situacao.id=9, com assinatura válida. O cancelamento requer também event=order.updated. HML atual não tem ERP/clientSecret configurado para validar essa assinatura.

Evidência: [inventário sanitizado da collection](../../../hub-logistico/docs/evidencias/postman-audit-2026-10-08.json). Os arquivos originais locais foram preservados.

## Conferência da descrição informada sobre produção

Descrição informada: “o Hub puxa todos os pedidos aprovados e manda o rastreio para a J&T”.

| Afirmação | Verificação atual |
| --- | --- |
| Puxa pedidos aprovados | GET /api/pedidos chama a listagem do Bling filtrada por situação id 9, denominada Atendido no código. Se “aprovado” é o nome comercial dessa etapa, há equivalência de negócio a confirmar; não existe validação financeira independente |
| Puxa todos | Sem idLoja, a tela consulta todas as lojas, mas a API sem datas usa recorte padrão de 90 dias, limite de páginas e orçamento de 90 s; o front inicia seu filtro com os últimos 30 dias. “Todos” não significa todo o histórico nem todos emitidos |
| Busca automática em lote | O timer do motor lê a fila SQLite. A busca em lote do Bling é disparada pela rota da tela; entrada automática depende de webhook. Não há polling de pedidos aprovados do ERP pelo timer do engine |
| Processa todos os encontrados | A busca pode mostrar pedidos de todas as lojas e o webhook pode enfileirá-los, mas a regra de gerar_automatico deixa somente Espírito Santo emitir na configuração observada |
| Manda rastreio à J&T | Emissão: o Hub manda dados do pedido e seu txlogisticId para addOrder. A J&T retorna billCode/rastreio; o Hub grava no Bling. Consulta, impressão e cancelamento enviam à J&T um billCode já existente, em outra etapa |

Portanto, listar pedidos, enfileirar pedidos e emitir etiquetas são operações diferentes. Um pedido na situação Atendido pode aparecer no Bling/tela de seleção, entrar na fila e terminar ignorado_loja. A origem de canal não substitui a loja efetiva retornada pelo Bling. O envio manual de IDs pela API também não revalida a situação do pedido antes da emissão.

## Controle do checkbox no front

O controle é efetivo no backend. A tela renderiza checked quando lojas.gerar_automatico é verdadeiro. Ao alternar, alternarLojaAutomatica faz PUT /api/lojas/:idBling/automatico com body {"automatico":true/false}; a rota admin grava 1/0 na coluna gerar_automatico. O motor lê a loja do pedido e exige gerar_automatico===1 antes de emitir.

Na inspeção de produção, somente Espírito Santo (206085936) estava em 1. Recife, Yampi, as duas lojas Shopify e as demais estavam em 0. Em HML todas estavam em 0. Isso sustenta o estado esperado dos checkboxes; não foi aberta sessão autenticada no front durante esta análise.

A flag não impede o webhook de enfileirar pedidos de outras lojas; bloqueia o avanço à emissão e grava ignorado_loja após consultar o ERP. Também se aplica ao envio manual pela fila atual. O rótulo “Manual” do front não implica uma exceção de processamento implementada no motor.

Fontes: server.js:1876 (checked), server.js:1894-1896 (PUT), server.js:548-554 (persistência) e seleção da loja no engine. Esses trechos do servidor coincidem por hash com o arquivo observado em produção.

## Compra até entrada no banco

1. A compra é feita no canal de venda. A integração do canal cria/atualiza o pedido no Bling. Essa etapa é externa ao Hub e depende do canal/loja; não foi comprovada pela collection nem por uma compra real nesta análise.
2. O pedido deve chegar à situação **Atendido, id 9**, para o webhook ser aceito como entrada logística. O Hub não considera simplesmente “compra paga” e não consulta uma aprovação financeira independente.
3. Um webhook autenticado na rota correta enfileira o ID do pedido. Eventos de outras situações são ignorados; order.updated com situação 12 segue o ramo de cancelamento.
4. Alternativamente, POST /api/enviar autenticado enfileira IDs manualmente. Essa rota não revalida situação Atendido nem faturamento; a tela de seleção lista Atendido, mas chamar a API diretamente não equivale a passar pela tela.
5. Se já existe linha pending, processing ou success para o ERP, a entrada é ignorada. O envio manual reutiliza a última linha se ela estiver failed, zerando retries e error_log; preserva tracking e os demais campos não citados pelo UPDATE.

No primeiro enfileiramento, o registro ilustrativo é:

```json
{
  "id": 42,
  "erp_id": "ERP_XPTO_FICTICIO",
  "status": "pending",
  "retries": 0,
  "tracking_number": null,
  "universal_payload": null,
  "error_log": null,
  "next_attempt_at": null,
  "created_at": "HORARIO_UTC_DO_ENFILEIRAMENTO"
}
```

O banco ainda não contém endereço, itens ou loja desse pedido: o webhook salva apenas o ID. O Bling não muda nessa etapa. IDs acima são placeholders explicativos, não dados para disparar requisições.

## Processamento do XPTO nos ambientes atuais

| Etapa | Produção atual | HML atual |
| --- | --- | --- |
| Entrada por compra/webhook | Assinatura válida e Atendido criam pending, se não duplicado | Sem ERP/clientSecret, webhook correto recebe 401; não cria XPTO |
| Entrada manual corrigida/autenticada | Cria pending ou reutiliza failed | Pode criar pending; isso não habilita integrações |
| Agendador | A cada 5 s seleciona pending elegível e depois marca processing, em operações separadas | Mesmo padrão de seleção/marcação |
| Pré-requisitos | Busca ERP, carrier padrão e WMS opcional; há ERP/carriers ativos | Falha ao buscar ERP/carrier, antes de consultar o pedido no Bling |
| Dados do pedido | OAuth válido; GET Bling e conversão para payload universal | Nenhum GET Bling nessa configuração |
| Regra de loja | gerar_automatico=1 obrigatório, inclusive para entrada manual | Não chega à regra de loja sem conectores |
| Transportadora | Conector próprio ativo da loja; fallback para carrier ativo mais antigo. Remetente por loja sobrescreve o remetente do conector | Nenhuma chamada de emissão |
| Persistência final | success, ignorado_loja ou ramo de erro conforme cenário | Manualmente enfileirado: retentativas e depois failed; webhook não autenticado: sem registro |
| Bling ao final | Rastreio atualizado somente no ramo de emissão/update bem-sucedido; situação não é alterada pelo Hub | Sem alteração pelo motor |
| Corpem | Nenhum conector WMS; envio não ocorre | Nenhum conector; envio não ocorre |

Se ERP/carrier fossem configurados na HML atual, o motor passaria a consultar o Bling antes de aplicar a regra de loja. Com todas as lojas desligadas, gravaria ignorado_loja com payload. Se uma loja fosse ligada com credenciais reais, essa revisão poderia emitir: DB_PATH separado não bloqueia chamadas externas. Essa hipótese não foi aplicada ao servidor.

Mesmo no envio manual, loja não automática é ignorada pelo engine. O comentário do servidor que sugere envio manual “sem restrição” não corresponde à checagem efetiva.

## Requisições e gravações para Espírito Santo em produção

Premissas deste cenário: XPTO novo, sem tracking salvo na mesma linha; loja Espírito Santo automática; dados válidos; APIs respondem como esperado; sem WMS, conforme a configuração observada.

| Ordem | Operação | O que muda |
| --- | --- | --- |
| 1 | UPDATE orders_queue: pending para processing | Só status local; Bling intacto |
| 2 | Renovação OAuth, se necessária: POST www.bling.com.br/Api/v3/oauth/token | Atualiza configuração OAuth do conector em connectors.config; não altera o pedido |
| 3 | GET api.bling.com.br/Api/v3/pedidos/vendas/{erpId} | Apenas leitura do pedido |
| 4 | GET /contatos/{id}, se endereço de entrega ausente/incompleto | Leitura de endereço geral/cobrança; sem endereço utilizável, erro antes da emissão |
| 5 | Seleção da loja, carrier e remetente | Consultas locais; loja desligada encerra como ignorado_loja |
| 6 | POST J&T /api/order/addOrder | Cria pedido/etiqueta externa e retorna billCode, aqui RASTREIO_XPTO |
| 7 | Log de emissão; UPDATE orders_queue.tracking_number | Coluna local passa a RASTREIO_XPTO; ainda não implica Bling atualizado |
| 8 | GET Bling /pedidos/vendas/{erpId} | Obtém transporte.volumes[0].id; sem objeto, erro após a etiqueta já existir |
| 9 | GET Bling /logisticas/objetos/{idObjeto} | Lê campos do objeto para preservar no PUT |
| 10 | PUT Bling /logisticas/objetos/{idObjeto} | Define rastreamento.codigo=RASTREIO_XPTO e preserva campos de embalagem, datas, frete e outros |
| 11 | GET Bling /logisticas/objetos/{idObjeto} | Confirma código persistido; 200 sem persistência é erro |
| 12 | Sem POST Corpem, pois não há WMS | Nenhuma ordem de separação enviada pelo Hub |
| 13 | UPDATE orders_queue: success + universal_payload; log final | Registra conclusão local; preserva o rastreio na coluna |

Em produção, engine equivalente a 992f2a9 só usa tracking da mesma linha para evitar emissão. Não extrai/reutiliza tracking pré-existente no Bling nem busca outra linha histórica como faz b288985. Um pedido com etiqueta previamente gerada no ERP pode receber nova etiqueta e ter o rastreio do primeiro objeto sobrescrito.

Na HML configurada, b288985 já reutiliza tracking da linha, histórico ou ERP; quando o código do ERP coincide, dispensa o PUT. Porém o histórico dessa revisão ainda aceita cancelados e não há a proteção de resultado incerto ou reserva atômica da PR #9.

## Estado final no banco e visualização no Bling

No cenário novo de sucesso em produção, sem WMS:

```json
{
  "id": 42,
  "erp_id": "ERP_XPTO_FICTICIO",
  "status": "success",
  "retries": 0,
  "tracking_number": "RASTREIO_XPTO",
  "error_log": null,
  "next_attempt_at": null,
  "universal_payload": {
    "orderId": "ERP_XPTO_FICTICIO",
    "store": {"id": 206085936},
    "situacao": {"id": 9, "nome": "Atendido"},
    "customer": {"name": "Cliente ficticio"},
    "address": {"street": "Endereco ficticio"},
    "package": {"weight": "1.00", "qty": 1},
    "invoice": "DADOS_LIDOS_DO_BLING_OU_NULL"
  }
}
```

O payload é um recorte ilustrativo dos campos relevantes. **Nessa versão de produção, trackingNumber só é atribuído ao payload dentro do ramo WMS. Como não há WMS, a coluna tracking_number fica preenchida, mas universal_payload.trackingNumber fica ausente.** GET /api/etiquetas lê o payload e pode exibir tracking nulo; GET /api/print/etiqueta/:queueId retorna 400 por falta de código no payload. O cancelamento automático também depende de payload.trackingNumber. A revisão b288985 e a PR #9 atribuem esse campo antes do WMS e corrigem essa diferença.

No Bling, o resultado esperado pelo contrato implementado é rastreamento.codigo=RASTREIO_XPTO no **primeiro objeto de logística/volume**. O adapter confirma por GET. Na tela, espera-se esse código no volume/logística do pedido, sujeito à atualização da interface. O Hub não muda situação para Despachado, não confirma entrega, não baixa estoque nem emite NF-e. Se XPTO estava Atendido, permanece Atendido salvo mudança por outro ator. Não houve inspeção visual de pedido real no Bling.

Para uma compra de Yampi/Shopify que permanece vinculada à sua loja original, o final esperado em produção é ignorado_loja, payload preenchido, tracking_number nulo e nenhum addOrder/PUT de rastreio. Se o processo comercial altera a loja para Espírito Santo, vale a regra da loja retornada pelo GET, não o canal originalmente presumido.

Para envio manual corrigido em HML atual, depois das tentativas:

```json
{
  "erp_id": "ERP_XPTO_FICTICIO",
  "status": "failed",
  "retries": 3,
  "tracking_number": null,
  "universal_payload": null,
  "error_log": "Conectores de ERP e Transportadora nao configurados ou inativos."
}
```

Há uma tentativa inicial e até três retentativas: quatro execuções no total. Backoffs de 30, 60 e 90 s, além da latência/agendamento. next_attempt_at conserva o último prazo gravado; o estado final não o limpa. Nenhuma consulta/emissão/update externa ocorre nesse cenário. No webhook de HML sem assinatura validável, esse registro nem chega a existir.

## Cenários e resultados

| Cenário | Produção atual | HML atual ou hipótese explicitada | Resultado no Bling |
| --- | --- | --- | --- |
| Compra ainda não Atendido | Webhook ignorado; sem nova fila | Sem ERP, webhook é recusado antes da regra de situação | Hub não altera |
| Compra Atendido de Yampi/Shopify | Após consultar o pedido: ignorado_loja, sem etiqueta | Webhook sem ERP: 401; envio manual: failed após retentativas | Sem novo rastreio pelo Hub |
| Espírito Santo, novo, APIs válidas | processing para success; coluna tracking preenchida, payload sem tracking se sem WMS | Atual: não completa por falta de conectores | Produção grava código no primeiro objeto; situação preservada |
| ERP já contém rastreio e linha nova sem tracking | Pode emitir outra etiqueta e sobrescrever código; não consulta histórico/ERP para evitar isso | Hipótese com conectores/loja ligada: b288985 reutiliza e dispensa update se igual | Produção pode trocar código; hipótese HML conserva existente |
| Falha Bling após addOrder | tracking da linha é mantido; retries/backoff reaproveitam etiqueta | Só reproduzível com conectores em hipótese controlada | Pode ainda estar sem novo código; success exige confirmação posterior |
| Resposta J&T perdida | Sem intenção durável; outra tentativa pode criar identidade/etiqueta nova | Mesmo risco em b288985 se emissão for habilitada | Rastreio pode permanecer anterior/ausente |
| Rate limit TOO_MANY_REQUESTS | Volta a pending por 15 s sem incrementar retries | Sem conectores não chega ao rate limit; configurada segue mesma regra | Sem garantia de avanço nessa tentativa |
| Sem objeto/volumes no Bling | Etiqueta pode ser criada antes de falhar no update; fica em retentativa/failed com tracking salvo | Hipótese configurada segue mesma limitação quando precisa atualizar | Não cria objeto automaticamente |
| Múltiplos volumes | Uma chamada addOrder; quantidade baseada no array, mas grava apenas no primeiro objeto | Mesmo mapeamento se habilitado | Demais volumes não recebem códigos próprios pelo Hub |
| Reenvio manual de failed | Mesma linha vira pending, retries=0/error_log=NULL; tracking preservado | Sem conectores falha novamente | Só muda no ramo de update bem-sucedido |
| Webhook order.updated cancelado | Marca pending/processing como cancelado; para success tenta consultar/cancelar J&T usando payload | Sem ERP, 401 antes desse ramo | Pedido já foi cancelado no Bling; Hub não altera sua situação |
| Cancelar J&T manualmente | Com queueId, marca somente linha success como cancelado; sem queueId não atualiza fila | Exige carrier, inexistente hoje | Não cancela pedido Bling nem limpa rastreio |
| Concorrência/repetição | Seleção e processing separados; intervalo pode sobrepor, inclusive enfileiramentos duplicados | Mesmo risco estrutural em b288985 | Efeitos externos repetidos são possíveis |
| WMS ativo, hipótese futura | POST config.url com codigo_pedido_erp/cliente/documento/rastreio_transportadora; falha posterior pode reenviar | Nenhum WMS hoje | Update de rastreio pode já ter ocorrido antes da falha WMS |

package.qty é volumes.length quando o campo existe: array vazio resulta 0; campo ausente resulta 1. O adapter retorna somente um rastreio, usa o primeiro volume e não formaliza etiqueta por volume. Regras de ausência/múltiplos volumes permanecem no backlog, sem definição inventada.

No cancelamento, não assumir que marcar a fila como cancelado significa etiqueta efetivamente cancelada. O código automático busca apenas linha success, não uma failed com etiqueta já criada; e produção pode não ter tracking no payload. Cancelamento pode falhar/logar sem desfazer o rastreio no Bling. São limites atuais a revisar junto às issues #3 e #8.

## Diferença depois da PR 9

A PR de rascunho #9 ainda não está implantada. Após um deploy validado dessa revisão:

| Regra | Produção com a revisão | HML com a revisão |
| --- | --- | --- |
| Reserva da fila | UPDATE atômico SQLite por job/ERP e guarda contra sobreposição | Motor retorna antes de reservar qualquer job |
| Tracking | Reutiliza códigos válidos e bloqueia cancelados/conflitos | Nenhuma emissão pelo motor nem por generateLabel |
| Resultado incerto J&T | Intenção persistida; failed com REVIEW_REQUIRED; não reemite automaticamente | Não cria intenção porque não processa |
| Payload em sucesso | trackingNumber salvo antes do WMS | Job recebido manualmente permanece pending com payload/tracking nulos |
| Banco novo | Seed mantém ES automática | Seed deixa todas as lojas desligadas; não muda flags de banco existente |
| Observabilidade | healthz e coletor disponíveis após implantação | Gate de pós-deploy verifica ambiente, SHA e emissão desligada |

Mesmo nessa revisão, o webhook/cancelamento e endpoints administrativos são fluxos próprios: o bloqueio de emissão do motor não é uma garantia de ausência de toda mutação externa, especialmente cancelamento de etiquetas por rotas autenticadas. Testes de ciclo completo com HML não devem ser confundidos com o processamento bloqueado; sandbox exige desenho e autorização de contas/dados específicos.

## Evidências e sequência de validação

A inspeção remota usou MCP, PM2 e SQLite mode=ro. Foram comparados SHA-256 de arquivos observados com fontes locais Git; produção engine/Bling coincidem com 992f2a9, HML corresponde a b288985. Os cenários são inferências do código com premissas explícitas, apoiadas por sete reproduções offline, não resultados de compras reais.

Reproduções: [cenários e chamadas simuladas](../../../hub-logistico/docs/evidencias/comparativo-cenarios-offline-2026-10-08.json). Executar na estação com o histórico Git disponível:

```bash
node scripts/compare-deployed-behavior.js
```

A reprodução carrega engine e getOrder reais de cada revisão com adapters/axios de rede simulados e SQLite em memória. Valida: sucesso e lacuna de payload em produção, rastreio ERP ignorado em produção, loja desligada, HML sem conectores até failed, HML configurada ignorando loja, reaproveitamento ERP em b288985 e bloqueio HML da revisão local. Não mede resposta real J&T/Bling, atualização visual, cancelamento ou integração de compra.

Para fechar uma validação funcional futura: corrigir contratos da collection; definir contas/dados de teste; aprovar o desenho de sandbox; implantar a revisão esperada; executar pós-deploy; então correlacionar ID do ERP, queueId, billCode e idObjeto entre respostas, SQL e tela do Bling. Confirmar separadamente contrato Corpem e regras de volumes. Não usar o runner completo da collection atual como teste de HML.

Referências de código: server.js (webhook, enviar, dashboard e etiquetas); engine.js de 992f2a9/b288985/revisão local; adapters/bling.js (getOrder/updateTracking); adapters/jtExpress.js (addOrder/consulta/impressão/cancelamento); adapters/corpem.js (payload parcial). Revisão proposta: https://github.com/userTI10/hub-logistico/pull/9.

Ambientes: [[hub-producao]] e [[hub-homologacao]]. Backlog: [[backlog-analise-hub-logistico]].

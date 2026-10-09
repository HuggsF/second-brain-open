# Rate limiting do Bling em produção

Análise em 08/10/2026 às 11:10–11:12 de Brasília, por leitura dos logs PM2 e SQLite. A PR #9 deve reduzir sobreposição e chamadas desnecessárias, mas não implementa uma solução completa para os 429. Parte do tratamento de rate limiting já existe em produção e permanece sem alteração na PR.

## Evidências observadas

| Evidência | Resultado |
| --- | --- |
| Processo | hub-logistico online, uma instância PM2 em fork_mode; 17 reinícios acumulados, sem causa atribuída |
| Últimas 5.000 linhas do stdout | 514 ocorrências de TOO_MANY_REQUESTS: 428 no UPDATE e 86 no GET |
| Arquivo stderr do PM2 | Vazio; registrarLog usa console.log também para mensagens ERRO |
| system_logs nas últimas 24 h, primeira coleta | 303 erros de rate limiting e 4 outros erros classificados como Bling UPDATE |
| Detalhamento dos mesmos 303 erros | 235 UPDATE e 68 GET; todos com period=second e limit=3 |
| Limite diário | Nenhuma evidência entre esses 303 registros; não inferir consumo diário de requisições a partir de contagem de erros |
| Job citado pelo usuário | ERP 27056160268, queueId=7023, final ignorado_loja, retries=0, sem tracking |
| Loja desse pedido | Recife, id 206084387, com automático desligado conforme inspeção anterior |
| Failed com TOO_MANY_REQUESTS no error_log atual | Zero; campo atual não substitui histórico completo de erros |

Os números do stdout abrangem um recorte de linhas sem janela temporal garantida. Os 303 eventos têm a janela temporal do banco; não somar as duas fontes porque registram os mesmos eventos. Quatro erros UPDATE não classificados como rate limiting não foram diagnosticados neste recorte.

[Evidências sanitizadas](../../../hub-logistico/docs/evidencias/rate-limiting-pm2-2026-10-08.json) incluem horários UTC originais, contadores, estágios e hashes de fontes. Nenhum payload de cliente ou credencial foi exportado.

## O pedido 27056160268

| Horário de Brasília | Evento |
| --- | --- |
| 11:02:56 | Webhook adiciona o pedido à fila |
| 11:06:46 | Motor inicia; GET Bling recebe TOO_MANY_REQUESTS |
| 11:07:01 | Motor tenta novamente após 15 s; consulta progride e identifica loja não automática |
| 11:07:01 | Finaliza como ignorado_loja; nenhuma etiqueta |

Esse pedido não terminou failed por rate limiting. A estratégia atual preservou retries=0. error_log ainda contém o 429 anterior e next_attempt_at conserva o prazo passado: o código não limpa esses campos ao gravar ignorado_loja. É histórico residual, não evidência de que o pedido continua bloqueado pelo rate limit. Não apagamos nem reprocessamos esse registro.

## Limites confirmados pelo fornecedor

O limite é por conta Bling, abrangendo os endpoints: 3 chamadas por segundo e 120 mil por dia. O fornecedor distingue o período no erro. Há também controle por IP, incluindo uma restrição específica para excesso de chamadas OAuth. Esses orçamentos exigem políticas distintas. [Documentação oficial do Bling](https://developer.bling.com.br/limites), consultada em 08/10/2026.

Não há evidência nesta amostra de esgotamento diário ou bloqueio OAuth/IP. A documentação de limites consultada não garante Retry-After em todas as respostas; a estratégia proposta deve respeitá-lo quando disponível, com fallback explícito.

## O que já existe em produção

1. **Limitador no adapter:** aguardarSlotBling mantém timestamps em memória e admite até três inícios de chamada em uma janela de um segundo. Os métodos de dados compartilham esse controle no mesmo processo.
2. **Fila:** o engine identifica TOO_MANY_REQUESTS procurando esse texto em error.message. Registra erro, volta o job a pending e marca next_attempt_at para 15 segundos depois, sem gastar retries.
3. **Listagem do painel:** oferece até sete tentativas por página, com espera de 1,5 s multiplicada pelo número da tentativa. Há orçamento de 90 s verificado entre páginas, não um prazo rígido que interrompe cada tentativa.
4. **Tracking:** uma etiqueta já salva na mesma linha é reutilizada quando Bling falha após addOrder; isso já existia na versão de produção.
5. **OAuth:** access_token é cacheado por conector, mas faltam coalescência de renovação simultânea, limite específico do token e coordenação entre processos.

O trecho do limitador do adapter e blingAuth.js não foi alterado pela PR #9. Os hashes de engine/adapter de produção correspondem a 992f2a9; o hash remoto de blingAuth.js também foi registrado para auditoria.

## Efeito esperado da PR 9

| Alteração | Benefício verificável | Limite |
| --- | --- | --- |
| Agendador único e guarda de reentrada | Um job longo não inicia outra execução sobreposta da mesma conexão | Não controla consultas simultâneas feitas pelo painel nem apps externos |
| Reserva atômica por job/pedido ERP | Consumidores do mesmo SQLite não processam o mesmo pedido simultaneamente | Não compartilha quota entre processos/ambientes/contas externas |
| Reaproveitar rastreio existente no Bling | Evita nova emissão; quando código coincide, dispensa o ciclo de updateTracking | Pedidos realmente novos ainda precisam do ciclo de gravação/confirmacão |
| Tracking persistido no payload antes do WMS | Corrige a diferença entre coluna e exibição/impressão | Não altera a taxa de chamada do adapter |
| Intenção de emissão durável | Evita reemitir depois de resultado externo incerto | Trata risco de duplicidade J&T, não quota Bling |
| Bloqueio HML | Se HML receber conectores depois do deploy, o motor não consumirá API para processar fila | HML atual já não tem conectores; chamadas diretas do Postman/painel são fluxos próprios |
| Tratamento de 429 do engine | GET/UPDATE reagendados e rastreio preservado | A espera fixa de 15 s e a identificação por texto já existiam |

Em um pedido novo de loja automática, o fluxo mínimo normalmente consome cinco chamadas de dados Bling: GET inicial do pedido; depois GET do pedido, GET do objeto, PUT do objeto e GET de confirmação. Endereço incompleto adiciona GET de contato; OAuth é separado. Reutilizar o código já presente pode eliminar as quatro chamadas do ciclo de update. Isso é uma redução por cenário, não previsão de redução percentual dos 303 erros.

Há evidência suficiente para esperar melhora de exclusividade e segurança. Não há experimento em produção demonstrando queda dos 429 após essa PR, porque ela ainda não foi implantada. Os logs também não identificam qual outro consumidor da conta contribuiu para o limite. Mesmo com uma instância PM2, painel e motor competem pelo orçamento; outros aplicativos/scripts da mesma conta precisam ser inventariados.

## Lacunas atuais

- Controle só em memória e por processo, sem orçamento compartilhado por conta.
- Uso do teto de três chamadas sem margem para outros consumidores ou variação de chegada à API.
- Depois de um 429, só o job aguarda: o painel e outros métodos continuam podendo chamar a conta.
- GET/UPDATE de fila e listagem têm políticas diferentes, sem cooldown único.
- Falta classificação estruturada por HTTP status, period, limit e Retry-After. Um 429 com body inesperado pode consumir retries como erro comum.
- Não há tratamento específico para quota diária: reagendar de 15 em 15 segundos não resolve essa condição.
- Renovação OAuth pode acontecer simultaneamente entre chamadas/consumidores, usando refresh_token rotativo.
- Lojas desligadas ainda exigem leitura/conversão do pedido antes do filtro; endereço pode provocar consulta adicional ao contato antes de ignorar a loja.
- O estado de processamento pode avançar enquanto error_log/next_attempt_at ficam antigos.
- O pós-deploy atual da PR reprova qualquer system_logs de tipo erro no período, inclusive um 429 que já se recuperou. Esse critério precisa distinguir falha terminal de throttling recuperável.

## Estratégia planejada para concluir o tratamento

Status: **backlog, ainda não implementada**. Registrar na demanda DEM-16 e revisar separadamente antes de implantação.

### 1 Classificar erros e centralizar a espera

Criar um cliente Bling comum para chamadas de dados, com erro estruturado contendo fornecedor, endpoint/operação, HTTP status, tipo, período, limite e Retry-After sanitizado. Tratar 429 tanto por status quanto pelo tipo retornado. Não persistir headers de autenticação nem payload completo em métricas.

Aplicar cooldown da conta a todas as operações quando houver 429. Para período second, usar espera crescente com aleatoriedade e teto configurável; respeitar Retry-After, se fornecido. Diferenciar espera transitória das três tentativas de falha de negócio.

Para período day, pausar consumo dessa conta e aguardar liberação confirmada pelo fornecedor ou sinal operacional; não manter polling a cada 15 s e não presumir timezone/reset exato. Para corpo ausente/desconhecido, usar pausa conservadora e diagnóstico sem afirmar que é limite por segundo.

### 2 Coordenar o orçamento por conta

Inventariar todos os consumidores da mesma conta Bling antes de escolher o armazenamento de coordenação. No processo único atual, centralizar fila, painel e demais chamadas em um scheduler com prioridade e limite configuráveis. Proposta inicial para avaliação: operar abaixo do teto, por exemplo duas chamadas por segundo, e medir.

Se produção, HML ou outros workers usarem a mesma conta, compartilhar quota/cooldown por identidade estável dessa conta em coordenação comum, por exemplo Redis. DBs separados e connector_id locais não identificam necessariamente quotas distintas. Um limitador de duas chamadas por processo também pode ultrapassar o limite agregado; não considerá-lo solução distribuída.

Priorizar recuperação/confirmacão de pedidos já emitidos e limitar buscas repetidas do painel, preservando atendimento aos dois fluxos. Definir cache curto e limites de paginação sem usar dados antigos para sobrescrever rastreio.

### 3 Proteger OAuth e evitar trabalho desnecessário

Coalescer refresh simultâneo por conector/conta: uma renovação em andamento deve ser aguardada pelos demais callers. Recarregar estado persistido antes de renovar após competição e preservar corretamente refresh_token rotativo. Coordenar múltiplos processos se houver. Aplicar política própria do token, sem presumir que o limite de dados o cobre.

Antecipar a decisão de loja após leitura confiável de metadados e antes de enriquecer endereço/contato, evitando chamadas extras para lojas desligadas. Usar loja do webhook somente se o contrato validado a fornecer; na ausência, consultar o ERP. Não eliminar cancelamentos nem ignorar para sempre um pedido cuja loja venha a ser habilitada. Deduplicação por evento precisa respeitar mudanças de estado.

### 4 Preservar efeitos externos e retomada

Continuar reutilizando etiqueta confirmada. Se o 429 vier no update/confirmacão do Bling, reagendar essa etapa sem addOrder novo. Persistir estágio/operação e identidade do objeto quando necessário para retomada verificável.

Distinguir rejeição 429 de timeout de resultado incerto. Para PUT de resposta perdida, ler/confirmar antes de reenviar; para emissão J&T incerta, manter REVIEW_REQUIRED e reconciliar conforme DEM-15. Não transformar retry de throttling em nova compra, nova etiqueta ou nova ordem WMS.

### 5 Medir recuperação e revisar o pós deploy

Medir chamadas e 429 por conta, endpoint e período; quantidade de jobs aguardando cooldown, idade da fila, jobs concluídos e confirmacões pendentes. Classificar throttling recuperável como evento transitório, mantendo histórico; limpar ou encerrar o erro ativo quando o job progride, sem remover evidências.

Comparar uma janela antes/depois do deploy, sob carga semelhante. Objetivos: redução da proporção 429/chamadas e da idade da fila, sem perda de throughput útil, tracking ou exclusividade. Não prometer zero 429 se existirem consumidores não coordenados. Definir limiares com a linha de base e alertar sobre persistência sem progresso.

No gate pós-deploy, processo/HTTP/revisão/banco continuam críticos. Um evento transitório recuperado não deve ser confundido com pedido failed; persistência e atraso devem ter critério próprio. Alterar esse critério exige testes dedicados antes de relaxar o gate atual.

## Testes e aceite

Foram acrescentados e executados dois testes na PR #9:

- GET retorna o erro da amostra: job fica pending, retries=0, espera agendada e nenhuma emissão.
- UPDATE retorna 429 após etiqueta confirmada: job preserva rastreio/intenção confirmada; depois da recuperação vira success com apenas um addOrder no total.

npm test passou com **22 cenários**: quatro originais e dezoito no runner Node, incluindo os dois novos. Serviços externos simulados; não valida o comportamento real de quotas compartilhadas.

Aceite da DEM-16: testes de 429 por segundo, por dia, HTTP 429 sem corpo padrão e Retry-After em segundos/data; disputa painel/motor; coordenação de múltiplos consumidores; renovação OAuth simultânea; retomada após PUT/confirmacão; ausência de nova etiqueta; recuperação sem erro ativo residual; critérios de pós-deploy diferenciados. Verificar sob carga controlada e com conta/dados autorizados, depois de implementar.

Nenhum processo foi recarregado, configuração/flag alterada ou pedido reprocessado em produção durante esta análise.

Backlog formal: [DEM-16 Rate limiting Bling por conta e recuperação de throttling](https://github.com/userTI10/hub-logistico/issues/10). Revisão: [PR #9](https://github.com/userTI10/hub-logistico/pull/9).

Ambiente: [[hub-producao]]. Proteções: [[protecoes-processamento-emissao-hub]]. Comparativo: [[comparativo-prod-homolog-postman]].


## Pós-deploy validado às 12:06 de Brasília
PRs #1/#9/#11 integradas e implantadas. Janela igual de cinco minutos: 3 429 antes, 13 depois, sob tráfego distinto. Fechamento ampliado: 15 429, duas etiquetas confirmadas e dois pedidos concluídos, 13 reaproveitamentos sem segunda emissão. Zero erro terminal ou nova falha. DEM-16 permanece alta; não atribuir causalidade/redução à alteração nem declarar quota solucionada. Gate de observação distingue 429 recuperável de erro terminal. [[deploy-validacao-hub-2026-10-08]].

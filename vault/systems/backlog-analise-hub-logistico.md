---
type: system
status: active
date: 2026-10-09
---
# Backlog da análise do Hub Logístico

## Consolidação do diário de bordo — 08/10/2026

Estado baseado na última evidência de produção de **15:56:41 de Brasília**, e não em monitoramento contínuo: PR [#13](https://github.com/userTI10/hub-logistico/pull/13) integrada; SHA `3cf7250afe30931a54621093638e1b0f76f64169` implantado em produção e HML. Produção ativa, somente Espírito Santo automática; HML com worker/emissão bloqueados. Os **65 arquivos de cada ambiente** conferiram com o manifesto. PM2 persistido, banco íntegro, failed=16; o job histórico 4532 permanece para reconciliação.

Validação: **36 cenários JavaScript e 3 testes Python** aprovados, CI Node 18/20 verde e testes Linux dos releases aprovados. Após atualizar os documentos e o snapshot do grafo, **7 testes de integração do Second Brain** passaram; o teste de revisão passou a verificar a evidência citada em vez de fixar um SHA antigo.

Na janela natural de 330 segundos: dois pedidos concluídos, uma nova etiqueta e uma reaproveitada; zero 429/erro terminal de fila. Isso comprova o comportamento observado, sem comprovar resolução definitiva da quota global.

Auditoria de **15 emissões duráveis**: pedido/txlogisticId/rastreio coincidem nas três fontes e nos PDFs. Apenas a nova emissão coincide também em número e chave da NF. As **14 emissões anteriores** têm número fiscal 0 e chave zerada nos PDFs J&T. Treze payloads antigos do hub também divergem da NF atual do Bling; um payload foi corrigido no reprocessamento, mas sua etiqueta permaneceu incorreta. A chave foi verificada no PDF porque getOrders retorna `invoceNumber` e omite a chave. **744 outros ERP IDs históricos com rastreio ainda não foram auditados.**

Decisões e motivos: exigir NF real antes de uma nova intenção/emissão; preservar rastreios para evitar duplicidade; manter a versão corrigida porque rollback não retifica etiquetas antigas e reintroduziria placeholders. Nenhuma remessa foi cancelada ou reenviada. O rollback está preparado para restaurar apenas código, preservar o banco atual e iniciar worker pausado.

Próximas ações: reconciliar as 14 remessas com contrato de retificação J&T e evidência por remessa ([issue #14](https://github.com/userTI10/hub-logistico/issues/14)); ampliar a auditoria ao histórico restante; implementar quota global/OAuth coordenado ([issue #10](https://github.com/userTI10/hub-logistico/issues/10)). Qualquer cancelamento/reemissão depende de plano concreto e autorização; não executar como consequência automática da auditoria.

Relatório privado por registro: [comparativo Bling/hub/J&T](C:/KIOSK/hub-logistico/.deploy-state/nota-reconciliacao-detalhada.private.json). [Resumo de deploy, testes e rollback](C:/KIOSK/hub-logistico/.deploy-state/nota-final-results.json). Chaves individuais e PDFs ficam privados; a issue externa contém somente resumo agregado.

Memória relacionada: [[hub-producao]], [[hub-homologacao]], [[deploy-validacao-hub-2026-10-08]], [[backlog-analise-hub-logistico]]. Os registros anteriores abaixo são históricos.

Data: 2026-10-08
Status: implementação local parcial; pendências no radar
Escopo: checkout local hub-logistico, branch dev, commit b288985.
Backlog iniciado localmente; DEM-09 a DEM-15 publicadas no GitHub nas issues #2 a #8. DEM-16 acrescentada nesta revisão. Ajustes locais autorizados e implementados em 2026-10-08; sem alteração em produção. Diagnóstico inicial preservado como contexto.

## DEM-09 Exclusividade do processamento da fila

Prioridade: alta. Estado: reserva implementada localmente; recuperação após crash e homologação pendentes.
Evidência inicial no commit b288985: engine.js:18-23 seleciona pending e depois marca processing; engine.js:244 agenda processQueue a cada cinco segundos sem aguardar a execução anterior.
Impacto: callbacks podem se sobrepor; a reserva em duas operações também permite que consumidores concorrentes selecionem o mesmo job. Duas linhas do mesmo erp_id continuam sendo outro problema mesmo com reserva exclusiva por linha.

Proposta: impedir reentrada dentro do processo com um worker único e flag liberada em finally, ou laço que aguarda o término antes de agendar a próxima execução. Reservar o job atomicamente no SQLite, com UPDATE condicional e conferência da linha alterada ou transação curta. Evitar manter transação aberta durante chamadas HTTP. Definir exclusão por pedido ERP e recuperação de jobs processing abandonados com lease e proprietário.
Porquê: singleton em memória tem alcance de um processo; não coordena processos PM2, múltiplas instâncias nem workers externos. Reserva por job não fornece idempotência da emissão externa.

Aceite: consumidores concorrentes não executam o mesmo job; duas linhas do mesmo pedido não emitem simultaneamente; processamento superior a cinco segundos não se sobrepõe; falha libera o bloqueio local; reinício recupera jobs abandonados segundo política definida. Testes com serviços simulados.

## DEM-10 Validade do rastreio reutilizado e cancelamento

Prioridade: alta. Estado: bloqueios conservadores implementados; modelo de validade pendente.
Evidência inicial no commit b288985: engine.js:152 consulta erp_id e tracking_number não vazio, sem filtro por status. server.js:185-252 filtra Atendido no webhook; server.js:841-854 cancela a etiqueta e pode marcar a linha cancelado mantendo o rastreio.
Impacto: nova linha pending pode recuperar rastreio de linha cancelada. Se o ERP ainda guardar o código cancelado, a terceira camada pode recuperá-lo mesmo após excluir linhas canceladas do histórico.

Esclarecimento: Atendido é situação do pedido no Bling; pending, processing, success, failed e cancelado são estados internos do job. Success não significa aprovação financeira ou faturamento. Failed pode conter uma etiqueta válida emitida antes de falha no Bling ou WMS; filtrar somente success recriaria risco de duplicidade.
Proposta: separar estado de processamento do estado de validade da etiqueta. Persistir transportadora, conector emissor, cancelamento confirmado e identidade da emissão. Definir reconciliação quando histórico e ERP divergem; bloquear reutilização de emissão cancelada também pela camada ERP.

Aceite: rastreio válido de job failed é preservado; etiqueta cancelada não é reutilizada por histórico nem ERP; conflito de códigos segue regra explícita; cancelamento com resultado incerto não é tratado como confirmação.

## DEM-11 Inicialização segura do banco de homologação

Prioridade: alta. Estado: seed e bloqueio implementados localmente; homologação pendente.
Causa: database.js:10 escolhe o arquivo por DB_PATH. Quando lojas está vazia, database.js:101-113 carrega lojas iniciais com Espírito Santo (206085936) em gerar_automatico = 1, sem distinção de ambiente.
O problema está na carga inicial de configuração, não no mecanismo SQLite. Configurar todas as lojas como 0 no banco existente não altera esse seed.

Fluxo impactado:
1. Primeiro boot com banco novo, arquivo perdido ou DB_PATH apontando para outro banco.
2. initDB cria tabelas e ativa a loja Espírito Santo.
3. Webhook de pedido Atendido ou envio manual adiciona pending.
4. engine consulta loja e permite o processamento porque gerar_automatico = 1.
5. Sem rastreio anterior, generateLabel chama a J&T; o adapter atual utiliza URL fixa e o contrato configurado.
6. Se houver credenciais reais, a homologação pode emitir frete real; depois vêm atualização do Bling e envio opcional ao WMS.

Com todas as lojas em 0, o motor em produção também ignora pedidos enviados manualmente: não existe bypass de origem manual no filtro de loja. A tela chamar esse estado de Manual não comprova um caminho controlado de teste.

Proposta: ambiente explícito, seed de homologação com todas as lojas desligadas e bloqueio de emissão real independente do caminho do banco. Definir caminho deliberado de testes e contratos de sandbox antes da implementação.
Aceite: banco hml novo inicia sem loja automática; caminhos webhook e manual não emitem frete real; configuração inválida não libera emissão; testes usam mocks; produção mantém comportamento apenas conforme decisão explícita. Banco atual do servidor não foi inspecionado nesta revisão.

## DEM-12 Contrato universal de separação e adapter Corpem

Prioridade: média. Estado: avaliação proposta por Hugo; depende do contrato do WMS.
Evidência inicial no commit b288985: adapters/corpem.js:6-16 usa payload de exemplo com pedido, cliente, documento e rastreio, enviando POST real quando um conector WMS está ativo. Não há itens/SKUs no payload atual de sendToWMS.

Proposta: entidade agnóstica OrdemDeSeparacao e porta WMS com contrato de entrada e resultado. CorpemAdapter traduz essa entidade para o contrato específico do fornecedor; novos WMS implementam a mesma porta. Não colocar campos específicos do Corpem na entidade universal.
Porquê: desacopla o domínio do fornecedor e torna validação e testes de contrato possíveis. Criar o adapter sozinho não fecha a issue: são necessárias documentação oficial, campos obrigatórios, vínculo entre pedido e expedição, autenticação, erros, confirmação e política de idempotência.

Aceite: contrato versionado com itens/SKUs, quantidades e demais campos acordados; tradução validada; erros e confirmação interpretados; retentativa não duplica ordem de separação; envio validado em homologação do WMS. Lista final de campos e ordem operacional picking/packing/emissão dependem de definição com operação e fornecedor.

## DEM-13 Volumes ausentes e múltiplos volumes

Prioridade: média. Estado: #status/blocked-definicao, mantido no backlog por decisão de Hugo.
Evidência inicial no commit b288985: adapters/bling.js:174 usa volumes[0]; updateTracking atualiza o primeiro objeto; package.qty usa volumes.length quando o array existe, inclusive zero para [].
Impacto: quantidade zero e representação incompleta de múltiplos volumes/rastreios; impressão, atualização do ERP, emissão de frete e integração WMS podem divergir.
Definições pendentes: unidade de emissão pedido/remessa/volume; quantidade quando ERP não informa volumes; peso por volume ou total; rastreio por volume; reprocessamento e cancelamento parcial; relação entre packing WMS e volumes.
Decisão: não inventar valores nem implantar regra enquanto o negócio não definir esses pontos.
Aceite futuro: exemplos aprovados de zero, um e vários volumes; contrato universal representando cada volume; mapeamento e testes de emissão, persistência, atualização e cancelamento parcial conforme a regra aprovada.

## DEM-14 Modelo semântico e organização do dashboard

Prioridade: média. Estado: dashboard implementado e verificado localmente.
Evidência inicial no commit b288985: dashboard/app.js define NODES_DATA, LINKS_DATA e docContent fixos; selectNode usa innerHTML desse conteúdo. O grafo mistura sistemas, regras, gaps e infraestrutura e aplica gravidade central em updatePhysics.
Impacto: posição pouco previsível, sobreposição potencial e conteúdo duplicado divergindo do vault. Alguns docPath apontam para documentos que não existem no inventário atual, como shopify.md, yampi.md, jt-express.md e corpem-wms.md.
Plano e critérios: [[modelo-semantico-e-visualizacao-grafo]].

## DEM-15 Reconciliação da emissão externa sem resposta persistida

Prioridade: alta. Estado: intenção persistida e bloqueio local; reconciliação automática pendente.
Evidência inicial no commit b288985: engine.js:172-174 emite e depois registra log e tracking; adapters/jtExpress.js:91 gera txlogisticId com timestamp e devolve somente billCode.
Impacto: emissão aceita pela J&T seguida de perda de resposta ou falha local pode ficar sem rastreio persistido; a próxima tentativa envia identidade diferente.
Proposta: persistir intenção/identidade antes da chamada e reconciliar resultado incerto antes de emitir de novo. Validar garantias da API para identidade estável; não presumir que ela fornece idempotência.
Aceite: teste de resposta perdida e crash após emissão comprova reconciliação e ausência de segunda emissão. Essa proteção é independente do singleton.

## Evidências e limites

npm test executado em 2026-10-08: quatro cenários aprovados em tests/suite_duplicidade.test.js, SQLite em memória e chamadas externas simuladas. Isso não mede cobertura total nem valida concorrência, cancelamento, contrato Corpem ou múltiplos volumes.
Referências: [[investigacao-duplicidade-etiquetas]], [[implantacao-instancia-homologacao]], [[bling-api-v3-especificacao-pedidos]], [[radar-demandas]].

## Implementação local em 2026-10-08

Ajustes autorizados por Hugo na branch fix/fila-rastreios-hml, sem deploy.

| Demanda | Entrega local | Pendente |
| --- | --- | --- |
| DEM-09 | Guarda local, agendador único e reserva atômica por job/ERP | Lease, heartbeat, recuperação após crash e homologação |
| DEM-10 | Bloqueio de cancelados/conflitos; preservar failed com etiqueta válida | Validade da etiqueta, conector emissor e homologação |
| DEM-11 | Seed hml desligado e bloqueio no motor/adapter | Configuração explícita, homologação e sandbox |
| DEM-12 | Contrato proposto documentado | Documentação do WMS e implementação/validação |
| DEM-13 | Pendência preservada | Definição operacional de volumes |
| DEM-14 | Catálogo de 19 nós, três vistas, filtros e fontes geradas do vault | Evoluir catálogo e recuperação GraphRAG |
| DEM-15 | Intenção durável e bloqueio de resultado incerto | Reconciliação automática e classificação das respostas |

npm test: quatro cenários originais e doze novos aprovados, serviços simulados. Demandas ainda dependentes de homologação/contrato não foram marcadas como concluídas. Detalhes: [[protecoes-processamento-emissao-hub]].

## Backlog no GitHub

- [DEM-09 Exclusividade do processamento da fila](https://github.com/userTI10/hub-logistico/issues/2)
- [DEM-10 Validade do rastreio reutilizado e cancelamento](https://github.com/userTI10/hub-logistico/issues/3)
- [DEM-11 Inicialização segura do banco de homologação](https://github.com/userTI10/hub-logistico/issues/4)
- [DEM-12 Contrato universal de separação e adapter Corpem](https://github.com/userTI10/hub-logistico/issues/5)
- [DEM-13 Volumes ausentes e múltiplos volumes](https://github.com/userTI10/hub-logistico/issues/6)
- [DEM-14 Modelo semântico e organização do dashboard](https://github.com/userTI10/hub-logistico/issues/7)
- [DEM-15 Reconciliação da emissão externa sem resposta persistida](https://github.com/userTI10/hub-logistico/issues/8)

## DEM-16 Rate limiting por conta e recuperação de throttling

Prioridade: alta. Estado: backlog; estratégia detalhada, ainda não implementada.

Evidência em produção em 08/10/2026: 303 TOO_MANY_REQUESTS nas últimas 24 h, todos period=second/limit=3; 235 no UPDATE e 68 no GET. Logs PM2 são stdout, stderr vazio. Pedido citado 27056160268 recuperou em 15 s e finalizou ignorado_loja, retries=0, mas error_log continuou com erro antigo.

Limitador local (3 inícios/s), reagendamento fixo de 15 s sem gastar retries e tentativas da listagem já existem em produção. PR #9 melhora exclusividade e reaproveitamento de rastreio, mas não altera o limitador nem OAuth. Dois testes novos comprovam GET 429 sem emissão e UPDATE 429 com recuperação sem segunda etiqueta.

Plano pendente:
1. Erros estruturados por status/tipo/period/limit/Retry-After; identificar HTTP 429 mesmo sem body padrão.
2. Scheduler/cooldown por conta para fila/painel; margem abaixo do teto e coordenação comum se houver consumidores em vários processos/ambientes.
3. Backoff crescente com aleatoriedade para limite por segundo; pausa específica para quota diária; não presumir reset/timezone.
4. Single-flight de OAuth/refresh_token rotativo, com coordenação entre processos quando aplicável.
5. Filtrar loja antes de enriquecimento de endereço, sob contrato confiável; preservar cancelamento/mudanças de estado.
6. Retomar update/confirmacão sem novo addOrder; conciliar timeout de efeito incerto.
7. Métricas de 429/chamadas, cooldown e progresso da fila; diferenciar transiente de failed no pós-deploy, preservar histórico e encerrar erro ativo residual.

Aceite: testes por segundo/dia, Retry-After segundos/data, corpo inesperado, disputa painel/motor, múltiplos consumidores, renovação OAuth simultânea, PUT/confirmacão de resultado incerto e ausência de segunda etiqueta. Comparar baseline antes/depois sob carga controlada. Ainda não implementado nem implantado.

Documentação detalhada e evidências sanitizadas na branch fix/fila-rastreios-hml: docs/rate-limiting-producao.md e docs/evidencias/rate-limiting-pm2-2026-10-08.json. Fonte oficial: https://developer.bling.com.br/limites.

Issue: https://github.com/userTI10/hub-logistico/issues/10. Procedimento e diagnóstico: [[rate-limiting-bling-producao]].

## Integração e validação em produção — 08/10/2026
PRs #1/#9/#11 integradas; SHA 1111ea15 implantado em produção e HML. 26 testes npm, três ensaios Python e CI Node 18/20 aprovados. DEM-09/10/11/15 têm proteções implantadas; DEM-11 seed/guarda HML comprovados por testes e ambiente pausado. Lease e reconciliação do processing4532, validade/conector e reconciliação automática continuam pendentes. Corpem e volumes não foram definidos por presunção. DEM-16 continua alta: 13 429 em cinco minutos posteriores, quota por conta ainda não implementada. Rollback HML exercitado e banco preservado; produção permanece ativa após verificação. [[deploy-validacao-hub-2026-10-08]].

## Atualização — PR #13 e auditoria fiscal, 08/10/2026

Revisão corrente de produção e HML: 3cf7250afe30931a54621093638e1b0f76f64169. PR #13 integrada com CI Node 18/20; 36 cenários JavaScript e 3 testes Python aprovados localmente, npm test também aprovado nos releases Linux isolados. HML permanece com worker/emissão bloqueados e lojas desligadas. Produção ativa, só Espírito Santo automática, HTTP interno/público saudáveis e bancos íntegros; PM2 persistido. Arquivos de produção conferidos por manifesto sem divergência.

Janela natural de 330 segundos após liberação às 15:35:26 de Brasília: dois pedidos concluídos, uma etiqueta nova e uma reaproveitada; zero 429/erro terminal de fila, failed=16 e processing antigo 4532 preservados. Janela anterior equivalente: nove 429 e nenhum pedido concluído. Carga diferente impede afirmar resolução definitiva de rate limiting. Worker pausado temporariamente para auditoria de leitura e restabelecido às 15:46:48; contador PM2 passou de 18 para 21 por reinícios intencionais de liberação/pausa/retomada, estável depois.

Auditoria cruzou todos os 15 registros duráveis de jt_emissions com GET de pedido e NF do Bling, consulta getOrders e PDF printOrder da J&T. ERP/txlogisticId/rastreio coincidem em 15/15. A emissão nova, ERP 27080564859 / rastreio 888030980289939 / NF 002609, coincide nas três fontes; a chave completa também coincide com o PDF da J&T. Chaves detalhadas e PDFs permanecem privados.

As 14 etiquetas anteriores têm NF 0 e chave zerada na J&T, divergentes do Bling. O payload do hub foi corrigido para o pedido antigo reprocessado, porém sua etiqueta permanece com os dados fiscais anteriores. Reprocessar não é retificar a transportadora. A consulta retorna o campo **invoceNumber**, e a chave precisou ser conferida no PDF. Os demais 744 ERP IDs do histórico com rastreio ainda não receberam esta auditoria cruzada.

Decisão: a versão corrigida bloqueia nova emissão sem NF real antes de criar intenção J&T; preserva rastreios existentes. Valida presença/formato, sem presumir autorização fiscal ou reconciliação histórica. Manter a versão corrigida; rollback reintroduziria placeholders e não corrigiria as etiquetas existentes. Nenhum cancelamento/reenvio foi feito. Backlog de reconciliação: https://github.com/userTI10/hub-logistico/issues/14; o GitHub contém só resumo agregado, dados individuais ficam privados. Quota global Bling permanece na issue #10.

Rollback pronto: sudo -n python3 /home/ti-kiosk/hub-deploy/deploy-control.py rollback --environment production --state /home/ti-kiosk/hub-deploy/backups/production-20261008T183411Z-3cf7250a/state.json. Restaura código, preserva banco atual e inicia worker pausado; reativação depende de conciliação. Backup HML: /home/ti-kiosk/hub-deploy/backups/hml-20261008T183312Z-3cf7250a.

Evidências locais: C:/KIOSK/hub-logistico/.deploy-state/nota-final-results.json; nota-cross-audit.private.json; nota-pdf-all-results.private.json; PDFs em nota-labels.private. Esses arquivos não foram publicados. Esta atualização substitui os registros anteriores para o estado corrente.

---
type: system
status: active
date: 2026-10-09
---
# Proteções locais de processamento e emissão do Hub

Atualizado em 2026-10-08. Implantado em produção e HML no SRV-API em 1111ea15eb9c67a6a17ef78c47cff0793a5f6dc6. PRs #1, #9 e #11 integradas; detalhes em deploy-validacao-2026-10-08.md.

## Reserva e concorrência

processQueue impede reentrada por conexão com WeakSet e finally. startEngine devolve um único agendador por conexão; stop encerra o timer. A reserva usa UPDATE com subconsulta e RETURNING, em uma instrução atômica no SQLite. Pedidos ERP com job processing não têm outra linha reservada, inclusive por outra conexão ao mesmo banco.
Não há transação aberta durante HTTP. Requer SQLite 3.35 ou superior; a suíte executa a instrução na biblioteca instalada.
Um processo que morra pode deixar processing bloqueado. Não existe expiração automática: recuperar sem investigar a emissão poderia duplicar frete. Lease com proprietário/heartbeat e recuperação segura permanecem pendentes na DEM-09.

## Rastreios e revisão operacional

Failed pode conter etiqueta válida; seu reaproveitamento foi preservado. Linhas cancelado não são fontes de rastreio. Código marcado cancelado em qualquer linha do mesmo pedido bloqueia reaproveitamento pelo job, registro de emissão ou ERP.
Histórico cancelado sem rastreio válido substituto bloqueia nova emissão até definição de remessa. Divergência entre Hub e ERP é REVIEW_REQUIRED, sem sobrescrever ERP.
Cancelado é sinal conservador: não representa necessariamente confirmação de cancelamento externo. O modelo completo de validade da etiqueta e conector emissor permanece DEM-10.
As gravações finais e de retentativa não sobrescrevem cancelamento recebido durante HTTP. Cancelamento no meio de uma chamada externa já enviada exige conferência; não existe cancelamento transacional entre SQLite e transportadora.

## Registro de emissão

jt_emissions é criado por initDB. Cada erp_id tem uma intenção com txlogistic_id persistido antes da chamada, state uncertain ou confirmed e tracking_number.
A J&T recebe a identidade registrada. Confirmado o billCode, o registro é atualizado antes de salvar o rastreio na fila e antes de registrar sucesso. Um rastreio confirmado permite recuperar falha posterior de persistência na fila.
Timeout, rejeição ou falha após registrar a intenção deixam uncertain e encerram o job como failed com REVIEW_REQUIRED. Até uma rejeição inequívoca é tratada conservadoramente; a classificação de respostas e reconciliação automática ainda não foram validadas.
Reenviar manualmente um job não limpa a intenção. Isso bloqueia repetição automática mesmo se o processo reiniciar. Não existe garantia presumida de idempotência da J&T, nem resolução automática de uncertain.

## Procedimento de recuperação

Com o consumidor parado e após verificar pedidos/etiquetas na J&T, conferir erp_id, txlogistic_id, estado, rastreio e linhas da fila. Se houve emissão, reconciliar o registro e rastreio existente; se não houve, a liberação de uma nova intenção depende de confirmação operacional e evidência do fornecedor. Não apagar uncertain só para liberar fila.
Revisão e ferramenta específica de reconciliação permanecem DEM-15. Não reativar processing abandonado enquanto houver consumidor ativo ou emissão externa não verificada.

## Homologação

HUB_ENV=hml é a configuração explícita recomendada. NODE_ENV=hml/homolog/homologacao ou nome do banco contendo hml/homolog também ativam proteção para instalações anteriores. Valores de ambiente desconhecidos falham antes de liberar processamento.
Banco novo de homologação carrega todas as lojas com gerar_automatico=0. Configurações de lojas existentes não são alteradas pela migração.
O motor mantém jobs pending sem chamar ERP, J&T ou WMS em homologação; generateLabel também rejeita chamadas diretas. Não existe bypass por clicar envio manual ou ligar uma loja.
Teste financeiro real/sandbox não foi habilitado. Os testes usam mocks com ambiente de teste/produção explicitamente isolado. Produção mantém o seed anterior.

## Contratos e definições pendentes

Corpem continua como integração parcial com payload de exemplo. Contrato WMS/OrdemDeSeparacao e itens exigem documentação do fornecedor antes de implementar: DEM-12.
Volumes ausentes e múltiplos volumes continuam aguardando regra operacional: DEM-13. Nenhuma regra de quantidade, peso ou reemissão parcial foi inventada.
Múltiplos conectores ERP e múltiplas remessas do mesmo erp_id ainda exigem identidade mais rica; o registro atual segue a identidade única utilizada pelo motor.

## Verificação

A consulta de NF usa GET /nfe/{id}. Toda nova emissão exige número positivo, série, chave de 44 dígitos não zerada e data de emissão válida. Falha de consulta ou NF incompleta bloqueia a emissão antes de criar intenção J&T; 429 volta à fila com cooldown. Rastreios existentes continuam reutilizáveis mesmo quando a consulta da NF está indisponível. O adapter J&T também rejeita placeholders em chamadas diretas. Esta validação de presença/formato não comprova autorização fiscal nem reconcilia etiquetas antigas. A suíte foi ampliada para 36 cenários JavaScript, incluindo essas regressões, e três testes Python de deploy/rollback.

npm test inclui 26 cenários aprovados, com CI Node 18/20 e execução em releases Linux isolados. Três testes Python verificam o controle e preservação de banco no rollback. A concorrência usa duas conexões ao mesmo SQLite temporário. No tráfego natural observado após implantação, dois pedidos concluíram com duas etiquetas confirmadas e rastreios consistentes; contrato Corpem e cobertura completa dos cenários operacionais permanecem pendentes.
Referências: [[backlog-analise-hub-logistico]], [[modelo-semantico-e-visualizacao-grafo]].

## Atualização — PR #13 e auditoria fiscal, 08/10/2026

Revisão corrente de produção e HML: 3cf7250afe30931a54621093638e1b0f76f64169. PR #13 integrada com CI Node 18/20; 36 cenários JavaScript e 3 testes Python aprovados localmente, npm test também aprovado nos releases Linux isolados. HML permanece com worker/emissão bloqueados e lojas desligadas. Produção ativa, só Espírito Santo automática, HTTP interno/público saudáveis e bancos íntegros; PM2 persistido. Arquivos de produção conferidos por manifesto sem divergência.

Janela natural de 330 segundos após liberação às 15:35:26 de Brasília: dois pedidos concluídos, uma etiqueta nova e uma reaproveitada; zero 429/erro terminal de fila, failed=16 e processing antigo 4532 preservados. Janela anterior equivalente: nove 429 e nenhum pedido concluído. Carga diferente impede afirmar resolução definitiva de rate limiting. Worker pausado temporariamente para auditoria de leitura e restabelecido às 15:46:48; contador PM2 passou de 18 para 21 por reinícios intencionais de liberação/pausa/retomada, estável depois.

Auditoria cruzou todos os 15 registros duráveis de jt_emissions com GET de pedido e NF do Bling, consulta getOrders e PDF printOrder da J&T. ERP/txlogisticId/rastreio coincidem em 15/15. A emissão nova, ERP 27080564859 / rastreio 888030980289939 / NF 002609, coincide nas três fontes; a chave completa também coincide com o PDF da J&T. Chaves detalhadas e PDFs permanecem privados.

As 14 etiquetas anteriores têm NF 0 e chave zerada na J&T, divergentes do Bling. O payload do hub foi corrigido para o pedido antigo reprocessado, porém sua etiqueta permanece com os dados fiscais anteriores. Reprocessar não é retificar a transportadora. A consulta retorna o campo **invoceNumber**, e a chave precisou ser conferida no PDF. Os demais 744 ERP IDs do histórico com rastreio ainda não receberam esta auditoria cruzada.

Decisão: a versão corrigida bloqueia nova emissão sem NF real antes de criar intenção J&T; preserva rastreios existentes. Valida presença/formato, sem presumir autorização fiscal ou reconciliação histórica. Manter a versão corrigida; rollback reintroduziria placeholders e não corrigiria as etiquetas existentes. Nenhum cancelamento/reenvio foi feito. Backlog de reconciliação: https://github.com/userTI10/hub-logistico/issues/14; o GitHub contém só resumo agregado, dados individuais ficam privados. Quota global Bling permanece na issue #10.

Rollback pronto: sudo -n python3 /home/ti-kiosk/hub-deploy/deploy-control.py rollback --environment production --state /home/ti-kiosk/hub-deploy/backups/production-20261008T183411Z-3cf7250a/state.json. Restaura código, preserva banco atual e inicia worker pausado; reativação depende de conciliação. Backup HML: /home/ti-kiosk/hub-deploy/backups/hml-20261008T183312Z-3cf7250a.

Evidências locais: C:/KIOSK/hub-logistico/.deploy-state/nota-final-results.json; nota-cross-audit.private.json; nota-pdf-all-results.private.json; PDFs em nota-labels.private. Esses arquivos não foram publicados. Esta atualização substitui o estado corrente descrito no registro anterior abaixo.

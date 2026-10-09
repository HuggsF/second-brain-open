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

npm test inclui 26 cenários aprovados, com CI Node 18/20 e execução em releases Linux isolados. Três testes Python verificam o controle e preservação de banco no rollback. A concorrência usa duas conexões ao mesmo SQLite temporário. No tráfego natural observado após implantação, dois pedidos concluíram com duas etiquetas confirmadas e rastreios consistentes; contrato Corpem e cobertura completa dos cenários operacionais permanecem pendentes.
Referências: [[backlog-analise-hub-logistico]], [[modelo-semantico-e-visualizacao-grafo]].


Validação real e limites: [[deploy-validacao-hub-2026-10-08]].

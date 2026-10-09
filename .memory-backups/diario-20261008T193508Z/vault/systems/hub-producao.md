# Hub — Produção

## Atualização — PR #13 e auditoria fiscal, 08/10/2026

Revisão corrente de produção e HML: 3cf7250afe30931a54621093638e1b0f76f64169. PR #13 integrada com CI Node 18/20; 36 cenários JavaScript e 3 testes Python aprovados localmente, npm test também aprovado nos releases Linux isolados. HML permanece com worker/emissão bloqueados e lojas desligadas. Produção ativa, só Espírito Santo automática, HTTP interno/público saudáveis e bancos íntegros; PM2 persistido. Arquivos de produção conferidos por manifesto sem divergência.

Janela natural de 330 segundos após liberação às 15:35:26 de Brasília: dois pedidos concluídos, uma etiqueta nova e uma reaproveitada; zero 429/erro terminal de fila, failed=16 e processing antigo 4532 preservados. Janela anterior equivalente: nove 429 e nenhum pedido concluído. Carga diferente impede afirmar resolução definitiva de rate limiting. Worker pausado temporariamente para auditoria de leitura e restabelecido às 15:46:48; contador PM2 passou de 18 para 21 por reinícios intencionais de liberação/pausa/retomada, estável depois.

Auditoria cruzou todos os 15 registros duráveis de jt_emissions com GET de pedido e NF do Bling, consulta getOrders e PDF printOrder da J&T. ERP/txlogisticId/rastreio coincidem em 15/15. A emissão nova, ERP 27080564859 / rastreio 888030980289939 / NF 002609, coincide nas três fontes; a chave completa também coincide com o PDF da J&T. Chaves detalhadas e PDFs permanecem privados.

As 14 etiquetas anteriores têm NF 0 e chave zerada na J&T, divergentes do Bling. O payload do hub foi corrigido para o pedido antigo reprocessado, porém sua etiqueta permanece com os dados fiscais anteriores. Reprocessar não é retificar a transportadora. A consulta retorna o campo **invoceNumber**, e a chave precisou ser conferida no PDF. Os demais 744 ERP IDs do histórico com rastreio ainda não receberam esta auditoria cruzada.

Decisão: a versão corrigida bloqueia nova emissão sem NF real antes de criar intenção J&T; preserva rastreios existentes. Valida presença/formato, sem presumir autorização fiscal ou reconciliação histórica. Manter a versão corrigida; rollback reintroduziria placeholders e não corrigiria as etiquetas existentes. Nenhum cancelamento/reenvio foi feito. Backlog de reconciliação: https://github.com/userTI10/hub-logistico/issues/14; o GitHub contém só resumo agregado, dados individuais ficam privados. Quota global Bling permanece na issue #10.

Rollback pronto: sudo -n python3 /home/ti-kiosk/hub-deploy/deploy-control.py rollback --environment production --state /home/ti-kiosk/hub-deploy/backups/production-20261008T183411Z-3cf7250a/state.json. Restaura código, preserva banco atual e inicia worker pausado; reativação depende de conciliação. Backup HML: /home/ti-kiosk/hub-deploy/backups/hml-20261008T183312Z-3cf7250a.

Evidências locais: C:/KIOSK/hub-logistico/.deploy-state/nota-final-results.json; nota-cross-audit.private.json; nota-pdf-all-results.private.json; PDFs em nota-labels.private. Esses arquivos não foram publicados. Esta atualização substitui o estado corrente descrito no registro anterior abaixo.

## Histórico da implantação anterior (12:06 de Brasília)


Estado validado em 08/10/2026 às 12:06 de Brasília. PRs #1, #9 e #11 integradas; revisão implantada 1111ea15eb9c67a6a17ef78c47cff0793a5f6dc6.

| Recurso | Valor verificado |
| --- | --- |
| Servidor | SRV-API |
| Diretório | /home/ti-kiosk/hub |
| PM2 | hub-logistico, online, uma instância fork |
| Porta | 3000 |
| Banco | /home/ti-kiosk/hub/hub.db, quick_check=ok |
| URL | https://hub.touticosmetics.com.br |
| Ambiente | HUB_ENV=production |
| Worker | HUB_WORKER_ENABLED=1 |
| Emissão automática | Só Espírito Santo, conector 2 |
| Revisão | REVISION e /healthz interno/público confirmam SHA 1111ea15eb9c67a6a17ef78c47cff0793a5f6dc6 |

Código exportado do Git, sem checkout em produção. 49 arquivos do manifesto SHA-256 conferidos. PM2 persistido com save. Reinicialização de liberação elevou contador 17 para 18; estável depois.

Na observação: dois pedidos concluídos, duas etiquetas confirmadas e 13 reaproveitamentos nas retentativas. Rastreios coincidem na fila, payload e registro de emissão. Quinze 429; zero erro terminal novo; failed=16 preservado; processing antigo 4532 desde 30/09 permanece para reconciliação. Nenhum pedido artificial de teste ou cancelamento real.

Rate limiting continua pendente, e a janela não prova redução de erros. Rollback restaura código, mantém banco atual e inicia worker pausado; reativação exige reconciliação. Backups privados: /home/ti-kiosk/hub-deploy/backups/production-20261008T145704Z-1111ea15.

Resultado/evidências: [[deploy-validacao-hub-2026-10-08]]. Procedimento: [[post-deploy-observabilidade-hub]]. Pendências: [[rate-limiting-bling-producao]], [[backlog-analise-hub-logistico]]. Comparativo histórico anterior: [[comparativo-prod-homolog-postman]].

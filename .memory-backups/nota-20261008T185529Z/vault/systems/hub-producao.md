# Hub — Produção

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

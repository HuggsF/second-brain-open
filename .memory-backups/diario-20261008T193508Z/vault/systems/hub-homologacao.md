# Hub — Homologação

## Atualização — PR #13 e auditoria fiscal, 08/10/2026

Revisão corrente de produção e HML: 3cf7250afe30931a54621093638e1b0f76f64169. PR #13 integrada com CI Node 18/20; 36 cenários JavaScript e 3 testes Python aprovados localmente, npm test também aprovado nos releases Linux isolados. HML permanece com worker/emissão bloqueados e lojas desligadas. Produção ativa, só Espírito Santo automática, HTTP interno/público saudáveis e bancos íntegros; PM2 persistido. Arquivos de produção conferidos por manifesto sem divergência.

Janela natural de 330 segundos após liberação às 15:35:26 de Brasília: dois pedidos concluídos, uma etiqueta nova e uma reaproveitada; zero 429/erro terminal de fila, failed=16 e processing antigo 4532 preservados. Janela anterior equivalente: nove 429 e nenhum pedido concluído. Carga diferente impede afirmar resolução definitiva de rate limiting. Worker pausado temporariamente para auditoria de leitura e restabelecido às 15:46:48; contador PM2 passou de 18 para 21 por reinícios intencionais de liberação/pausa/retomada, estável depois.

Auditoria cruzou todos os 15 registros duráveis de jt_emissions com GET de pedido e NF do Bling, consulta getOrders e PDF printOrder da J&T. ERP/txlogisticId/rastreio coincidem em 15/15. A emissão nova, ERP 27080564859 / rastreio 888030980289939 / NF 002609, coincide nas três fontes; a chave completa também coincide com o PDF da J&T. Chaves detalhadas e PDFs permanecem privados.

As 14 etiquetas anteriores têm NF 0 e chave zerada na J&T, divergentes do Bling. O payload do hub foi corrigido para o pedido antigo reprocessado, porém sua etiqueta permanece com os dados fiscais anteriores. Reprocessar não é retificar a transportadora. A consulta retorna o campo **invoceNumber**, e a chave precisou ser conferida no PDF. Os demais 744 ERP IDs do histórico com rastreio ainda não receberam esta auditoria cruzada.

Decisão: a versão corrigida bloqueia nova emissão sem NF real antes de criar intenção J&T; preserva rastreios existentes. Valida presença/formato, sem presumir autorização fiscal ou reconciliação histórica. Manter a versão corrigida; rollback reintroduziria placeholders e não corrigiria as etiquetas existentes. Nenhum cancelamento/reenvio foi feito. Backlog de reconciliação: https://github.com/userTI10/hub-logistico/issues/14; o GitHub contém só resumo agregado, dados individuais ficam privados. Quota global Bling permanece na issue #10.

Rollback pronto: sudo -n python3 /home/ti-kiosk/hub-deploy/deploy-control.py rollback --environment production --state /home/ti-kiosk/hub-deploy/backups/production-20261008T183411Z-3cf7250a/state.json. Restaura código, preserva banco atual e inicia worker pausado; reativação depende de conciliação. Backup HML: /home/ti-kiosk/hub-deploy/backups/hml-20261008T183312Z-3cf7250a.

Evidências locais: C:/KIOSK/hub-logistico/.deploy-state/nota-final-results.json; nota-cross-audit.private.json; nota-pdf-all-results.private.json; PDFs em nota-labels.private. Esses arquivos não foram publicados. Esta atualização substitui o estado corrente descrito no registro anterior abaixo.

## Histórico da implantação anterior (12:06 de Brasília)


Estado validado em 08/10/2026. Revisão implantada 1111ea15eb9c67a6a17ef78c47cff0793a5f6dc6. Este documento representa HML; produção tem documentação própria em [[hub-producao]].

| Recurso | Valor verificado |
| --- | --- |
| Servidor | SRV-API |
| Diretório | /home/ti-kiosk/hub-homolog |
| PM2 | hub-homolog, online |
| Porta | 3001 |
| Banco | /home/ti-kiosk/hub-homolog/hub-homolog.db, quick_check=ok |
| URL | https://hub-hml.touticosmetics.com.br |
| Ambiente | HUB_ENV=hml |
| Worker/emissão | HUB_WORKER_ENABLED=0; /healthz confirma false |
| Conectores / fila | Sem conectores, fila vazia |
| Lojas | Todas com gerar_automatico=0 |

HTTP interno e público validado em três amostras. 49 arquivos conferidos pelo manifesto. Seed HML bloqueado e motor/adapter protegidos; não habilitar emissão real para teste.

A primeira ativação encontrou erro de cwd no CLI PM2/preload. Rollback restaurou código e preservou banco; HML voltou online pausada. Correção na PR #11, CI Node 18/20 e nova ativação aprovada. PM2 save executado.

HEAD local alinhado à versão implantada; diferenças Git remanescentes são de EOL, sem diferença de conteúdo ao ignorar finais de linha. A branch remota hml ainda está em b288985: promover revisão por PR antes de reutilizar o pipeline automático. Deploy atual foi manual e controlado.

Procedimento: [[post-deploy-observabilidade-hub]]. Resultado e rollback: [[deploy-validacao-hub-2026-10-08]]. Comparativo histórico anterior: [[comparativo-prod-homolog-postman]].

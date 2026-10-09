# Hub — Homologação

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

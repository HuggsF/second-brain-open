# Validação do deploy — 08/10/2026

As PRs [#1](https://github.com/userTI10/hub-logistico/pull/1), [#9](https://github.com/userTI10/hub-logistico/pull/9) e [#11](https://github.com/userTI10/hub-logistico/pull/11) foram integradas. Produção e homologação receberam 1111ea15eb9c67a6a17ef78c47cff0793a5f6dc6 pelo pacote Git exportado e transferido via SSH. SHA-256 do tar: 728c4fd7cc3c7ab5471eeb862bd97ed82c916ad30a28bfd23b74fed0c2b05593. Os 49 arquivos do manifesto de cada ambiente conferiram, sem divergência.

CI Node 18/20 aprovada: [execução da correção final](https://github.com/userTI10/hub-logistico/actions/runs/37796248467). São 26 cenários npm, três testes Python do controle/rollback e sete comparações offline. npm test também passou nos dois releases isolados usando Node 18.19.1 e dependências Linux existentes; lockfile não mudou.

## Ativação e observação
Horários de Brasília (UTC-3): HML validada às 11:57:56–59; produção validada pausada às 11:58:47–50; worker liberado às 11:59:21; fechamento às 12:06:25. GET /healthz interno e público confirmou SHA, ambiente, banco e política. Produção permanece ativa, só ES automática (conector 2); Recife e demais lojas desligadas. HML permanece HUB_ENV=hml e HUB_WORKER_ENABLED=0, lojas desligadas e fila vazia. PM2 save persistiu os estados.

Não houve reinício inesperado: contador produção 17 antes, 18 após a reinicialização autorizada de liberação, estável durante observação. SQLite quick_check=ok. Failed permaneceu 16; zero erro terminal novo, zero REVIEW_REQUIRED e zero emissão uncertain na janela. O processing antigo 4532 permanece desde 30/09, sem reprocessamento automático.

| Métrica em janela de cinco minutos | Antes: 11:52:05–11:57:05 | Depois: 11:59:21–12:04:21 |
| --- | ---: | ---: |
| 429 | 3 | 13 |
| GET / UPDATE 429 | 1 / 2 | 1 / 12 |
| Outros erros | 0 | 0 |
| Fluxos concluídos | 0 | 1 |
| Etiquetas novas | 1 | 2 |
| Reaproveitamentos registrados | 0 | 11 |

No fechamento ampliado até 12:06:25: dois pedidos concluídos, duas etiquetas confirmadas, 13 reaproveitamentos e 15 erros 429 (2 GET, 13 UPDATE). As duas linhas success têm rastreio da fila, payload e jt_emissions coincidentes. Os 772 success históricos com payload sem tracking ficaram preservados; nenhuma nova inconsistência foi identificada. Os logs confirmam UPDATE do Bling e conclusão; a interface fiscal do Bling não foi exercitada manualmente.

Há mais 429 na janela posterior. Volume e mistura de chamadas diferem; esses números não isolam causalidade nem provam melhoria do limitador. As proteções de emissão/reaproveitamento funcionaram no tráfego observado, mas rate limiting permanece pendência alta na [issue #10](https://github.com/userTI10/hub-logistico/issues/10). Não tratá-lo como resolvido por este deploy.

## Rollback pronto e testado
A primeira tentativa HML falhou porque o preload de pausa também alcança o CLI PM2 e ele foi iniciado fora do diretório da aplicação. O código foi restaurado, o banco preservado e HML voltou online pausada. A PR #11 corrigiu cwd e adicionou teste de regressão; a ativação foi repetida com sucesso. Produção só foi alterada após essa correção e aceite de HML.

Rollback de produção, se os critérios de docs/deploy-rollback.md forem violados:

```bash
sudo -n python3 /home/ti-kiosk/hub-deploy/deploy-control.py rollback --environment production --state /home/ti-kiosk/hub-deploy/backups/production-20261008T145704Z-1111ea15/state.json
sudo -n pm2 save
```

O comando para o processo, copia o banco atual com SQLite backup, restaura código anterior e inicia com worker pausado. Não restaura o banco pré-deploy. Reativação depende de reconciliação das etiquetas/intents/jobs e autorização operacional. Backups privados ficam fora da aplicação; não anexar dump PM2 nem banco a issues.

## Próximas ações e limites
Quota/cooldown por conta, OAuth single-flight e retomada por etapa: DEM-16. Recuperação de processing antigo/lease: DEM-09. Validade/conector de etiqueta: DEM-10. Contrato Corpem e volumes: DEM-12/13. Reconciliação automática: DEM-15. Não houve criação de pedido artificial ou cancelamento real para testar.

HML recebeu atualização manual controlada; HEAD local foi alinhado ao SHA implantado. Existem diferenças de final de linha em Git (sem diferença de conteúdo ao ignorar EOL); o manifesto do pacote confere integralmente. A branch remota hml ainda está em b288985: promover a revisão por PR antes de executar novamente o workflow HML, para evitar retorno à revisão anterior. Pipeline de produção automático não foi criado.

Evidências: evidencias/deploy-comparacao-janelas-2026-10-08.json, deploy-prod-observacao-final-2026-10-08.json, deploy-prod-health-final-2026-10-08.json e deploy-hml-health-2026-10-08.json. Logs PM2 por offset desde preparação incluem três 429 anteriores à troca; para atribuição pós-deploy usar os eventos SQLite por horário/id, sem somar as duas fontes.


Memória relacionada: [[hub-producao]], [[hub-homologacao]], [[post-deploy-observabilidade-hub]], [[rate-limiting-bling-producao]].

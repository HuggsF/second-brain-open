# Pipeline de homologação do Hub Logístico

Atualizado em 2026-10-08. Workflow existente no checkout; execução remota atual não revalidada.

## Comportamento implementado

Fonte: .github/workflows/deploy-hml.yml. Push em hml ou workflow_dispatch executa npm ci e testes com Node 20. Deploy via SSH depende do job de testes e atua exclusivamente em /home/ti-kiosk/hub-homolog: copia hub-homolog.db, sincroniza origin/hml, instala dependências, testa e executa pm2 reload hub-homolog.
Produção não é alvo desse workflow. Main exige PR. A execução #37678979439 de 2026-10-07 é registro histórico, sem nova verificação nesta revisão.

## Limites

pm2 reload não comprova zero downtime: depende de modo de execução, prontidão e saúde. A revisão local adiciona health check e observação pós-deploy; rollback automático permanece pendente. A cópia de SQLite ativo não comprova backup consistente; avaliar backup nativo/pausa controlada conforme journal.
O checkout remoto usa origin/hml após fetch, sem fixar o SHA testado; a revisão local serializa deploys HML e verifica o SHA carregado contra github.sha, falhando em caso de divergência. Token do Actions é gravado na URL remota e merece revisão própria.
A proposta anterior de deploy em produção foi substituída pela descrição do workflow real; mudanças em produção exigem revisão separada.

## Revisão local

Branch fix/fila-rastreios-hml adiciona proteção de concorrência, intenção persistida e bloqueio de homologação. Vinte cenários locais aprovados; sem deploy. HUB_ENV=hml é recomendado; o nome hub-homolog.db ativa proteção por compatibilidade. A suíte usa serviços simulados.
Referências: [[protecoes-processamento-emissao-hub]], [[backlog-analise-hub-logistico]], [[implantacao-instancia-homologacao]].

## Gate pós-deploy local

Após reload, três amostras verificam PM2, HTTP interno/público, revisão carregada, ambiente, bloqueio HML e SQLite somente para leitura. Falha impede sucesso do workflow, sem ação corretiva automática. Procedimento: [[post-deploy-observabilidade-hub]]. Aguardando implantação para comprovação remota.

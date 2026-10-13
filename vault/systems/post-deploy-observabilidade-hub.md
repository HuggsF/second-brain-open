---
type: system
status: active
date: 2026-10-09
---
# Observabilidade pós-deploy do Hub Logístico

Data: 2026-10-08. Implantado em HML e produção; observação aprovada com alerta de 429. Resultado e evidências em deploy-validacao-2026-10-08.md.

## Fluxo e critérios

1. Registrar horário UTC de início e SHA completo aprovado para implantação.
2. Executar CI, implantar em homologação e recarregar o processo pelo fluxo existente.
3. Coletar três amostras de PM2, HTTP interno, HTTPS público e SQLite aberto somente para leitura.
4. Comparar ambiente e SHA retornados por `/healthz`, disponibilidade do banco, reinícios, erros novos e aumento de jobs failed.
5. Emitir relatório JSON e código de saída 0 (aprovado) ou 1 (falhou). Falha bloqueia a conclusão do workflow. Investigar antes de nova implantação; o observador não reinicia processos, recupera jobs ou efetua rollback.

`/healthz` consulta SELECT 1 e retorna versão, ambiente, política de emissão, workerEnabled e revisão capturada na inicialização. Retorna 503 se o banco estiver indisponível. O pacote de deploy usa REVISION com SHA completo, inclusive em produção sem Git; sem marcador válido ou checkout a checagem falha. O SHA comprova a revisão declarada na inicialização; não verifica arquivos alterados manualmente no servidor. O controlador verifica o manifesto SHA-256 antes da cópia.

O coletor consulta o banco definido no ambiente/cwd do processo PM2, com fallback para configuração local. Não imprime configuração, pedidos, tokens ou conteúdo dos logs. Contadores incluem pending, processing, failed, erros desde o deploy e lojas automáticas. 429 recuperável é separado de erro terminal e gera aviso para verificar progresso e issue #10. Pending em HML é esperado porque o motor bloqueia processamento. Processing e lojas automáticas em HML geram aviso para conferência. Produção pausada exige --worker-enabled 0. A política e os comandos de rollback estão em deploy-rollback.md.

## Execução

Após disponibilizar esta revisão no servidor, executar no diretório do ambiente:

```bash
node scripts/post-deploy-check.js --environment hml --expected-sha SHA_COMPLETO --since HORARIO_UTC_INICIO
```

Produção: diretório `/home/ti-kiosk/hub`, argumento `--environment production`. Somente observar após uma implantação autorizada. Esta alteração não cria workflow de deploy de produção.

No Windows, usando o gateway MCP existente:

```powershell
C:\KIOSK\second-brain\.venv\Scripts\python.exe C:\KIOSK\second-brain\observability\post_deploy_mcp.py --environment hml --sha SHA_COMPLETO --since HORARIO_UTC_INICIO
```

O runner usa `srv_api_run_safe_command` do gateway `mcp_servers/srv_api_gateway_mcp.py` com comando fixo e argumentos validados/escapados. A janela MCP é de três amostras separadas por um segundo; timeouts de PM2 (3 s) e HTTP (4 s) limitam a coleta usual a menos de 30 s. Timeout de SSH ou ausência do script é falha de observabilidade, não aprovação. No Actions a janela usa intervalos de cinco segundos. Sem --since, somente erros desde o início da observação são contados; para validar o deploy informar o início real.

## Diagnóstico e limites

Falha HTTP externa: conferir DNS, TLS e Nginx; interna: processo/porta. SHA divergente: verificar checkout e processo realmente carregado. Reinícios/erros: inspecionar logs PM2 e system_logs sob controle de acesso, removendo dados pessoais antes de compartilhar. Falhas novas de fila: conferir jobs e intenção de emissão antes de reprocessar. Não criar pedido real para testar saúde.

A observação curta não substitui métricas contínuas, alertas ou reconciliação com J&T/Corpem. Há amostragem: falhas transitórias entre leituras podem passar despercebidas. O gateway atual tem blocklist de comandos, não allowlist de leitura, e aceita chave de host SSH automaticamente. Restringir comandos e fixar identidade do host ficam como pendências de governança; não tratar essa configuração como garantia de somente leitura.

## Evidência remota nesta sessão

MCP autenticado ao SRV-API; /healthz interno e público validado em ambos os ambientes na revisão 1111ea15eb9c67a6a17ef78c47cff0793a5f6dc6. Produção ativa e HML pausada. PM2 save executado após estabilidade. Erros 429 geraram aviso e a fila progrediu sem novas falhas ou inconsistências; ver deploy-validacao-2026-10-08.md.

Estado efetivo e política de rollback: [[deploy-validacao-hub-2026-10-08]], [[hub-producao]], [[hub-homologacao]].

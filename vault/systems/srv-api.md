# Servidor de Integração: SRV-API (Hub Central)

## Visão Geral
O **SRV-API** é o servidor Linux (Azure Ubuntu 24.04 LTS) que atua como o **Hub Central de Integrações** da holding KIOSK Brands. Ele concentra a comunicação entre os sistemas de vendas em lojas/quiosques, o ERP SAP, o Salesforce e os canais de leads e pagamentos.

## Serviços Críticos em Execução (systemd)
1. **`hub-sap.service` (Hub de Integração SAP):**
   - Responsável por intermediar chamadas e sincronizações de dados entre as APIs da holding e o ERP SAP.
2. **`salesforce-api.service` & `salesforce-celery.service`:**
   - Instância Gunicorn e workers Celery responsáveis por receber e processar webhooks do **Salesforce** de forma assíncrona.
3. **`api-saurus.service` (API Saurus):**
   - Integração com o sistema **Saurus**, gerenciando dados de lojas, faturamento diário, vendas e movimentação de estoque dos quiosques.
4. **`pm2-kiosk-webhookgetnet.service`:**
   - Receptor de webhooks de pagamento da adquirente **Getnet** para confirmação de transações financeiras.
5. **`facebook-leads-api.service`:**
   - Ingestão de leads de campanhas de expansão e novos franqueados vindos do Facebook Ads.
6. **Infraestrutura Base:**
   - `nginx.service` (Reverse Proxy e SSL)
   - `redis-server.service` (Broker de mensageria para o Celery e cache)

## Acesso e Governança
- **Acesso Técnico:** SSH via chave privada RSA (`SRV-API_key.pem`) com usuário `ti-kiosk`.
- **Gateway MCP de diagnóstico:** Integrado localmente via `mcp_servers/srv_api_gateway_mcp.py` para diagnósticos controlados de CPU, memória, status de serviços e leitura de logs (`srv_api_view_logs`).

## Hub e observabilidade — 2026-10-08

Processos PM2 hub-logistico e hub-homolog confirmados online por leitura via MCP nesta sessão. Documentos próprios: [[hub-producao]] e [[hub-homologacao]]. O runner de [[post-deploy-observabilidade-hub]] usa comando fixo de leitura. O gateway genérico usa blocklist, não allowlist, e AutoAddPolicy de SSH; pinagem de host e restrição de comandos pendentes.

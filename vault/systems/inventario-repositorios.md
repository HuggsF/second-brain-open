# Auditoria de Repositórios e Serviços: Servidor SRV-API

## Data da Auditoria
2026-10-07

## Resumo Executivo
Foi realizada uma varredura completa no servidor de produção `SRV-API` (`191.233.18.195`).  
**Constatação sobre Git:** Não existem pastas `.git` locais no servidor de produção. O código foi implantado via deploy direto de artefatos (tarball / rsync). Os repositórios oficiais com controle de versão estão na nuvem corporativa (GitHub/GitLab/Bitbucket da holding).

No entanto, foram mapeados **7 projetos/serviços ativos**, com seus códigos-fonte, documentações e arquiteturas detalhadas abaixo:

---

## 1. Hub de Integração SAP B1 (`hub-sap`)
* **Diretório:** `/opt/hub-sap` (produção systemd) e `/home/ti-kiosk/hub-sap`
* **Stack:** Node.js (>= 20.17), Express, SQLite (`hub.db`), Axios
* **Serviço Systemd:** `hub-sap.service`
* **Responsabilidade:**
  - Recebe payloads JSON (Kiosk Parser v2.1) vindos de formulários do Salesforce (Screen Flow) e webhooks.
  - Integra no **SAP Business One via Service Layer** em duas etapas:
    1. Criação do Parceiro de Negócio (`POST /BusinessPartners`).
    2. Atualização de tabelas adicionais UDO (`POST /HCO003`).
  - Gera o código do cliente consultando a última numeração de loja no SAP para as marcas **YES, AMAVIA e TOUTI**.

---

## 2. Hub Logístico Modular (`hub`)
* **Diretório:** `/home/ti-kiosk/hub`
* **Stack:** Node.js, Express, SQLite (`hub.db`), `pdf-lib`
* **Descrição no package.json:** `hub-logistico-v4-completo` (Bling -> J&T Express -> Corpem)
* **Responsabilidade:**
  - Emissão, cancelamento e listagem de etiquetas de envio com a transportadora **J&T Express**.
  - Integração com o operador logístico **Corpem**.
  - Geração de PDFs de etiquetas para os pedidos expedidos aos quiosques.

---

## 3. Webhook API Salesforce (`salesforceapi`)
* **Diretório:** `/home/ti-kiosk/salesforceapi`
* **Stack:** Python 3 (Flask, Gunicorn, Celery, Redis local na porta 6379, `xmltodict`)
* **Serviços Systemd:** `salesforce-api.service` (Porta 8010) e `salesforce-celery.service`
* **Responsabilidade:**
  - Recebe webhooks em formato XML do Salesforce.
  - Enfileira no Redis e processa em background via Celery.
  - Converte XML para JSON e dispara para os endpoints das marcas (ex: Touti).

---

## 4. API Saurus (`api-saurus`)
* **Diretório:** `/home/ti-kiosk/api-saurus`
* **Stack:** Python 3 (FastAPI, Uvicorn, pyodbc, SQL Server)
* **Serviço Systemd:** `api-saurus.service` (Porta 8020)
* **Responsabilidade:**
  - Camada de leitura direta sobre o banco SQL Server `dbsaurus_touticosmetics`.
  - Expõe vendas, estoque e faturamento das lojas/quiosques para clientes e franqueados da Kiosk Brands via autenticação por chaves individuais.

---

## 5. API de Leads e Extração E-commerce (`apileads`)
* **Diretório:** `/home/ti-kiosk/apileads`
* **Stack:** Python 3 (FastAPI, Uvicorn, SQLite `meta_leads.db`, Pandas/Excel)
* **Serviços Systemd:** `facebook-leads-api.service` (Porta 8000) e `leadecommerce.service` (Porta 8001)
* **Responsabilidade:**
  - Coleta automática de leads de campanhas de expansão de franquias do Facebook Ads.
  - Exportação e relatórios consolidados em planilhas Excel para a equipe comercial.

---

## 6. Webhook Getnet (`webhook-getnet-prod`)
* **Diretório:** `/home/ti-kiosk/webhook-getnet-prod`
* **Stack:** Node.js ES Modules (Node 22), PM2
* **Serviço Systemd:** `pm2-kiosk-webhookgetnet.service`
* **Responsabilidade:**
  - Recepção e validação de notificações de pagamento da adquirente **Getnet** para fechamento de pedidos.

---

## 7. Integração Bling / J&T (`bling`)
* **Diretório:** `/home/ti-kiosk/bling`
* **Stack:** Node.js, Express, Axios
* **Responsabilidade:**
  - API de apoio para despachos logísticos no ERP Bling e transportadora J&T Express.

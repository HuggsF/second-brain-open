---
type: system
status: active
date: 2026-10-09
---
# Postman Collection: Hub Logístico & Integrações

Esta coleção do Postman foi estruturada para permitir o teste unitário de cada requisição individual das APIs do **Hub Logístico**, **Bling ERP v3** e **J&T Express**, sem depender do fluxo completo automatizado.

---

## Arquivos Gerados no Repositório

* **Collection (v2.1.0):** [`hub-logistico/postman/Hub_Logistico_API.postman_collection.json`](file:///C:/KIOSK/hub-logistico/postman/Hub_Logistico_API.postman_collection.json)
* **Environment (HML):** [`hub-logistico/postman/Hub_Logistico_HML.postman_environment.json`](file:///C:/KIOSK/hub-logistico/postman/Hub_Logistico_HML.postman_environment.json)

---

## Estrutura das Pastas da Collection

### 1. `Hub Logístico (APIs do Hub)`
Permite testar o comportamento do servidor em Homologação (`https://hub-hml.touticosmetics.com.br`):
* **Simular Webhook Bling (`POST /api/webhook/bling`):** Dispara o webhook simulando um pedido com situação `Atendido` (id 9). Verifica se entra na fila `orders_queue`.
* **Simular Pedido Cancelado (`POST /api/webhook/bling`):** Envia situação `Cancelado` (id 12) e valida se a fila aborta o processamento.
* **Disparo Manual (`POST /api/enviar`):** Envia uma lista de IDs para forçar o processamento imediato.
* **Listar Fila & Contadores (`GET /api/pedidos`):** Consulta status da fila, erros e sucessos.
* **Obter PDF da Etiqueta (`GET /api/etiqueta/:queueId/pdf`):** Baixa o binário do PDF da J&T para impressão.
* **Listar & Alternar Lojas (`GET /api/lojas`):** Inspeciona quais lojas estão em modo automático ou manual.
* **Consultar Logs (`GET /api/logs`):** Consulta a tabela `system_logs`.

---

### 2. `Bling ERP v3 (Endpoints Oficiais)`
Permite disparar chamadas diretas para a API oficial do Bling com token OAuth2:
* **Buscar Pedido por ID (`GET /Api/v3/pedidos/vendas/:id`):** Inspeciona o payload bruto do Bling (volumes, transportadora, chave de NF-e).
* **Listar por Situação (`GET /Api/v3/pedidos/vendas`):** Filtra pedidos com `idsSituacoes[]=9` ("Atendido").
* **Buscar Objeto de Logística (`GET /Api/v3/logisticas/objetos/:id`):** Verifica se o volume já possui código de rastreio gravado.
* **Gravar Rastreio (`PUT /Api/v3/logisticas/objetos/:id`):** Testa a atualização de código de rastreamento no volume.

---

### 3. `J&T Express (Endpoints com Assinatura MD5)`
*Possui Pre-request Script configurado para calcular automaticamente o digest MD5 e os headers de autenticação da J&T:*
* **Gerar Etiqueta (`POST /addOrder`):** Envia payload de emissão de frete. Retorna o `billCode` oficial (`code: "1"`).
* **Consultar por BillCode (`POST /getOrders`):** Consulta histórico de rastreio de uma etiqueta da J&T.
* **Imprimir Etiqueta (`POST /printOrder`):** Retorna o base64 da etiqueta de postagem.

---

## Como Importar no Postman:

1. Abra o **Postman**.
2. Clique no botão **Import** (canto superior esquerdo).
3. Selecione os dois arquivos da pasta `C:\KIOSK\hub-logistico\postman\`:
   * `Hub_Logistico_API.postman_collection.json`
   * `Hub_Logistico_HML.postman_environment.json`
4. Selecione o ambiente **"Hub Logístico — [HML] Homologação"** no seletor do topo direito.
5. Preencha seus tokens e credenciais caso deseje chamar os endpoints diretos da J&T e Bling.

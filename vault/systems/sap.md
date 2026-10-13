---
type: system
status: active
date: 2026-10-09
---
# Sistema ERP: SAP (KIOSK Brands)

## Visão Geral
O **SAP** é o ERP central da holding KIOSK Brands. Ele processa as transações financeiras, contábeis, faturamento e gestão de inventário de produtos cosméticos e perfumaria para as marcas do grupo (**Touti**, **Amavia** e **Yes! Cosméticos**).

## Ponto Crítico de Dor: Falta de Tracking de Pedidos
Atualmente, quando um quiosque ou franquia realiza um pedido de reposição de estoque:
- O pedido entra no fluxo de faturamento do SAP.
- **Não há tracking em tempo real:** O franqueado não tem visibilidade se o pedido está "Aprovado", "Em Separação", "Faturado", "Expedido" ou "Em Rota de Entrega".
- **Impacto no Suporte:** Esse vazio de informação gera uma enxurrada de chamados no suporte (atualmente no SULTS), sobrecarregando a equipe da holding com perguntas repetitivas (*"Onde está meu pedido nº 12345?"*).

## Estratégia de Engenharia Proposta
1. **Camada de Integração via MCP:**
   - Criar um MCP Server local seguro para o SAP que consulta o status de ordens de venda e notas fiscais por CNPJ/ID do quiosque sem expor credenciais no frontend.
2. **Exposição para Salesforce & Agentes:**
   - Sincronizar eventos de status de pedido do SAP para o Salesforce.
   - Criar um **Agente de Acompanhamento de Pedidos** capaz de responder ao franqueado no Teams/WhatsApp/Salesforce automaticamente.

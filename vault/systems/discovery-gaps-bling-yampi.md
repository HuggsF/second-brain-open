---
type: system
status: active
date: 2026-10-09
---
# Discovery Técnico: Gaps Estruturais Bling ERP & Checkout Yampi

**Data:** 07/10/2026  
**Origem:** Reunião de Alinhamento e Discovery com Operação E-commerce, Gestão (Tadeu / Davi) e Engenharia  
**Contexto:** Ecossistema Touti Cosmetics (Shopify ➔ Yampi ➔ Bling ➔ Hub Logístico ➔ Transportadoras)

---

## GAP 1: Cadastro do Hub Logístico no Bling (Aplicativo de Logística vs. Usuário de API)

### 1.1. O que foi relatado pela Operação
> *"O hub de Tadeu está cadastrado no Bling apenas como API e não como Aplicativo de Logística. Por causa disso, as informações do hub não saem nativamente nas telas fiscais e de expedição do Bling... não aparece o campo da transportadora nem o objeto de postagem preenchido na interface da logística."* (min 20:58 e 25:25)

### 1.2. Diagnóstico Técnico & Causa Raiz
No ecossistema do Bling ERP, existem duas modalidades distintas de acoplamento:
1. **Integração Externa via REST API (Estado Atual):**
   * O Hub conecta via credenciais OAuth2 (`clientId`, `clientSecret`, `refreshToken`) como um consumidor externo de API.
   * O Hub consegue ler dados do pedido (`GET /pedidos/vendas/{id}`) e atualizar campos customizados ou disparar atualização de rastreamento.
   * **Limitação:** Como o Hub não está registrado como um *Provedor de Serviços de Logística nativo* dentro do Bling (Menu: *Configurações > Logística > Integrações Logísticas*), o Bling trata a expedição como manual. O operador não vê botões de "Gerar Remessa", "Imprimir Etiqueta Nativa" ou vínculo do serviço de entrega na tela de expedição fiscal.
2. **Aplicativo de Logística Homologado no Bling (Objetivo):**
   * Um conector cadastrado sob a estrutura de Logística/Transportadora no Bling.
   * Permite que o Bling reconheça o Hub ou a J&T como o método oficial de frete do pedido, preenchendo automaticamente o `servicoEntrega`, transportadora padrão e objeto de postagem direto na NF-e.

### 1.3. Impacto Operacional
* Operadores de expedição precisam alternar entre telas do Bling e do Hub ou verificar manualmente se o rastreio foi preenchido.
* Risco de pedidos serem despachados ou faturados sem que o vínculo da transportadora conste na nota fiscal.

### 1.4. Plano de Ação Proposto
1. Mapear na documentação do Bling v3 a estrutura de **Integração Logística Customizada / Webhook de Logística**.
2. Avaliar se o Hub deve:
   * (A) Registrar as transportadoras diretamente no Bling e fazer o Hub apenas preencher a PLP/Objeto via endpoint oficial de logística; OU
   * (B) Criar o aplicativo privado no portal de desenvolvedores do Bling cadastrado com escopo de Logística.
3. Alinhar com Tadeu o modelo atual do conector e documentar os campos fiscais exigidos pela expedição de Recife e Espírito Santo.

---

## GAP 2: Pedidos Aprovados na Yampi que não Entram no Bling

### 2.1. O que foi relatado pela Operação
> *"Tem pedido que está aprovado e pago na Yampi, mas não aparece no Bling, ou demora horas para aparecer. Se a sincronização falha, a gente só descobre quando o cliente reclama no SAC... temos que ir manualmente na Yampi caçar o pedido."* (min 27:04 e 27:32)

### 2.2. Diagnóstico Técnico & Hipóteses de Falha
O fluxo natural é: `Yampi (Pagamento Aprovado) ➔ Webhook/Integração Yampi ➔ Bling (Criação de Pedido de Venda)`.

Quando um pedido "some" entre a Yampi e o Bling, as causas mais frequentes na arquitetura são:
1. **Divergência de SKU / Variação de Produto:**
   * Se o SKU vendido na Yampi (vindo da Shopify) não tiver correspondente idêntico cadastrado no Bling, a API do Bling rejeita a criação do pedido (`HTTP 400 - Produto não encontrado`).
2. **Inconsistência Cadastral do Cliente:**
   * O Bling v3 possui validações estritas de CPF/CNPJ, CEP com 8 dígitos e campos de endereço obrigatórios (bairro, número). Se o cliente preencher algo inconsistente na Yampi, a integração quebra silenciosamente.
3. **Rate Limit da API do Bling (3 req/s):**
   * Em momentos de pico de vendas ou concorrência com o próprio Hub consumindo a API, a Yampi recebe `HTTP 429 - Too Many Requests`. Se as retentativas automáticas da Yampi expirarem, o pedido fica com status "Falha na Sincronização" travado no painel da Yampi.
4. **Falta de Observabilidade / Alerta Passivo:**
   * Não existe hoje um robô ou rotina que compare:
     `Contagem de Pedidos Pagos na Yampi (últimas 24h) VS Pedidos Criados no Bling`.

### 2.3. Impacto Operacional
* Lead time de entrega estourado: pedidos pagos ficam dias parados sem faturamento.
* Sobrecarga do SAC e atrito direto com clientes.

### 2.4. Plano de Ação Proposto
1. **Auditoria de Falhas na Yampi:** Acessar o painel da Yampi (*Integrações > Bling > Logs de Erro / Pedidos Não Sincronizados*) para catalogar as 3 maiores razões de rejeição no Bling.
2. **Criação de Conciliador de Pedidos (Robô de Reconferência):**
   * Criar uma rotina agendada (cron) que consulta pedidos pagos na Yampi via API e verifica se o ID ou número do pedido já existe no Bling.
   * Se encontrar pedidos com mais de 30 minutos sem correspondente no Bling, disparar alerta no Teams ou enfileirar para reprocessamento automático.

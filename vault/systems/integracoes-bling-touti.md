# Integrações Bling — Touti (Second Brain)

## Visão geral

A integração J&T Express está quase toda montada na conta Bling TOUTI, mas faltam a permissão de Cadastros do usuário de integração, os dados fiscais do transportador e a autorização do app pela J&T. Este doc é a página-mãe das integrações Bling no second brain: inventário, diagnóstico e referência dos manuais da J&T.

> **ALERTA URGENTE**: a Bling migra a autenticação da API para JWT em **15/10/2026** (6 dias). Apps de terceiros ou próprios (J&T Express, n8n, ETL API, CLAUDE CODE, eComerce Touti, Mktplaces app Mercado Antigo, Unbox) precisam ser adequados antes dessa data; apps nativos como Mercado Livre e Shopee não são afetados.

| Item | Valor |
|---|---|
| Conta Bling | TOUTI (domínio de login: touticosmetics) |
| Usuário que configurou | TI KIOSK, em 11/06/2026 |
| Fontes | Manual "Integração Bling V3 - 2026" (J&T, 23 p.) e "Create Order / Criação de pedido" (J&T, 14 p.) |
| Levantamento na Bling | Somente leitura, feito em 09/10/2026 |

---

## Inventário de integrações

A conta tem **24 instalações** e **7 apps próprios** cadastrados (limite: 30); **6 instalações estão como "Não autenticado"**. O selo de autenticação só aparece em apps via API; integrações nativas não mostram selo.

| Integração | Categoria | Tipo | Status | Afetada pelo JWT |
|---|---|---|---|---|
| eComerce Touti | Marketplace | App próprio | Não autenticado | Sim |
| Frenet Integração e Gestão de Entregas | Gestão de entregas | Terceiro | Não autenticado | Sim |
| Prax | Dashboards e BI | Terceiro | Não autenticado | Sim |
| CLAUDE CODE | Soluções em IA | App próprio | Não autenticado | Sim |
| ETL API | ERP | App próprio | Não autenticado | Sim |
| Troque e Devolva | Outro | Terceiro | Não autenticado | Sim |
| Mktplaces app Mercado Antigo | Marketplace | App próprio | Autenticado | Sim |
| Integrai | Hub | Terceiro | Autenticado | Sim |
| n8n | Soluções em IA | App próprio | Autenticado | Sim |
| J&T EXPRESS | Outro (Logística Personalizada) | Nativa Bling | Ativa | O app "J&T Express" sim |
| integração | Outro (Logística Personalizada) | Nativa Bling | Ativa | Não |
| Mercado Livre | Marketplace | Nativa | Ativa | Não |
| Touti Tiktok Shop | Marketplace | Nativa | Ativa | Não |
| Loja Virtual TikTok 02 | Marketplace | Nativa | Ativa | Não |
| AMAVIA-SHOPIFY | Plataforma de e-commerce | Nativa | Ativa | Não |
| Touti Loja VIP | Plataforma de e-commerce | Nativa | Ativa | Não |
| Correios | Gestão de entregas | Nativa | Ativa | Não |
| Frenet | Gestão de entregas | Nativa | Ativa | Não |
| Frenet_VIP_Shopify | Gestão de entregas | Nativa | Ativa | Não |
| Loggi | Gestão de entregas | Nativa | Ativa | Não |
| Logística TikTok Shop (2 instâncias) | Gestão de entregas | Nativa | Ativa | Não |
| Mercado Livre (logística) | Gestão de entregas | Nativa | Ativa | Não |
| Total | Gestão de entregas | Nativa | Ativa | Não |

Apps próprios na Área do Integrador (todos privados e aprovados): Unbox, n8n, ETL API, J&T Express, CLAUDE CODE, eComerce Touti, Mktplaces app Mercado Antigo. Unbox está cadastrado, mas não aparece instalado.

**Perguntas em aberto**: as duas instâncias "Logística TikTok Shop" e as três Frenet são todas usadas? A "integração" (Logística Personalizada) serve a qual transportadora?

---

## Integração J&T Express — diagnóstico

Dos 20 passos do manual, **4 têm pendência**: o cadastro fiscal do transportador, a permissão de Cadastros do usuário jt, a categoria do app e a autorização do app pela J&T.

| Passos | O que pede o manual | Situação na conta | Status |
|---|---|---|---|
| 1–3 | Transportador J&T com CNPJ, IE, Contribuinte 1, endereço | Cadastro existe, sem CNPJ/IE/endereço; Contribuinte=9 | **Pendente** |
| 4 | ID do transportador enviado ao TI J&T | ID 18197580249 | OK (confirmar envio) |
| 5–6 | Logística Personalizada "J&T EXPRESS" | Código logística API 1016341 | OK |
| 7–8 | Serviço J&T Standard ligado ao transportador | Serviço ativo, ID 14899116069 | OK |
| 9–11 | App privado; categoria Gestão de entregas | Categoria "Nenhuma das opções anteriores" | **Ajustar** |
| 12 | Escopos logísticos e fiscais | Todos presentes | OK |
| 13 | Contato do desenvolvedor | J&T Express com e-mail e celular | OK |
| 14 | Client ID/Secret/convite enviados ao TI | App não em Minhas Instalações | **Verificar** |
| 15–17 | Usuário jt@domínio | Usuário jt@touticosmetics | OK |
| 18 | Cadastros > Clientes e Fornecedores: todos | Todos desmarcados | **Pendente** |
| 19 | Vendas: escopos logísticos e fiscais | Todos marcados | OK |
| 20 | Enviar 6 dados + pedido teste | Sem registro | **Verificar** |

---

## Pendências e próximos passos

> **Primeiro passo**: confirmar com o TI da J&T a adequação ao JWT antes de 15/10/2026.

- [ ] Perguntar ao TI J&T se o app já está vinculado no JMS e se a conexão está adequada ao JWT
- [ ] Confirmar se os 6 dados do passo 20 foram enviados
- [ ] Usuário jt: marcar todas as permissões de Cadastros > Clientes e Fornecedores
- [ ] Transportador: preencher CNPJ, IE, Contribuinte 1 e endereço conforme o manual
- [ ] App J&T Express: mudar categoria para Gestão de entregas
- [ ] Gerar pedido teste com fone do remetente/destinatário, transportadora antes da NF e peso bruto
- [ ] Avisar responsáveis dos demais apps afetados pelo JWT (n8n, ETL API, CLAUDE CODE, etc.)
- [ ] Decidir o destino das 6 instalações "Não autenticado"

---

## Contexto: Hub Logístico como Aplicativo

O Hub Logístico atualmente consome a API Bling v3 diretamente (como API pura), e **precisa se tornar um aplicativo registrado** na Bling para:

1. Conformidade com a migração JWT (15/10/2026)
2. Gerenciamento adequado de escopos e permissões
3. Separação de credenciais entre produção e homologação

O app **J&T Express** na área do integrador (Client ID/Secret já existem) é o candidato natural, ou pode ser necessário um app dedicado para o Hub.

---

## Referência: manual Integração Bling V3 (J&T)

O manual liga a Bling ao sistema JMS da J&T em 20 passos, divididos em cinco blocos:

1. **Transportador (1–4)**: Cadastros > Clientes e Fornecedores. J&T EXPRESS BRAZIL LTDA, CNPJ 42.584.754/0001-86, IE 133512711118, Contribuinte 1 — ICMS. Endereço: Av. Eng. Luiz Bernini, 105, Cidade Monções, São Paulo/SP, CEP 04571-900.
2. **Logística Personalizada (5–8)**: Central de Extensões > "Logística Personalizada" > nome "J&T EXPRESS". Serviço J&T Standard, contato J&T EXPRESS BRAZIL LTDA.
3. **App de integração (9–14)**: Área do Integrador > Criar Aplicativo > Privado. Categoria Gestão de entregas, escopos logísticos e fiscais.
4. **Usuário de integração (15–19)**: login jt@domínio. Permissões de Cadastros e Vendas.
5. **Envio ao TI J&T (20)**: ID transportador, Client ID, Client Secret, link de convite, domínio, senha.

---

## Referência: API J&T — Create Order

Documentação oficial: open.jtjms-br.com. A API serve para criar pedidos direto no JMS sem passar pela Bling.

### Campos principais

| Campo | Valor padrão / regra |
|---|---|
| customerCode | Código do cliente (começa com "J") |
| txlogisticId | Nº do pedido do cliente; sai na etiqueta |
| expressType | "EZ" (tabela de preços) |
| orderType | "2" (cobrança mensal) |
| serviceType | "02" (modelo de operação) |
| deliveryType | "03" (modelo de entrega) |
| weight | Peso bruto com ponto decimal, máx. 2 casas |
| totalQuantity | Quantidade de volumes |

### Tipos de documento fiscal (docType)

| docType | Documento | Campos obrigatórios |
|---|---|---|
| 0 (padrão) | NF-e | invoiceNumber, invoiceSerialNumber, invoiceMoney, invoiceAccessKey, taxCode |
| 1 | Declaração de conteúdo (DC) | invoiceNumber, invoiceMoney, invoiceIssueDate |
| 20 | DC-e | invoiceAccessKey, invoiceMoney, invoiceIssueDate |

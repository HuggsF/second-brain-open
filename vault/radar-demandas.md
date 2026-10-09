# 🧭 Radar de Demandas & Multi-Frentes (KIOSK Brands)

Este painel central permite acompanhar todas as demandas ativas em paralelo pelas marcas e ecossistemas (Touti, Amavia, Yes! Cosmetics, Holmes, Sults, SAP, etc.) sem perda de contexto.

---

## 🚦 Status Atual das Demandas

| ID | Frente / Sistema | Demanda / Iniciativa | Status | Responsável Atual | Bloqueio / Próximo Passo | Doc / Evidência |
| :---: | :--- | :--- | :---: | :---: | :--- | :---: |
| **DEM-01** | Touti / Hub Logístico | Correção de Duplicidade de Etiquetas J&T Express | `#status/doing` | Hugo Melo | Fix de NF deployado (10/10 reconciliados). Fix dedup INTEGER vs TEXT commitado (branch `fix/nota-fiscal-jt`, `e60344d`), deploy pendente. 44 pedidos com tracking duplicado + 529 com potencial divergência Hub ≠ Bling identificados. Evidência de correção em lote validada (pedido 27055321029). | [[investigacao-duplicidade-etiquetas]] |
| **DEM-02** | Infra / SRV-API | Implantação do Ambiente de Homologação (Porta 3001) | `#status/done` | Hugo Melo | DNS propagado e SSL Let's Encrypt ativo (`https://hub-hml.touticosmetics.com.br`) | [[implantacao-instancia-homologacao]] |
| **DEM-03** | Touti / Bling ERP | Configuração de Webhook de Testes em Homologação | `#status/pending` | Equipe Bling / Admin | Apontar webhook no Bling para `https://hub-hml.touticosmetics.com.br/api/webhook/bling` | [[implantacao-instancia-homologacao]] |
| **DEM-04** | DevOps / GitHub | Pipeline CI/CD e Observabilidade | `#status/done` | Hugo Melo | CI Node18/20 aprovada; prod controlado com pausa; promover branch hml antes do próximo Actions | [[proposta-pipeline-ci-cd-github-actions]] |
| **DEM-05** | Amavia / E-commerce | Mapeamento Inicial de Repositórios & Arquitetura | `#status/backlog` | Hugo Melo | Aguardando alinhamento de prioridades | [[inventario-repositorios]] |
| **DEM-06** | Yes! Cosmetics | Integração de Dados & Conectores | `#status/backlog` | Hugo Melo | Aguardando demandas iniciais | [[inventario-repositorios]] |
| **DEM-07** | Touti / Bling ERP | Modelagem do Hub como Aplicativo Logístico vs. API | `#status/backlog` | Hugo Melo / Tadeu | Exibir campos nativos de transportadora/objeto na interface fiscal do Bling | [[discovery-gaps-bling-yampi]] |
| **DEM-08** | Touti / E-commerce | Conciliação e Monitoramento de Pedidos Yampi ➔ Bling | `#status/backlog` | Hugo Melo | Investigar causas de perda de pedidos pagos e criar alertas | [[discovery-gaps-bling-yampi]] |
| **DEM-09** | Hub / Fila | Exclusividade do processamento | `#status/doing` | A definir | Reserva implantada/validada; lease e job4532 pendentes | [[backlog-analise-hub-logistico#DEM-09 Exclusividade do processamento da fila]] |
| **DEM-10** | Hub / Etiquetas | Validade do rastreio e cancelamento | `#status/doing` | A definir | Bloqueios implantados; validade/conector pendentes | [[backlog-analise-hub-logistico#DEM-10 Validade do rastreio reutilizado e cancelamento]] |
| **DEM-11** | Hub / Homologação | Inicialização segura de banco novo | `#status/doing` | A definir | Seed testado e HML bloqueada; sandbox pendente | [[backlog-analise-hub-logistico#DEM-11 Inicialização segura do banco de homologação]] |
| **DEM-12** | Hub / Corpem | Contrato universal de separação | `#status/backlog` | A definir | Obter contrato WMS e validar adapter | [[backlog-analise-hub-logistico#DEM-12 Contrato universal de separação e adapter Corpem]] |
| **DEM-13** | Hub / Volumes | Volumes ausentes e múltiplos | `#status/backlog` | A definir | Pendente de definição operacional | [[backlog-analise-hub-logistico#DEM-13 Volumes ausentes e múltiplos volumes]] |
| **DEM-14** | Second Brain | Modelo e visualização do grafo | `#status/doing` | A definir | Dashboard validado; catálogo e GraphRAG em evolução | [[modelo-semantico-e-visualizacao-grafo]] |
| **DEM-15** | Hub / J&T | Reconciliação de emissão incerta | `#status/doing` | A definir | Intenção persistida; reconciliação automática pendente | [[backlog-analise-hub-logistico#DEM-15 Reconciliação da emissão externa sem resposta persistida]] |

| **DEM-16** | Hub / Bling | Rate limiting por conta e recuperação | `#status/blocked-externo` | Tadeu / Comercial Bling | Plano Elite (R$1.250/mês) necessário para ampliar limite; comercial Bling entrará em contato com Tadeu | [[rate-limiting-bling-producao]] |
| **DEM-17** | Hub / Webhook | Dedup INTEGER vs TEXT — 44 duplicatas + 529 divergências | `#status/doing` | Hugo Melo | Causa raiz: `pedidoWebhook.id` (number) vs `erp_id` (text) no SQLite. Fix commitado `e60344d`, deploy pendente. Correção em lote dos 44+529 pedidos afetados com evidência validada. | [[investigacao-duplicidade-etiquetas]] |

---

## 🏷️ Dicionário de Tags de Status
- `#status/doing` ➔ **Comigo agora** (estou ativamente desenvolvendo ou testando).
- `#status/blocked-externo` ➔ **Bloqueado por terceiros** (esperando DNS, chave de API, aprovação de gerente, resposta de fornecedor).
- `#status/pending` ➔ **Pronto para iniciar** assim que a dependência destravar.
- `#status/done` ➔ **Entregue e homologado** (com evidência e documentação linkada).
- `#status/backlog` ➔ **Mapeado no Discovery** (iniciativa estruturada com causa raiz e plano de ação).

---

## 🔄 Fluxo de Auditoria Semanal
Toda sexta-feira ou antes de reuniões com Tadeu/Davi:
1. Filtrar o que está em `#status/blocked-externo` para cobrar os responsáveis no chat.
2. Mover o que foi homologado para `#status/done`.
3. Atualizar a coluna **Bloqueio / Próximo Passo** para dar visibilidade imediata em 30 segundos.


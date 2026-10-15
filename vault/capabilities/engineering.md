---
type: capability
status: active
date: 2026-10-13
---
# Capacidade: Engenharia de Software

## Escopo
Codificação, evolução e sustentação de todas as aplicações e integrações da KIOSK Brands. Atuando no modelo **Full-Cycle Developer** (equipe enxuta composta pelo desenvolvedor e seu superior técnico), esta capacidade cobre de ponta a ponta a entrega de software de alta confiabilidade: do entendimento do requisito de negócio à implementação, testes preliminares e instrumentação para observabilidade.

- **Equipe:** Composta por 2 desenvolvedores responsáveis por todo o ecossistema de código.
- **Filosofia:** Propriedade total do ciclo de vida do código (*You build it, you run it*). O desenvolvedor não é apenas um implementador de tickets, mas um resolvedor de problemas técnicos e de negócios.
- **Foco:** Máxima automação, código enxuto, tipagem estrita, contratos explícitos, concorrência segura e idempotência em todas as operações de escrita (evitando retrabalho e prejuízo financeiro operacional).

## Sistemas sob responsabilidade
- [[hub-producao]] — Hub Logístico em Produção (APIs de despacho, emissão e rastreamento)
- [[hub-homologacao]] — Instância de Homologação do Hub
- [[srv-api]] — Servidor central de APIs e webhooks
- [[integracoes-bling-touti]] — Microserviços de integração Bling ERP para Touti Cosmetics
- [[second-brain-frontend-waves]] — Interface de visualização operacional e fluxos
- [[second-brain-frontend-360]] — Visão 360 integrada de pedidos, franqueados e logística
- [[second-brain-graphrag-multiagent]] — Arquitetura semântica e multiagente
- [[second-brain-observability-bff]] — Backend for Frontend de telemetria e auditoria

## Regras e Diretrizes do Time (System Design & Concorrência)
1. **Idempotência Obrigatória com Chave Única:** Qualquer endpoint ou job que emita etiquetas, notas ou atualize status de pedidos deve exigir `Idempotency-Key` e gravar travas atômicas no banco contra execução concorrente ou duplicada ([[protecoes-processamento-emissao-hub]], [[PB-006-transacoes-distribuidas-saga-outbox]]).
2. **Padrão Transacional Outbox:** Nunca executar chamadas de rede externas síncronas dentro da transação ACID do banco. O disparo de eventos deve ser registrado na tabela outbox na mesma transação da entidade ([[03-sistemas-distribuidos-eventos-concorrencia]]).
3. **Orquestração de Sagas:** Transações distribuídas que tocam múltiplos serviços (Hub, Bling, SEFAZ, Transportadoras) devem implementar o padrão Saga com compensações reversas automáticas ([[PB-006-transacoes-distribuidas-saga-outbox]]).
4. **Respeito a Rate Limits com Filas de Controle:** Chamadas à Bling API v3 e parceiros devem ser encapsuladas por filas Token Bucket com buffers controlados ([[rate-limiting-bling-producao]], [[01-redes-gateways-comunicacao]]).
5. **CQRS em Consultas de Alto Desempenho:** Segregar estritamente endpoints de comando (escrita transacional) de endpoints de consulta (modelos de leitura desnormalizados ou cacheados).
6. **Cache-Aside Defensivo:** Consultas frequentes usam Cache-Aside com TTL estrito e travas de mutex no cache miss para impedir colapso do banco (*Cache Stampede*) ([[02-persistencia-storage-consistencia]]).
7. **Separar Negócio de Tecnologia:** Demandas de negócio vindas de Logística, ERP ou CRM são traduzidas em tarefas técnicas com critérios de aceite claros antes de qualquer codificação.

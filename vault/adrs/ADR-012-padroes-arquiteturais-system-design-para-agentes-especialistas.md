---
type: adr
status: Aceito
date: 2026-10-12
---
# ADR-012: Adoção de Padrões Arquiteturais de System Design para os 4 Agentes Especialistas

## Contexto
O ecossistema de software e inteligência operacional da KIOSK Brands (Hub Logístico, integrações Bling v3, Touti Cosmetics, SAP, Salesforce e o próprio Second Brain) lida com desafios crescentes de escala, concorrência distribuída, limites de vazão de APIs parceiras (*rate limiting*) e tolerância a falhas. 

Historicamente, incidentes como duplicidade de etiquetas de frete (ex: DEM-17 decorrente de divergência de tipos INTEGER vs TEXT) e lentidão em integrações revelaram que decisões técnicas precisam ser norteadas por **padrões formais de arquitetura de sistemas distribuídos** (*System Design*).

A ingestão completa da formação **Descomplicando System Design** (30 módulos, 254 aulas, 42.72 horas) forneceu o repertório técnico e os playbooks operacionais necessários para padronizar as decisões dos 4 Agentes Especialistas da holding:
1. **Agente DEV:** Desenvolvimento Full-Cycle e integrações de microsserviços.
2. **Agente DEVOPS:** Confiabilidade de infraestrutura, deploys contínuos e SRE.
3. **Agente QA:** Testes de carga, estresse, breakpoint e garantias de qualidade.
4. **Agente PRODUTO / ARQUITETURA:** Planejamento de capacidade, trade-offs de negócio e governança de dados.

## Decisão
Adotar oficialmente a taxonomia e os padrões de System Design estruturados nos 6 Eixos Temáticos do Second Brain (`vault/architecture/system-design/`), com diretrizes mandatórias para cada agente:

### 1. Diretrizes para o Agente DEV
- **Idempotência Estrita com Chaves Únicas:** Todo endpoint mutável ou consumidor de webhooks deve implementar verificação de `Idempotency-Key` antes de processar regras de negócio, eliminando duplicidade de pedidos e etiquetas ([[PB-006-transacoes-distribuidas-saga-outbox]]).
- **Padrão Transacional Outbox:** Eliminação de *Dual-Write*. Escritas locais no banco de dados e disparo de eventos devem ser comitados atomicamente na mesma transação ACID.
- **Sagas Orquestradas:** Operações de pedido distribuído que envolvam múltiplos sistemas (Hub, Bling, SEFAZ, J&T) devem ser governadas por uma máquina de estados orquestrada com compensações reversas automáticas em caso de falha.
- **CQRS em Consultas Analíticas:** Segregação do modelo de escrita relacional (OLTP) dos modelos de leitura desnormalizados usados pelos dashboards 360 e relatórios gerenciais.

### 2. Diretrizes para o Agente DEVOPS & SRE
- **Proteção por Circuit Breaker & Exponential Backoff:** Chamadas a APIs externas devem ser protegidas por disjuntores com cooldown e retries com *Full Jitter* ([[PB-004-resiliencia-circuit-breaker-retry-bulkhead]]).
- **Bulkheads de Recursos:** Isolamento estrito de pools de conexões e workers por integração e por parceiro logístico.
- **Deploys Seguros sem Downtime:** Padrões Blue/Green e Canary com capacidade de rollback em segundos para o Hub de Produção.
- **Governança de Confiabilidade:** Metas de RTO (15 min) e RPO (0 min para fiscal) monitoradas via Four Golden Signals (Latência P95/P99, Tráfego, Erros, Saturação) e métodos USE/RED ([[PB-007-disaster-recovery-spof-avaliacao-rto-rpo]]).

### 3. Diretrizes para o Agente QA
- **Pirâmide de Testes de Carga:** Homologações de novas versões devem obrigatoriamente submeter o sistema aos testes: Smoke -> Average Load -> Stress -> Spike -> Breakpoint Test ([[PB-005-testes-de-carga-stress-breakpoint-qa]]).
- **Validação de Concorrência Concorrente:** Testes de estresse com payloads duplicados simultâneos para comprovar que nenhuma etiqueta duplicada é gerada.
- **Respeito aos Ambientes Sanitizados:** Homologação rigorosamente isolada de qualquer chamada externa a emissores reais ([[RULE-002-homologacao-sem-chamadas-externas]]).

### 4. Diretrizes para o Agente PRODUTO / ARQUITETURA
- **Matriz de Trade-offs CAP/PACELC em Novas Demandas:** Para cada nova feature, definir explicitamente se a prioridade é Consistência Forte (PC/EC) ou Baixa Latência / Alta Disponibilidade (PA/EL).
- **Dimensionamento via Lei de Little ($L = \lambda \times W$):** O dimensionamento de instâncias, workers e filas deve ser calculado matematicamente a partir da taxa projetada de requisições e latência de processamento.
- **Governança de Bounded Contexts (DDD):** Isolamento de regras de negócio de cada holding (Touti, Amavia, Yes!) evitando vazamento de acoplamento conceitual.

## Consequências

### Positivas
- **Eliminação de Riscos Financeiros:** Blindagem contra emissões duplicadas de frete e notas fiscais indevidas.
- **Alinhamento Unificado da Equipe:** A dupla de desenvolvedores Full-Cycle passa a operar com contratos, playbooks e terminologias padronizadas de classe mundial.
- **Prontidão para Escala:** A arquitetura suporta crescimento de 10x no volume de pedidos sem colapso de infraestrutura ou aumento desproporcional de custos.
- **Autonomia dos Agentes do Second Brain:** Cada agente possui critérios de aceite inegociáveis baseados em padrões formais da indústria.

### Negativas / Mitigações
- **Curva de Rigor Técnico:** Implementação de Outbox e Sagas exige disciplina de código.  
  *Mitigação:* Uso dos playbooks prontos (`PB-004`, `PB-005`, `PB-006`, `PB-007`) como receitas pré-fabricadas.
- **Overhead de Testes de Carga:** Execução da pirâmide de testes de performance exige tempo de máquina em homologação.  
  *Mitigação:* Automação dos scripts via K6/Locust integrada ao pipeline de CI/CD.

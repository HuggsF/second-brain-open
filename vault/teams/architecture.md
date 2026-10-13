---
type: team
status: active
date: 2026-10-13
---
# Time: Arquitetura & Tech Lead

## Escopo
Definição de padrões de projeto, arquitetura de sistemas distribuídos de alta escala, governança de dados, elaboração e aprovação de ADRs (Architecture Decision Records) e alinhamento estratégico entre os dois desenvolvedores da equipe técnica.

## Papel no Modelo Full-Cycle
- Como a equipe de tecnologia é composta pelo desenvolvedor e seu superior, o time de Arquitetura funciona como o fórum de **decisão conjunta e governança técnica**.
- Evita decisões impulsivas ou dívida técnica descontrolada, garantindo que qualquer escolha estrutural (ex: migração de API, novo banco de dados, refatoração de filas, protocolo de sincronização) seja devidamente documentada via ADR antes da codificação.
- Serve de ponte para traduzir estratégias de produto da holding em contratos técnicos sustentáveis baseados nos padrões de **System Design**.

## Sistemas sob responsabilidade
- [[system-design-index]] — Hub Mestre de Padrões Arquiteturais e Guias Especializados
- [[modelo-semantico-e-visualizacao-grafo]] — Definição do modelo semântico de dados e grafo do Second Brain
- [[second-brain-graphrag-multiagent]] — Arquitetura de agentes autônomos, recuperação semântica e contratos
- [[sap]] — Definição de contratos de integração e fronteiras com o ERP da holding
- [[salesforce]] — Diretrizes de arquitetura para a migração dos legados SULTS e Holmes para o Salesforce

## Princípios Arquiteturais (Diretrizes de System Design)
1. **Contratos Explícitos:** Comunicação entre sistemas deve ser governada por esquemas versionados (JSON Schema, OpenAPI).
2. **Desacoplamento por Eventos & Outbox:** Sistemas externos (Bling, Salesforce, SAP) não devem bloquear a thread principal dos microsserviços. Disparos de eventos seguem o Padrão Outbox ([[03-sistemas-distribuidos-eventos-concorrencia]]).
3. **Avaliação Formal de Trade-offs (CAP / PACELC):** Toda decisão de persistência deve declarar seu posicionamento na matriz CAP/PACELC ([[02-persistencia-storage-consistencia]]).
4. **Dimensionamento Matemático via Lei de Little:** A capacidade de instâncias e filas é modelada matematicamente ($L = \lambda \times W$) antes de aumentos de infraestrutura ([[05-capacidade-testes-carga-observabilidade]]).
5. **Crescimento Guiado pelo Scale Cube:** Expansão avaliada pelos eixos X (Clonagem Horizontal), Y (Decomposição Funcional de Microsserviços) e Z (Sharding por Tenant/Franquia) ([[04-resiliencia-confiabilidade-alta-escala]]).
6. **Documentação Viva (Second Brain):** Toda decisão arquitetural relevante deve ser registrada no vault como ADR ([[ADR-012-padroes-arquiteturais-system-design-para-agentes-especialistas]]).
7. **Simplicidade Pragmática:** A arquitetura deve ser sustentável pela equipe Full-Cycle de 2 pessoas. Sem complexidade acidental.

## Canais de Comunicação
- **Todos os Times (`adr`):** Emissão de ADRs de referência para guiar os desenvolvimentos.
- **Desenvolvimento (`handoff`):** Especificação de arquitetura de novas funcionalidades, contratos de dados e máquinas de estado de Sagas ([[PB-006-transacoes-distribuidas-saga-outbox]]).
- **Liderança de Negócio (`demand` / `adr`):** Alinhamento de viabilidade técnica, prazos e impactos sistêmicos de novas demandas de produto.

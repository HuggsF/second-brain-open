---
type: architecture
status: intelligence
date: 2026-10-12
---
# Base de Inteligência Técnica: Agente & Time ARQUITETURA / PRODUTO

> **Origem do Conhecimento:** *Descomplicando System Design* — Conteúdo Principal (Days 0, 2, 3, 4, 5, 6, 15, 16, 17, 23).  
> **Objetivo:** Fornecer chunks estruturados de governança, trade-offs, modelagem de dados e capacidade para Arquitetura e Produto.

## 1. Metodologia de System Design & Requisitos (Day 0)

### Ensinamento Central
- **Fase 1: Clarificação de Requisitos:**
  - *Requisitos Funcionais:* O que o sistema faz (ex: gerar etiqueta de frete, sincronizar estoque).
  - *Requisitos Não-Funcionais:* Como o sistema se comporta sob pressão (Throughput: 100 RPS; Latência P95: $< 300\text{ms}$; Disponibilidade: 99.9%; Tolerância a falhas).
- **Fase 2: Estimativa Back-of-the-Envelope (Cálculo Rápido de Ordem de Grandeza):**
  - Sempre calcular: Volume de Leitura vs Escrita (Razão R/W), Largura de Banda de Rede e Volume de Disco em 1 e 5 anos antes de escolher a tecnologia de banco de dados.

---

## 2. Matriz de Trade-offs: Teorema CAP & PACELC (Day 3)

### Ensinamento Central
- Em sistemas distribuídos, **não existe almoço grátis**. Partições de rede acontecem.
- **Classificação Mandatória por Subsistema:**
  1. *Financeiro, Emissão Fiscal e Gestão de Estoque:* **PC/EC** (Prioriza Consistência Forte a todo custo. Se a rede particionar, prefere rejeitar a requisição a emitir nota com dados incorretos).
  2. *Catálogo de Produtos, Busca e Visualizações do Grafo:* **PA/EL** (Prioriza Baixa Latência e Disponibilidade contínua. Aceita que réplicas fiquem desatualizadas por milissegundos).

---

## 3. Seleção de Modelos de Dados & Índices Internos (Day 4)

### Ensinamento Central
- **B-Trees (PostgreSQL, MySQL):** Otimizados para sistemas *Read-Intensive* com transações relacionais rígidas.
- **LSM-Trees (Log-Structured Merge-Trees / RocksDB, Cassandra):** Otimizados para sistemas *Write-Intensive* (ex: ingestão massiva de logs de telemetria, IoT, histórico de rastreios). Escritas são sequenciais e instantâneas em memória.
- **Índices Invertidos (Elasticsearch):** Otimizados para buscas textuais multifacetadas com tolerância a erros tipográficos (*fuzzy search*).

---

## 4. O Modelo do Scale Cube (Day 15)

### Ensinamento Central
A evolução do software corporativo obedece aos 3 eixos ortogonais:
- **Eixo X (Clonagem Horizontal):** Rodar $N$ instâncias da mesma aplicação atrás de um balanceador. Exige que a aplicação seja 100% *Stateless*.
- **Eixo Y (Decomposição Funcional / Bounded Contexts DDD):** Quebrar o monólito em microsserviços autônomos (Hub de Despacho, Faturamento, Catálogo).
- **Eixo Z (Sharding por Dados / Tenant):** Particionar os dados por cliente/região (ex: Touti no cluster 1, Amavia no cluster 2). Garante que problemas em uma holding não afetem as outras.

---

## 5. Capacity Planning Matemático: Lei de Little (Day 23)

### Ensinamento Central
A capacidade de qualquer sistema em regime estável é regida por:
$$L = \lambda \times W$$
- $L$ = Concorrência média necessária no servidor (*In-Flight Requests*).
- $\lambda$ = Taxa de chegada de requisições por segundo (RPS).
- $W$ = Latência média de processamento (em segundos).

*Diretriz Prática:*  
Se a meta de pico é atender $\lambda = 150\text{ RPS}$ e a latência de emissão é $W = 0.4\text{s}$, o pool de workers deve suportar no mínimo:
$$L = 150 \times 0.4 = 60\text{ conexões concorrentes ativas}$$
Adicionar sempre uma margem de segurança (*Headroom*) de 50%, configurando o pool para 90 workers.

---

## 6. Sharding, Particionamento & Replicação (Days 16 e 17)

### Ensinamento Central
- **Consistent Hashing com Virtual Nodes:** Permite adicionar ou remover servidores de banco de dados ou cache sem provocar re-sharding massivo.
- **Evitar Hot Partitions:** Nunca usar timestamps sequenciais como chave de partição; usar hashes compostos (`tenant_id:order_id`).
- **Consenso Distribuído (Raft / Paxos) & Quorum:**
  - Garantia de consistência em escrita:
    $$W + R > N$$
    Garante que toda leitura sempre encontre ao menos um nó que participou da escrita mais recente.

---

## Seção MBA Full Cycle — IA Generativa Aplicada ao Time ARQUITETURA & PRODUTO

> **Origem:** MBA Full Cycle — Engenharia de Software com IA 2026 (Módulos 06, 07, 08, 02)  
> **Data de Adição:** 2026-10-12

---

## 7. Hierarquia de Documentação Técnica & Spec-Driven Development (FC-008, FC-017)

### Ensinamento Central
- **Hierarquia Formal de Especificação:**
  ```
  📋 PRD (Product Requirement Document) — 12 seções estruturadas
  ├── PRD de Alto Nível (visão de produto)
  └── PRD de Feature (requisitos detalhados)
       ↓
  📐 Design & Arquitetura
  ├── HLD (High Level Design Document) — componentes, fluxos globais
  ├── FDD (Feature Design Document) — design técnico específico
  └── Diagramas C4 (Context, Container, Component, Code) via Mermaid
       ↓
  📝 Architecture Decision Records (ADRs / MADR)
       ↓
  📏 Engineering Guidelines (regras globais de código e arquitetura)
  ```
- **Spec-Driven Development (SDD):** A especificação técnica (PRD/FDD) deve existir e ser validada **antes** de qualquer geração de código por IA. A IA atua como compilador da especificação em código e testes.
- *Ação:* Exigir FDD e PRD aprovados antes de iniciar sprints com agentes autônomos.

---

## 8. Tree of Thought (ToT) & Skeleton of Thought (SoT) na Tomada de Decisão (FC-002)

### Ensinamento Central
- **Tree of Thought (ToT):**
  - Técnica para decisões arquiteturais complexas envolvendo trade-offs entre 3 ou mais alternativas (ex: Event Sourcing vs Outbox Pattern vs Change Data Capture).
  - O agente arquiteto explora ramificações paralelas, avalia prós, contras, custos operacionais e consistência antes de selecionar a rota ótima.
- **Skeleton of Thought (SoT):**
  - Geração de documentos longos (PRDs e HLDs) estruturando primeiro o esqueleto e títulos das seções, e em seguida preenchendo as seções de forma paralela ou modular, eliminando truncamentos e perda de contexto.
- *Ação:* Usar SoT na geração automatizada de PRDs e ToT para decisões registradas em novos ADRs.

---

## 9. Diagramação C4 com Mermaid & MADR (FC-009, FC-010)

### Ensinamento Central
- **C4 Model Padronizado em Mermaid:**
  - *Nível 1 (Contexto):* Atores e sistemas externos que interagem com o Second Brain e ecossistema KIOSK.
  - *Nível 2 (Contêineres):* APIs, MCP servers, banco vetorial, bancos relacionais, message broker.
  - *Nível 3 (Componentes):* Controllers, services, domain handlers, parsers de ingestão.
  - *Nível 4 (Código):* Classes e interfaces críticas.
- **MADR (Markdown Architectural Decision Records):**
  - Formato padronizado contendo: Contexto e Problema, Opções Consideradas (com prós e contras ponderados), Decisão Escolhida, Consequências Positivas e Negativas.
- *Ação:* Adotar templates MADR e Mermaid C4 obrigatórios para todos os novos ADRs a partir do ADR-013.

---

## 10. Engineering Guidelines como Base de Alinhamento de Agentes (FC-011)

### Ensinamento Central
- **Engineering Guidelines como Documento Vivo:**
  - Centraliza padrões de design (clean architecture, naming conventions, tratamento de exceções, idempotência, segurança).
  - É injetado diretamente no system prompt ou context window dos agentes desenvolvedores e revisores de código para garantir conformidade automática.
- *Ação:* Criar e manter `vault/architecture/engineering-guidelines.md` como contrato vivo para humanos e agentes.

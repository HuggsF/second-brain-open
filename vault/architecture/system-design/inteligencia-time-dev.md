# 💻 Base de Inteligência Técnica: Agente & Time DEV

> **Origem do Conhecimento:** *Descomplicando System Design* — Conteúdo Principal (Days 4, 6, 9, 11, 12, 13, 18, 19, 20).  
> **Objetivo:** Fornecer chunks estruturados de decisão e padrões arquiteturais para a dupla de engenharia Full-Cycle da KIOSK Brands.  
> **Status:** `#status/intelligence` | **Data:** 2026-10-12

---

## 1. Concorrência Segura & Primitivas de Sincronização (Day 11)

### Ensinamento Central
- **Concorrência vs Paralelismo:** Concorrência é a composição de processos independentes (ótimo para I/O-bound: chamadas aos ERPs Bling, SAP e transportadoras); paralelismo é a execução física simultânea em múltiplos cores (CPU-bound: geração de PDFs de etiquetas, criptografia).
- **Deadlocks (Condições de Coffman):** Só ocorrem quando há exclusão mútua, retenção e espera, não-preempção e espera circular.
  - *Regra de Ouro:* Adquirir locks em **ordem alfabética canônica estrita** em todo o código (ex: sempre lockar `Order` antes de `Inventory`).
- **Race Conditions & Lost Updates:**
  - Em bancos relacionais, nunca fazer `SELECT` seguido de `UPDATE` na aplicação sem travas atômicas.
  - Usar **Optimistic Locking** com coluna `version` (`UPDATE ... WHERE version = expected`) para cenários de baixa contenção, ou **Pessimistic Locking** (`SELECT ... FOR UPDATE`) para alta contenção.
- **Idempotência Universal (Eliminação de DEM-17):**
  - Todo endpoint mutável deve exigir o header `Idempotency-Key: <UUIDv4>`.
  - Inserção atômica com trava de semáforo antes de processar qualquer lógica de negócio.

---

## 2. Comunicação Síncrona vs Assíncrona & Mensageria (Days 12 e 13)

### Ensinamento Central
- **Quando usar Síncrono (REST / gRPC):**
  - Consultas em tempo real imediatas (leitura de saldo de estoque em checkout, autenticação de sessão).
  - Usar **gRPC com Protobuf e HTTP/2** para tráfego interno serviço-a-serviço (multiplexação, binário, contratos tipados).
  - Usar **REST com JSON** para APIs públicas e integração externa com parceiros.
- **Quando usar Assíncrono (Mensageria / Eventos):**
  - Todas as mutações de estado que tocam sistemas externos (Bling, SEFAZ, J&T).
  - Desacoplamento temporal: se o Bling ERP estiver fora do ar, o pedido é aceito, enfileirado e processado assim que o parceiro restabelecer.
- **Topologia de Mensageria (Kafka vs RabbitMQ):**
  - *RabbitMQ:* Roteamento flexível, entrega orientada a filas de tarefas com ACKs individuais.
  - *Kafka / Streaming:* Log imutável particionado em disco com retenção durável e múltiplos consumidores autônomos por offset.
  - *Log Compaction:* Manter apenas a última mutação de cada chave (`order_id`), permitindo reconstruir o estado atual instantaneamente.
- **Garantias de Entrega:**
  - O mundo distribuído opera em *At-Least-Once*. Mensagens duplicadas **vão acontecer**. Logo, o consumidor DEVE ser 100% idempotente.

---

## 3. Padrão Transacional Outbox (Days 13 e 19)

### Ensinamento Central
- **O Anti-Pattern do Dual-Write:** Gravar no banco e publicar no broker de mensagens em blocos separados gera inconsistência silenciosa garantida quando a rede ou o processo cair no meio.
- **Solução Outbox:**
  1. Dentro da mesma transação ACID do PostgreSQL:
     ```sql
     BEGIN;
     INSERT INTO pedidos (id, status, total) VALUES ('PED-99', 'CRIADO', 150.00);
     INSERT INTO outbox_events (aggregate_id, event_type, payload, status)
     VALUES ('PED-99', 'PedidoCriadoEvent', '{"id":"PED-99"}', 'PENDING');
     COMMIT;
     ```
  2. Um worker assíncrono (ou Debezium CDC) lê a tabela `outbox_events`, envia ao broker e marca como `PROCESSED`.
  3. Resultado: Garantia matemática de que nenhum evento é perdido e nenhum evento fantasma é publicado.

---

## 4. Orquestração de Sagas & Transações Distribuídas (Day 19)

### Ensinamento Central
- O protocolo 2PC (Two-Phase Commit) é inviável em microsserviços modernos com APIs de terceiros.
- **A Saga Orquestrada:**
  - Uma máquina de estados central no Hub coordena as chamadas sequenciais.
  - Cada transação local commita seus dados imediatamente.
  - Se a etapa $N$ falhar (ex: Transportadora indisponível após NF emitida), o orquestrador dispara as **Transações Compensatórias** em ordem reversa ($C_{N-1}, \dots, C_1$):
    - Cancela Nota Fiscal na SEFAZ.
    - Estorna reserva de estoque no Bling.
    - Notifica o canal de origem.

---

## 5. CQRS & Event Sourcing (Days 18 e 20)

### Ensinamento Central
- **CQRS (Command Query Responsibility Segregation):**
  - Segregar o modelo de escrita transacional (OLTP altamente normalizado com constraints e travas) do modelo de leitura (read models desnormalizados em Redis, SQLite ou Elasticsearch).
  - Permite que o Dashboard 360 faça consultas instantâneas $O(1)$ sem disputar locks com a fila de emissão de pedidos.
- **Event Sourcing:**
  - O estado da entidade não é uma linha sobrescrita (`status = 'ENTREGUE'`), mas o somatório ordenado de fatos imutáveis (`PedidoCriado`, `PagamentoConfirmado`, `NFEmitida`, `EtiquetaGerada`).
  - Permite auditoria 100% perfeita, reconstrução histórica e replay retroativo em caso de auditoria contábil.

---

## 6. Estratégias de Cache Defensivo (Day 5)

### Ensinamento Central
- **Padrão Cache-Aside com TTL Estrito:**
  - Aplicação busca no Redis. Se miss, busca no banco, grava no cache com TTL e retorna.
- **Mitigação do Cache Stampede (Thundering Herd):**
  - Quando uma chave muito acessada expira sob tráfego massivo, centenas de requisições batem no banco simultaneamente.
  - *Solução:* **Distributed Mutex Lock no Cache Miss** (apenas a primeira thread busca no banco enquanto as outras aguardam 50ms) ou **Early Probabilistic Recomputation (XFetch)**.
- **Cache Penetration:** Usar Bloom Filters ou cachear valores nulos com TTL curto (30s) para evitar sobrecarga com IDs inexistentes.

---

## 7. Backend for Frontends — BFF Pattern (Day 9)

### Ensinamento Central
- **Segregação por Canal:** Web Admin, App de Franqueados e PDV de Loja não compartilham a mesma API central. Cada um possui seu BFF dedicado.
- **API Composition:** O BFF executa chamadas paralelas assíncronas aos microsserviços internos (`Hub + Bling + ERP`), junta os dados e devolve um payload enxuto formatado especificamente para a tela do cliente em uma única viagem de rede (*single RTT*).

---

## 🤖 Seção MBA Full Cycle — IA Generativa Aplicada ao Time DEV

> **Origem:** MBA Full Cycle — Engenharia de Software com IA 2026 (Módulos 06, 08, 03)  
> **Data de Adição:** 2026-10-12

---

## 8. Role Prompting & ReAct para Agentes MCP (FC-001, FC-003)

### Ensinamento Central
- **Role Prompting:** Todo system prompt de agente MCP deve iniciar com persona explícita: papel, domínio de expertise e contexto KIOSK.
- **ReAct Pattern (Reasoning + Acting):** Para agentes que interagem com APIs externas (Bling, SAP), o modelo deve pensar ('Thought'), decidir ação ('Action'), executar com ferramentas ('Observation') e iterar.
- **Prompt Chaining com LangChain:** Conectar prompts sequencialmente onde o output de um é input do próximo. Pipeline: `Análise → Diagnóstico → Recomendação → Ação`.
- *Ação:* Implementar ReAct nos MCP servers que chamam APIs externas para raciocínio antes de cada chamada.

---

## 9. Context Engineering & PRPs (FC-014)

### Ensinamento Central
- **Context Engineering** vai além de Prompt Engineering: construção de **sistemas completos** que fornecem informações e ferramentas corretas no formato ideal para a LLM.
- **PRPs (Product Requirement Prompts):** PRD + inteligência de código curada + agente — o pacote mínimo viável para a IA gerar código pronto para produção na primeira tentativa.
- **Estrutura de um PRP:** Purpose → Principles → Goal → Context (docs, codebase tree, gotchas) → Blueprint → Tasks → Validation Loop → Anti-Patterns.
- **Regra de Ouro:** *"Cada novo chat é como um novo desenvolvedor contratado. Reflita sobre o que ele precisa ter em mãos para entregar a tarefa."*
- *Ação:* Usar PRPs para features complexas que envolvam múltiplos sistemas (Hub + Bling + SAP).

---

## 10. Gestão de Prompts & Testabilidade com IA (FC-005, FC-016)

### Ensinamento Central
- **Prompt Registry:** Arquivo `prompt.yaml` como catálogo centralizado com id, versão (semver), categoria e tags.
- **Testes Automatizados de Prompts:** Validar que novas versões de prompts não degradam métricas (Precision ≥ 0.85, Recall ≥ 0.80).
- **Guardrails Anti-Alucinação:** Fornecer contexto rico (RAG), reduzir temperatura para factuais, usar structured outputs com schema rígido, validar outputs contra schema antes de retornar.
- **Testabilidade:** Todo código gerado por IA deve ser testável. Escrever testes ANTES ou JUNTO com o código.
- *Ação:* Versionar todos os system prompts dos MCP servers. Implementar guardrails de validação de output.

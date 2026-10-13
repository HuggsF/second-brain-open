---
type: architecture
status: reference
date: 2026-10-13
---
# Eixo 6: Cases Reais & Estudos de Caso Práticos

> **Módulos de Origem:** Aulas ao Vivo (Cases 1 a 6) e Day 6 (Case Core Banking com Domain-Driven Design).  
> **Agentes Beneficiados:** `🤖 PRODUTO / ARQUITETURA` e `🤖 DEV`

## 1. Case: Encurtador de Links em Larga Escala (Tipo TinyURL / Bitly)

### Desafio Arquitetural
- 100 milhões de URLs geradas por mês; Razão de Leitura:Escrita de 100:1 (Altamente *Read-Heavy*).
- URLs curtas de no máximo 7 caracteres amigáveis (`[a-zA-Z0-9]`).

### Decisões de Engenharia
1. **Espaço Amostral Base62:**
   - 62 caracteres possíveis ($26 + 26 + 10$).
   - Com 7 caracteres: $62^7 \approx 3.5\text{ trilhões}$ de URLs únicas possíveis (suficiente para décadas).
2. **Geração de Chaves sem Colisão (Key Generation Service - KGS):**
   - Em vez de calcular `hash(url)` e tratar colisões, um serviço background pré-gera sequências aleatórias de 7 caracteres e as salva em uma tabela com status `DISPONIVEL`.
   - Quando uma nova URL chega, pega-se a próxima chave atômica via fila em memória, garantindo complexidade $O(1)$ sem concorrência.
3. **Estratégia de Cache e Armazenamento:**
   - Chave-Valor em memória (Redis) com política de evicção LRU armazenando os 20% das URLs mais acessadas (que atendem 80% do tráfego).
   - Banco persistente orientado a documentos ou chave-valor distribuído (MongoDB / DynamoDB / PostgreSQL particionado).

---

## 2. Case: Busca em Catálogo de Produtos (E-Commerce / Touti Cosmetics)

### Desafio Arquitetural
- Milhares de SKUs com variações (fragrância, volumetria, linha), buscas facetadas, filtros por preço, disponibilidade em estoque e busca textual tolerante a erros de digitação (*fuzzy search*).

### Decisões de Engenharia
1. **Segregação de Leitura e Escrita (CQRS):**
   - Transações de cadastro e estoque ficam no banco relacional ACID (PostgreSQL).
   - Um pipeline assíncrono (CDC via Debezium ou Outbox Worker) alimenta o **Elasticsearch / OpenSearch**.
2. **Índice Invertido e N-Grams:**
   - Analisador fonético e *Edge N-gram* para permitir busca instantânea tipo *autocomplete* conforme o usuário digita no PDV ou e-commerce.
3. **Tratamento de Estoque em Tempo Real:**
   - O Elasticsearch armazena o catálogo estático e atributos semânticos.
   - O saldo de estoque volátil é consultado em cache ultra-rápido (Redis Hashes) no momento de exibir o produto para evitar *overbooking*.

---

## 3. Case: Checkout Distribuído em Saga (O Padrão Central da KIOSK Brands)

### Desafio Arquitetural
- O checkout envolve múltiplos serviços heterogêneos: Sistema de Carrinho, Gateway de Pagamento, Bling ERP (Reserva de Estoque), SEFAZ (Emissão Fiscal) e Transportadora (J&T / Total Express para Etiqueta).
- Se a transportadora falhar após a nota emitida, o sistema não pode deixar a nota ativa nem o estoque preso.

### Solução Arquitetural
- **Orquestrador de Sagas (State Machine do Hub Logístico):**
  - Mantém o estado da transação no banco com uma chave de idempotência (`Idempotency-Key` gerada no início do pedido).
  - Executa as transações locais passo a passo:
    1. Reservar Estoque no ERP.
    2. Autorizar Pagamento.
    3. Emitir NF-e.
    4. Gerar Etiqueta de Frete.
- **Protocolo de Compensação:**
  - Se a etapa 4 falha após 3 tentativas com backoff exponencial:
    - Cancela NF-e na SEFAZ.
    - Estorna cobrança no Gateway.
    - Libera reserva de estoque no ERP.
    - Notifica o cliente com explicação amigável do motivo da falha.

---

## 4. Case: Catálogo de Promoções de Alto Throughput (Flash Sales / Black Friday)

### Desafio Arquitetural
- Milhares de requisições simultâneas por segundo em campanhas promocionais de curta duração.
- Risco extremo de *Cache Stampede* e colapso de banco de dados.

### Decisões de Engenharia
1. **Cache em Borda (Edge Caching / CDN):**
   - Regras de promoção e banners cacheados na Cloudflare/Fastly com TTL de 60 segundos.
   - Headers `stale-while-revalidate` permitindo que o cliente receba o cache antigo instantaneamente enquanto a borda busca a versão fresca em segundo plano.
2. **Mutação com Invalidação Atômica:**
   - Quando o time de produto altera o desconto de uma fragrância no painel, dispara-se um evento que purga seletivamente a chave exata via API da CDN.
3. **Lock Distribuído na Recomputação:**
   - Caso o cache expire em momento de pico, apenas 1 requisição adquire o lock no Redis para consultar o banco de dados; todas as demais recebem a resposta anterior ou esperam 50ms.

---

## 5. Case: Telemetria e Consulta Geoespacial de Frotas / Entregas

### Desafio Arquitetural
- Coleta de coordenadas GPS de centenas de veículos e pedidos em trânsito a cada 5 segundos.
- Consultas analíticas: *"Quais entregas estão em um raio de 5km de determinado franqueado?"*

### Decisões de Engenharia
1. **Armazenamento de Séries Temporais (Time-Series):**
   - Ingestão contínua em formato append-only (TimescaleDB ou ClickHouse).
   - Dados antigos (> 30 dias) sofrem *Downsampling* (agregação de média horária para economizar 90% de espaço em disco).
2. **Indexação Geoespacial com H3 (Hexagonal Hierarchical Spatial Index - Uber):**
   - Em vez de cálculos trigonométricos caros de latitude/longitude em tempo de execução, converte-se a coordenada do entregador em um índice hexagonal H3 inteiro de 64 bits.
   - A busca de vizinhança torna-se uma operação trivial de comparação de inteiros $O(1)$.

---

## 6. Case: Core Banking & Modelagem DDD (Domain-Driven Design)

### Desafio Arquitetural
- Segregação de responsabilidades e fronteiras rígidas em sistemas financeiros onde erros de saldo são intoleráveis.

### Decisões de Engenharia
1. **Bounded Contexts Estritos:**
   - Domínio de Conta Corrente separado do Domínio de Crédito e do Domínio de Auditoria.
   - Comunicação exclusiva via contratos públicos (*Published Language / Anti-Corruption Layer - ACL*).
2. **Entidades Imutáveis com Event Sourcing:**
   - Saldo de conta **nunca é uma coluna editável** (`UPDATE contas SET saldo = saldo + 100`).
   - Saldo é o somatório estrito da sequência imutável de transações de Débito e Crédito:
     $$\text{Saldo} = \sum \text{Créditos} - \sum \text{Débitos}$$
   - Elimina qualquer possibilidade de divergência oculta em auditorias financeiras.

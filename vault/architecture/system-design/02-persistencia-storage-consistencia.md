---
type: architecture
status: reference
date: 2026-10-13
---
# Eixo 2: Persistência, Storage & Consistência

> **Módulos de Origem:** Day 2 (Storage, RAID e I-O), Day 3 (Teorema CAP, ACID e BASE), Day 4 (Databases, Modelos e Indexação), Day 5 (Estratégias de Cache), Day 16 (Sharding e Particionamento), Day 17 (Replicação de Dados).  
> **Agentes Beneficiados:** `🤖 DEV` e `🤖 PRODUTO / ARQUITETURA`

## 1. Storage & I/O em Alto Desempenho

### Métricas Fundamentais
- **IOPS (Input/Output Operations Per Second):** Quantidade de operações de leitura/escrita realizadas por segundo. Crítico para bancos relacionais transacionais (OLTP).
- **Throughput / Bandwidth:** Volume total de dados transferidos (ex: MB/s ou GB/s). Crítico para analytics e pipelines de ingestão de logs/documentos (OLAP).
- **Latency (I/O Wait):** Tempo que uma requisição espera na fila de I/O do kernel antes de ser atendida pelo disco (NVMe SSD: microssegundos; SATA SSD: milissegundos).

### Níveis de RAID
- **RAID 0 (Striping):** Alto throughput, sem redundância (falha de 1 disco perde tudo).
- **RAID 1 (Mirroring):** Duplicação idêntica, alta tolerância a falhas de leitura.
- **RAID 10 (1+0):** O padrão de ouro para bancos de dados de produção (combina velocidade do striping com a segurança do espelhamento).

---

## 2. Teorema CAP & Teorema PACELC

### Teorema CAP (Brewer)
Em presença de uma **Partição de Rede (P)** (inevitável em sistemas distribuídos), o sistema deve escolher entre:
- **Consistência (C):** Toda leitura recebe a escrita mais recente ou gera erro.
- **Disponibilidade (A):** Toda requisição não com falha recebe uma resposta não errônea, mas pode não ser a mais recente.

### Extensão PACELC (Abadi)
Se há **Partição (P)**, escolha entre **Disponibilidade (A)** e **Consistência (C)**;  
**Else (E)** (operação normal sem partição), escolha entre **Latência (L)** e **Consistência (C)**.

```
                  ┌── (P)artição ──> Escolha entre [A]vailability ou [C]onsistency
Sistema Distribuído ──┤
                  └── (E)lse ──────> Escolha entre [L]atency ou [C]onsistency
```

### Decisão para KIOSK Brands:
- **Financeiro / Emissão Fiscal (NF-e, Etiquetas, Contabilidade):** **PC/EC** (Prioriza Consistência Absoluta, mesmo com maior latência).
- **Catálogo de Produtos, Busca e Visualizações do Second Brain:** **PA/EL** (Prioriza Baixa Latência e Disponibilidade com Consistência Eventual).

---

## 3. ACID vs BASE

| Modelo | Princípios | Características | Aplicação no Ecossistema |
| :--- | :--- | :--- | :--- |
| **ACID** | Atomicity, Consistency, Isolation, Durability | Transações rígidas, locks pessimistas/MVCC, escrita segura em disco (WAL/fsync). | PostgreSQL / MySQL do Hub para geração de ordens e deduplicação de pedidos. |
| **BASE** | Basically Available, Soft-state, Eventual consistency | Alta disponibilidade, nós assíncronos, resolução de conflitos por timestamp ou CRDTs. | Grafo Semântico do Second Brain, cache de visualizações 360, logs de telemetria. |

---

## 4. Modelos de Armazenamento e Indexação Interna

### B-Trees vs LSM-Trees (Log-Structured Merge-Trees)
- **B-Trees / B+ Trees (PostgreSQL, MySQL, Oracle):**
  - Otimizados para **Read-Intensive**.
  - Leituras em complexidade $O(\log N)$ com poucas páginas de disco acessadas.
  - Escritas exigem modificação aleatória (*random I/O*) em páginas de dados, dependendo de cache de escrita e WAL.
- **LSM-Trees (RocksDB, Cassandra, ScyllaDB, LevelDB):**
  - Otimizados para **Write-Intensive**.
  - Escritas são sequenciais em memória (*MemTable*) e adicionadas em disco como logs imutáveis (*SSTables*).
  - Um processo contínuo de compactação em background (*Compaction*) unifica os arquivos.
  - Leituras exigem busca em múltiplos níveis (mitigado por *Bloom Filters*).

### Índices Invertidos (Elasticsearch / OpenSearch):
- Mapeia cada termo/palavra para a lista de IDs de documentos onde ela ocorre.
- Essencial para busca textual em catálogos, pedidos históricos e base de conhecimento do Second Brain.

---

## 5. Estratégias de Cache & Mitigação de Falhas

### Padrões de Acesso ao Cache
1. **Cache-Aside (Lazy Loading):**
   - Aplicação consulta o cache. Se *Hit*, retorna. Se *Miss*, busca no banco, popula o cache com TTL e retorna.
   - Padrão recomendado para as consultas do Hub e tabelas de franqueados.
2. **Write-Through:**
   - A aplicação escreve no cache e o cache escreve de forma síncrona no banco de dados.
3. **Write-Behind (Write-Back):**
   - A aplicação escreve apenas no cache. Um worker assíncrono drena os dados para o banco. Altíssimo throughput de escrita, risco de perda em crash de memória.

### Políticas de Evicção:
- **LRU (Least Recently Used):** Descarta o item menos acessado recentemente.
- **LFU (Least Frequently Used):** Descarta o item com menor frequência histórica.

### Riscos e Mitigações Críticas:
- **Cache Stampede / Thundering Herd:** Múltiplas requisições simultâneas sofrem *cache miss* no exato instante em que uma chave pesada expira, sobrecarregando o banco de dados.
  - *Mitigação:* **Mutex Lock no Cache Miss** (apenas 1 thread busca no banco enquanto as outras aguardam) ou **Probabilistic Early Recomputation (XFetch)**.
- **Cache Penetration:** Buscas por IDs inexistentes que sempre batem no banco de dados.
  - *Mitigação:* Armazenar chave nula no cache com TTL curto (ex: 30s) ou usar **Bloom Filter**.

---

## 6. Sharding, Particionamento & Replicação

### Topologias de Sharding
- **Range-Based Sharding:** Particionamento por faixas (ex: Pedidos 1 a 1.000.000 no Shard A). Risco de *Hot Spot* se os IDs forem sequenciais.
- **Hash-Based Sharding:** Partição = $\text{hash}(key) \pmod N$. Distribui uniformemente, mas dificulta rebalanceamento ao adicionar nós.
- **Consistent Hashing (com Virtual Nodes):** Permite adicionar ou remover servidores sem mover mais do que $K/N$ chaves, garantindo redistribuição suave.

### Modelos de Replicação:
- **Primary-Replica (Leader-Follower):**
  - Escritas apenas no nó Primário. Réplicas atendem consultas de leitura.
  - *Atenção à replicação assíncrona:* Uma leitura feita imediatamente após a escrita na réplica pode ler dado desatualizado (*Replication Lag*). Exige regra de **Read-Your-Own-Writes** (ler do primário após escrita recente do usuário).
- **Quorum e Consenso Distribuído (Raft / Paxos):**
  - Garantia de que uma transação só é commitada após confirmação da maioria:  
    $$W + R > N$$  
    Onde $W$ = nós de escrita, $R$ = nós de leitura, $N$ = total de réplicas.

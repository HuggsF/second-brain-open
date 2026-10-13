---
type: architecture
status: intelligence
date: 2026-10-12
---
# Base de Inteligência Técnica: Agente & Time DEVOPS / SRE

> **Origem do Conhecimento:** *Descomplicando System Design* — Conteúdo Principal (Days 1, 7, 8, 10, 21, 22, 25, 26, 27, 28).  
> **Objetivo:** Fornecer chunks estruturados de infraestrutura, resiliência, observabilidade e confiabilidade contínua.

## 1. Roteamento de Borda, Load Balancers & Gateways (Days 1, 7, 8)

### Ensinamento Central
- **Layer 4 vs Layer 7:**
  - *L4 (TCP):* Terminação rápida sem descriptografia ou leitura de payload. Ideal para altíssimo throughput com latência mínima.
  - *L7 (HTTP/2, HTTP/3):* Roteamento baseado em headers, host e paths. Terminação TLS e compressão concentradas na borda.
- **Algoritmos de Balanceamento (Envoy):**
  - Para chamadas com tempos de execução heterogêneos (como emissão de notas e etiquetas, que variam de 100ms a 4s), usar **Least Connections / Least Requests** em vez de Round Robin simples.
  - Usar **Maglev / Ring Hash** quando for benéfico enviar o mesmo `tenant_id` para a mesma réplica para maximizar o cache local.
- **Outlier Detection (Ejeção Automática de Réplicas Doentes):**
  - O Envoy monitora passivamente respostas 5xx. Se uma réplica falhar 3 vezes consecutivas em 5 segundos, ela é ejetada automaticamente do pool por 30 segundos.
- **API Gateways & Rate Limiting (Kong):**
  - *Token Bucket:* Permite rajadas pontuais controladas (*bursts*), reabastecendo em taxa fixa.
  - *Leaky Bucket:* Garante uma vazão perfeitamente linear para proteger parceiros externos como o Bling v3.

---

## 2. Service Mesh & Inovações com eBPF (Day 10)

### Ensinamento Central
- **O Fim do Overhead de Sidecars Tradicionais:**
  - Injetar um proxy Envoy ao lado de cada container consome muita CPU e memória em clusters enxutos.
- **A Abordagem Moderna com eBPF (Cilium / Ambient Mesh):**
  - A interceptação e segurança (mTLS, L7 tracing, métricas de rede) ocorrem diretamente dentro do kernel Linux via programas eBPF seguros.
  - Reduz latência de rede em até 40% e elimina a necessidade de gerenciar sidecars manuais.

---

## 3. Resiliência: Circuit Breaker & Retries Desincronizados (Day 21)

### Ensinamento Central
- **Circuit Breaker (Disjuntor de Falhas):**
  - *Closed:* Operação normal.
  - *Open:* Se a taxa de erro atingir $\ge 50\%$ em 20s, o disjuntor abre. As chamadas falham **imediatamente no cliente** (*Fast Fail*) sem fazer requisições de rede inúteis.
  - *Half-Open:* Após 30s de cooldown, 3 requisições de teste passam. Sucesso fecha o circuito; erro reabre por 60s.
- **Full Jitter no Exponential Backoff:**
  - Retentar na mesma janela agrava o colapso (*Thundering Herd*).
  - Fórmula obrigatória: $\text{Delay} = \text{random}(0, \min(M, B \times 2^{\text{tentativa}}))$.

---

## 4. Bulkhead Pattern & Cell-Based Architecture (Days 25 e 26)

### Ensinamento Central
- **Bulkheads (Isolamento de Compartimentos):**
  - Conexões de banco e pools de threads para o Hub Logístico de emissão rápida NUNCA compartilham recursos com rotinas pesadas de conciliação ou relatórios analíticos.
  - Falha na integração da J&T não consome as conexões reservadas para os Correios ou Total Express.
- **Arquitetura Celular (Cell-Based):**
  - Em vez de um cluster gigante único, divide-se a aplicação em células autônomas idênticas.
  - *Shuffle Sharding:* Clientes são mapeados para subconjuntos de células sobrepostos (ex: Franqueado A nas Células 1 e 2; Franqueado B nas Células 2 e 3). A probabilidade de dois franqueados colidirem na mesma célula em caso de desastre cai para quase zero.

---

## 5. Deploys Seguros sem Downtime (Day 22)

### Ensinamento Central
- **Blue/Green Deployments:**
  - Dois ambientes idênticos mantidos. O roteador inverte o tráfego de 100% Azul para 100% Verde em milissegundos. Rollback instantâneo via chaveamento de tráfego.
- **Canary Releases:**
  - Encaminha 5% do tráfego real para a nova versão. Se os Four Golden Signals estiverem estáveis por 15 minutos, amplia-se para 25%, 50% e 100%.
- **Feature Flags:**
  - Código novo entra desligado por padrão no deploy. Ativação controlada via regra de negócio sem necessidade de nova compilação ou pipeline.

---

## 6. Auditoria de SPOFs & Disaster Recovery (Day 27)

### Ensinamento Central
- **Métricas Mandatórias de Continuidade:**
  - **RTO (Recovery Time Objective):** Tempo máximo suportável de parada. Meta KIOSK: $\le 15\text{ minutos}$.
  - **RPO (Recovery Point Objective):** Quantidade máxima tolerável de dados perdidos. Meta KIOSK: $0\text{ minutos}$ (Zero Data Loss para emissões fiscais e financeiro).
- **Estratégia de Failover:**
  - Réplica do banco em outra zona com failover automatizado via patroni/consul.
  - DNS corporativo configurado com TTL de 300 segundos para chaveamento rápido em contingência.

---

## 7. Observabilidade: Golden Signals, USE & RED (Day 28)

### Ensinamento Central
- **Four Golden Signals (Google SRE):**
  1. *Latência:* Medida estritamente em **P95 e P99** (separando sucessos de falhas rápidas).
  2. *Tráfego:* Requisições por segundo (RPS) e conexões simultâneas ativas.
  3. *Erros:* Taxa de erros HTTP 5xx e exceptions não tratadas.
  4. *Saturação:* Porcentagem de uso do recurso mais restritivo (CPU, memória, conexões de banco de dados).
- **Diagnóstico USE (Recursos de Hardware/Banco):**
  - **U**tilization (tempo ocupado), **S**aturation (fila de espera), **E**rrors (erros físicos/TCP).
- **Diagnóstico RED (Serviços e APIs):**
  - **R**ate (RPS), **E**rrors (erros/seg), **D**uration (distribuição de latência).

---

## Seção MBA Full Cycle — IA Generativa Aplicada ao Time DEVOPS

> **Origem:** MBA Full Cycle — Engenharia de Software com IA 2026 (Módulos 02-05, 03-02, 06)  
> **Data de Adição:** 2026-10-12

---

## 8. Docker Compose for AI Agents (FC-015)

### Ensinamento Central
- **Docker Compose for Agents** simplifica ambientes de desenvolvimento com IA containerizando todos os serviços: bancos (PostgreSQL, Redis), brokers (RabbitMQ), servidores MCP e agentes de IA.
- **Benefícios:** Ambiente 100% reproduzível, isolamento de dependências, onboarding em um comando (`docker compose up`).
- **Padrão KIOSK:** O `docker-compose.yml` do Second Brain deve incluir todos os MCP servers, banco vetorial, serviços de observabilidade e ferramentas de avaliação.
- *Ação:* Atualizar `docker-compose.yml` para incluir todos os serviços do ecossistema Second Brain em um único compose.

---

## 9. SLI/SLO/SLA e Error Budget Formalizados (FC-019)

### Ensinamento Central
- **SLI (Service Level Indicator):** Métrica observável (ex: latência P95 das APIs MCP).
- **SLO (Service Level Objective):** Meta interna (ex: P95 < 250ms, 99.5% uptime para MCP servers).
- **SLA (Service Level Agreement):** Compromisso contratual com stakeholders internos (ex: 99.0% uptime).
- **Error Budget = 100% - SLO:** Se o error budget é consumido (ex: > 0.5% downtime/mês), **freeze de deploys** até recuperação.
- **Pipeline de Error Budget:** Automatizar verificação de SLOs no CI/CD; deploy vetado se taxa de erro > 0.1% em homologação.
- *Ação:* Definir SLOs formais para cada MCP server do Second Brain. Implementar verificação de error budget no pipeline.

---

## 10. Engineering Guidelines para Infraestrutura (FC-011)

### Ensinamento Central
- **Guidelines como documentos vivos** são consumidos tanto por humanos quanto por agentes de IA como contexto para gerar configurações e scripts consistentes.
- **Seções obrigatórias para DEVOPS:**
  1. Stack de infra (Docker, K8s, Terraform/Pulumi)
  2. Padrões de containerização (Dockerfile, multi-stage build)
  3. Pipeline CI/CD (stages, gates, rollback)
  4. Observabilidade (logs estruturados, Prometheus, OpenTelemetry)
  5. Security (TLS, secrets management, RBAC)
  6. Disaster Recovery (RTO, RPO, backups)
- *Ação:* Criar `vault/architecture/engineering-guidelines-devops.md` consumível pelo Agente DEVOPS.

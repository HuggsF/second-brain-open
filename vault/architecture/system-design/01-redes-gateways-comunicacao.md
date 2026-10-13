---
type: architecture
status: reference
date: 2026-10-13
---
# Eixo 1: Redes, Gateways & Comunicação

> **Módulos de Origem:** Day 1 (Protocolos de Rede), Day 7 (Load Balancers e Proxies Reversos), Day 8 (API Gateways), Day 09 (Backend for Frontends - BFFs), Day 10 (Service Mesh Pattern), Day 12 (Comunicação Síncrona).  
> **Agentes Beneficiados:** `🤖 DEV` e `🤖 DEVOPS`

## 1. Fundamentos de Rede & Camadas OSI em Larga Escala

### Modelo Conceitual e Decisões Técnicas
- **Layer 4 (Transporte - TCP/UDP):** Decisão de roteamento baseada apenas em IP e Porta. Usado em Load Balancers de altíssimo throughput (ex: HAProxy em modo TCP, AWS NLB). Vantagem: Menor latência, menor overhead de CPU. Desvantagem: Não lê headers, cookies ou paths da URL.
- **Layer 7 (Aplicação - HTTP/1.1, HTTP/2, HTTP/3):** Decisão de roteamento baseada em payload, path, headers e host (ex: Nginx, Envoy, Kong).
  - *HTTP/1.1:* Conexões persistentes via `Keep-Alive`, porém sofre de *Head-of-Line Blocking* no nível da conexão HTTP.
  - *HTTP/2:* Multiplexação de streams sobre uma única conexão TCP, compressão de headers HPACK, binário. Resolve o bloqueio de aplicação, mas ainda compartilha o bloqueio de pacotes TCP subjacente.
  - *HTTP/3 (QUIC / UDP):* Elimina o *Head-of-Line Blocking* no nível de transporte. Conexões sobrevivem à troca de rede (migração de IP móvel).

### Diretriz para KIOSK Brands:
- **Tráfego Externo (Lojas/Franqueados/Mobile):** Terminação TLS em L7 com HTTP/2 habilitado no Gateway/Proxy Reverso.
- **Tráfego Interno (Serviço-a-Serviço):** gRPC com HTTP/2 e Protobuf para chamadas de alta performance com contratos estritos, ou REST JSON com `Keep-Alive` agressivo para integrações legadas.

---

## 2. Load Balancers & Proxies Reversos (Envoy & Nginx)

### Algoritmos de Balanceamento
1. **Round Robin:** Distribuição sequencial. Ideal quando todas as requisições têm custos idênticos e os nós possuem capacidades iguais.
2. **Least Connections / Least Requests:** Encaminha para o servidor com menor número de conexões ativas. Fundamental para o Hub Logístico, onde o processamento de emissão de NF e etiqueta varia de 150ms a 3.000ms.
3. **Consistent Hashing (Maglev / Ring Hash):** Garante que requisições com a mesma chave (ex: `tenant_id` ou `order_id`) atinjam o mesmo nó. Permite caching local em memória eficiente sem espalhar cache miss por todo o cluster.

### Healthchecks:
- **Active Healthcheck:** O proxy faz ping periódico (`/healthz`).
- **Passive Healthcheck (Outlier Detection):** Se uma instância responder com 5xx consecutivas (ex: 3 erros em 5s), o Envoy ejeta a instância do pool por 30s automaticamente.

---

## 3. API Gateways & Controles de Fluxo (Kong)

### Responsabilidades do Gateway
1. **Autenticação & Autorização Centralizada:** Validação de JWT, OAuth2 e API Keys antes de permitir o acesso à rede interna.
2. **Roteamento Dinâmico:** Desacoplamento entre URLs públicas e nomes de serviços no Docker/Kubernetes.
3. **Rate Limiting & Throttling:**
   - *Token Bucket:* Permite pequenos surtos (*bursts*) de tráfego até o limite de tokens acumulados, reabastecendo em taxa constante.
   - *Leaky Bucket:* Força uma vazão de saída rigorosamente constante, descartando o excesso quando o buffer enche.
   - *Aplicação na KIOSK:* Proteção das integrações com o Bling ERP v3 (limite de requisições por segundo por token) via Token Bucket com fila interna de espera.

---

## 4. Backend for Frontends (BFF Pattern)

### Princípios Arquiteturais
- **Segregação por Canal:** Em vez de uma API única monolítica servir Mobile, Web Dashboard e PDV, cada canal possui seu próprio BFF adaptado.
- **API Composition:** O BFF faz chamadas paralelas aos microsserviços internos (ex: `Hub + Bling + Touti`), sintetiza um payload limpo e retorna ao cliente em uma única viagem de rede (*single round-trip*).
- **Contenção de Blast Radius:** Se a interface do PDV precisar de uma transformação pesada, a falha afeta apenas o BFF do PDV, mantendo as operações web intactas.

---

## 5. Service Mesh (Envoy, Istio & Inovações com eBPF)

### Arquitetura Control Plane vs Data Plane
- **Data Plane (Sidecars ou Proxyless):** Intercepta todo o tráfego de entrada e saída (Inbound/Outbound) aplicando mTLS, métricas Prometheus e retries automáticos.
- **Control Plane (Istio / Cilium):** Distribui políticas de segurança, certificados e regras de roteamento.
- **Evolução Moderna com eBPF (Cilium / Ambient Mesh / ZTunnel):**
  - Elimina o overhead de ter um proxy sidecar por container.
  - Interceptação de pacotes direto no nível do kernel Linux via eBPF, reduzindo consumo de memória e latência em até 40%.

---

## 6. Comunicação Síncrona: REST vs gRPC vs Webhooks vs WebSockets

| Protocolo | Mecanismo | Formato | Caso de Uso Recomendado |
| :--- | :--- | :--- | :--- |
| **REST (HTTP/1.1 / JSON)** | Request-Response síncrono | Texto (JSON) | APIs públicas para terceiros, endpoints administrativos do Hub. |
| **gRPC (HTTP/2 / Protobuf)** | RPC binário multiplexado | Binário (Protobuf) | Comunicação interna entre agentes do Second Brain e microsserviços críticos. |
| **Webhooks** | Event-driven HTTP POST invertido | JSON | Notificações de mudança de status (ex: Yampi para Hub, J&T para Hub). Exige retries com backoff. |
| **WebSockets** | Conexão full-duplex bidirecional | Texto/Binário | Feed em tempo real do Dashboard Operacional e alertas de divergência de estoque/etiquetas. |

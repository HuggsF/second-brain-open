# 🛡️ Eixo 4: Resiliência, Confiabilidade & Alta Escala

> **Módulos de Origem:** Day 15 (Scale Cube), Day 21 (Patterns de Resiliência), Day 22 (Modelos de Deployment), Day 25 (Bulkhead Pattern), Day 26 (Cell-Based Pattern), Day 27 (Single Point of Failure e Disaster Recovery).  
> **Status:** `#status/reference` | **Agentes Beneficiados:** `🤖 DEVOPS` e `🤖 PRODUTO / ARQUITETURA`

---

## 1. O Modelo do Scale Cube (Abbott & Fisher)

O cubo de escalabilidade divide a arquitetura em três eixos ortogonais de crescimento:

```
                  Eixo Y: Decomposição por Serviço / Função
                            ▲
                            │   ┌─────────────┐
                            │  /             /│
                            │ ┌─────────────┐ │
                            │ │             │ │
                            │ │             │ ┼────► Eixo X: Clonagem Horizontal
                            │ └─────────────┘ │      (Stateless Replicas)
                            │/             /
                            └─────────────► Eixo Z: Particionamento / Sharding
                                                    (Por Tenant / Cliente / Região)
```

1. **Eixo X (Clonagem Horizontal):** Executar múltiplas cópias do mesmo serviço atrás de um balanceador de carga. Fácil implementação, exige que o serviço seja rigorosamente *Stateless* (sem sessão em memória).
2. **Eixo Y (Decomposição Funcional / Microsserviços):** Quebra do monólito em domínios delimitados (ex: Separar o serviço de Catálogo, o Hub de Emissão de Etiquetas e o Módulo de Faturamento). Permite equipes independentes e escalabilidade direcionada.
3. **Eixo Z (Particionamento por Dados / Sharding de Tenants):** Cada instância atende um subconjunto específico de dados (ex: Franqueados Região Sul no Cluster A, Franqueados Região Sudeste no Cluster B). Reduz a sobrecarga de banco de dados e isola completamente falhas de clientes gigantes.

---

## 2. Padrões Fundamentais de Resiliência

### 1. Circuit Breaker (Disjuntor)
Previne que falhas repetidas em um serviço externo (ex: Bling ERP instável) drenem as threads e recursos do Hub.
- **Closed (Fechado):** Operação normal. Todas as requisições passam.
- **Open (Aberto):** Se a taxa de erro ultrapassar o limiar (ex: 50% de erros em 10s), o disjuntor abre. Todas as chamadas subsequentes falham **imediatamente** sem fazer requisição de rede, acionando o *Fallback*.
- **Half-Open (Semi-Aberto):** Após um tempo de cooldown (ex: 30s), permite que uma fração mínima de tráfego de teste passe. Se tiver sucesso, volta para Closed; se falhar, reabre por mais tempo.

### 2. Retry com Exponential Backoff e Full Jitter
Tentar novamente sem delay só agrava o colapso do serviço de destino (*Thundering Herd*).
$$\text{Delay} = \text{random}(0, \min(M, B \times 2^{\text{tentativa}}))$$
- **Backoff Exponencial:** Aumenta o tempo de espera a cada falha (100ms, 200ms, 400ms, 800ms...).
- **Full Jitter:** Introduz aleatoriedade no delay para desincronizar os retries de centenas de clientes simultâneos.

### 3. Bulkhead Pattern (Isolamento de Compartimentos)
Inspirado nas anteparas dos navios que impedem que o alagamento de um compartimento afunde o navio inteiro.
- **Bulkhead de Threads/Processos:** Pools de conexões e workers separados. Se a integração da J&T travar por lentidão, ela esgota apenas o seu próprio pool (ex: 5 conexões), deixando 20 conexões livres para a emissão da Total Express e Correios.
- **Bulkhead de Infraestrutura:** Clusters ou nós separados por criticidade (Tráfego de Emissão Fiscal separado de Tráfego de Relatórios).

---

## 3. Cell-Based Architecture Pattern

Em altíssima escala, arquiteturas centralizadas atingem limites de contenção (*Blast Radius* inaceitável: se o banco principal cai, 100% da empresa pára).

### Princípios da Arquitetura Celular
1. O ecossistema é particionado em **Células Autônomas e Idênticas** (cada célula possui suas APIs, workers e banco de dados).
2. Uma camada de roteamento na borda (*Cell Router*) direciona o tráfego baseado na chave do cliente (`tenant_id`).
3. Uma célula nunca se comunica com outra célula diretamente.
4. **Shuffle Sharding:** Técnica avançada onde clientes são alocados em subconjuntos sobrepostos de células (ex: Cliente 1 nas células A+B; Cliente 2 em B+C). Reduz a chance de dois clientes colidirem em falha para quase zero.

---

## 4. Estratégias Modernas de Deployment (Zero Downtime)

| Estratégia | Como Funciona | Riscos / Overhead | Casos de Uso na KIOSK |
| :--- | :--- | :--- | :--- |
| **Rolling Update** | Instâncias da versão nova substituem as antigas gradualmente (1 a 1). | Requer que a versão nova e antiga coexistam e suportem o mesmo esquema de banco. | Atualizações rotineiras do Hub em ambiente de Homologação. |
| **Blue/Green** | Mantém dois ambientes idênticos completos (Azul = ativo; Verde = novo). O roteador inverte o tráfego instantaneamente. | Custo duplicado de infraestrutura durante a janela de transição. Rollback instantâneo. | Deploys de grande porte em Produção (alterações de infraestrutura do Hub). |
| **Canary Release** | Roteia uma pequena porcentagem do tráfego real (ex: 5%) para a nova versão. Se métricas de erro estiverem estáveis, expande para 100%. | Exige telemetria precisa e observabilidade em tempo real dos Golden Signals. | Liberação de novas integrações de transportadoras e novos webhooks. |
| **Feature Flags** | O código novo vai para produção desligado por padrão, ativado dinamicamente por regra de negócio sem novo deploy. | Requer limpeza contínua de código para evitar flags obsoletas. | Liberação de novos recursos por franqueado ou piloto controlado. |

---

## 5. Single Point of Failure (SPOF) & Disaster Recovery (DR)

### Identificação de SPOFs
Um SPOF é qualquer componente físico ou lógico cuja falha interrompe a operação de todo o sistema.
- *Exemplos comuns:* Banco de dados primário sem réplica automática com auto-failover, token único de API compartilhado sem rotação, balanceador de carga em instância única, DNS com TTL de 24 horas.

### Métricas de Confiabilidade e Recuperação
- **MTTD (Mean Time to Detect):** Tempo médio decorrido entre a ocorrência de um incidente e sua detecção pelos alarmes.
- **MTTR (Mean Time to Repair/Recover):** Tempo médio necessário para restabelecer a operação normal do serviço.
- **MTBF (Mean Time Between Failures):** Tempo médio entre falhas operacionais.
- **RTO (Recovery Time Objective):** Tempo máximo tolerável de parada de negócio admitido pela holding (ex: RTO do Hub = 15 minutos).
- **RPO (Recovery Point Objective):** Volume máximo de dados perdidos tolerável, medido em tempo (ex: RPO do Hub = 0 minutos para emissão fiscal, tolerância a perda zero).

### Estratégias de Recuperação de Desastre
1. **Backup & Restore:** Custo mínimo, RTO/RPO longo (horas).
2. **Pilot Light:** Serviços mínimos (banco replicando continuamente), servidores de aplicação sobem em caso de desastre.
3. **Warm Standby:** Cópia em escala reduzida rodando continuamente em outra zona/região.
4. **Multi-Region Active-Active:** Tráfego dividido ativamente entre duas regiões geográficas distintas. Custo elevado, RTO/RPO próximo de zero.

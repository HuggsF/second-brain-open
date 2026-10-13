---
type: architecture
status: intelligence
date: 2026-10-12
---
# Base de Inteligência Técnica: Agente & Time QA

> **Origem do Conhecimento:** *Descomplicando System Design* — Conteúdo Principal (Days 11, 14, 21, 24, 28).  
> **Objetivo:** Fornecer chunks estruturados de testes de carga, concorrência, confiabilidade e auditoria para o time de QA.

## 1. Pirâmide de Testes de Carga & Estresse (Day 24)

### Ensinamento Central
O time de QA executa a suíte de performance em etapas sequenciais com objetivos estritos:

```
Estágio 1: Smoke Test (1 a 5 VUs · 2 min) ──────► Sanidade de contratos funcionais
                 │
Estágio 2: Average Load Test (50 RPS · 10 min) ─► P95 < 250ms sob carga diária normal
                 │
Estágio 3: Stress Test (150 RPS · 10 min) ─────► Carga 2x-3x superior ao pico de vendas
                 │
Estágio 4: Spike Test (0 a 300 RPS em 10s) ────► Validar Rate Limiter e contenção 429
                 │
Estágio 5: Breakpoint Test (Ramping contínuo) ──► Determinar ponto de saturação física
                 │
Estágio 6: Soak / Endurance Test (6h-24h) ─────► Caçar vazamentos de memória e conexões
```

### Regras de Ouro para QA:
1. **Ambiente Sanitizado:** Testes de carga NUNCA disparam chamadas a webservices externos reais de produção (SEFAZ, J&T real, Bling real) — usar sempre mock servers com latência artificial configurável ([[RULE-002-homologacao-sem-chamadas-externas]]).
2. **Avaliação por Percentis:** Médias aritméticas mentem em sistemas distribuídos. O critério de aprovação deve ser sempre baseado em **P95 e P99**.
3. **Métricas de Aceite:**
   - Erros funcionais: $0\%$.
   - Latência P95 em Average Load: $< 300\text{ms}$.
   - Latência P99 em Stress: $< 800\text{ms}$.

---

## 2. Testes de Concorrência Massiva & Idempotência (Day 11)

### Ensinamento Central
- O principal risco financeiro em logística de e-commerce é a emissão duplicada de etiquetas e notas fiscais por duplo clique do operador ou webhooks repetidos (caso real DEM-17).
- **Protocolo de Teste de Concorrência:**
  1. Enviar 50 requisições HTTP paralelas em menos de 10ms com o **mesmo payload e a mesma `Idempotency-Key`**.
  2. **Critério de Sucesso Estrito:**
     - Exatamente 1 requisição retorna `HTTP 200/201 OK` com a etiqueta gerada.
     - As outras 49 requisições devem retornar `HTTP 409 Conflict` (ou retornar a mesma etiqueta já cacheada se a execução já tiver terminado).
     - **Zero duplicidade no banco de dados.**

---

## 3. Injeção de Falhas & Validação de Circuit Breakers (Day 21)

### Ensinamento Central
- Sistemas distribuídos não falham apenas caindo; eles falham ficando lentos (*Grey Failures*).
- **Cenários Obrigatórios de Teste de Resiliência:**
  1. *Latência Alta Simulada:* Configurar o mock da transportadora para responder em 5.000ms.
     - *Esperado:* O timeout do Hub (3.000ms) cancela a requisição, o Circuit Breaker abre após 10 falhas e as chamadas subsequentes falham em $< 5\text{ms}$ (*Fast Fail*).
  2. *Retorno Contínuo de 500:*
     - *Esperado:* O sistema enfileira o pedido em Dead Letter Queue (DLQ) para retry posterior com backoff, sem travar o worker principal.

---

## 4. Validação de Service Levels: SLI, SLO & Error Budget (Day 28)

### Ensinamento Central
- O time de QA atua como guardião do **SLO (Service Level Objective)**:
  - Meta de Disponibilidade Interna: $99.5\%$ de sucesso mensal.
  - Meta Contratual (SLA): $99.0\%$.
- **Error Budget (Orçamento de Erro):**
  - Se os testes em homologação mostrarem regressão de latência ou taxa de erro $> 0.1\%$, o deploy é vetado automaticamente pelo pipeline.

---

## Seção MBA Full Cycle — IA Generativa Aplicada ao Time QA

> **Origem:** MBA Full Cycle — Engenharia de Software com IA 2026 (Módulos 06-08, 06-09)  
> **Data de Adição:** 2026-10-12

---

## 5. Pipeline de Prompt Evaluation (FC-007)

### Ensinamento Central
O MBA Full Cycle ensina um pipeline completo de avaliação de prompts com métricas quantitativas:

**Etapas do Pipeline:**
1. **Criar Golden Dataset:** Pares de `input` → `expected_output` curados manualmente
2. **Executar prompt** em todas as entradas do dataset
3. **Aplicar evaluators:**
   - *Binários:* Correto ou Incorreto
   - *Score com Range:* 1-5 ou 1-10
   - *Pairwise:* Comparação entre 2 versões de prompt
   - *LLM-as-Judge:* Um LLM avalia o output de outro
4. **Calcular métricas:**
   - Precision ≥ 0.85 (relevância do retornado)
   - Recall ≥ 0.80 (completude do esperado)
   - F1 ≥ 0.82 (harmônica P×R)
   - Embedding Distance (similaridade semântica)
5. **Comparar com baseline** — se melhor, merge; se pior, iterar

### Regra de Ouro para QA:
- **Todo prompt dos agentes MCP deve ter golden dataset associado**
- **Novas versões de prompt só podem ser deployadas se métricas ≥ baseline**
- *Ação:* Criar golden datasets para os 4 agentes MCP em `evals/golden_datasets/`.

---

## 6. Validação de Guardrails Anti-Alucinação (FC-016)

### Ensinamento Central
- **Cenários de Teste Anti-Alucinação:**
  1. *Query sem contexto:* Enviar pergunta sobre tema inexistente no vault → Esperado: "Não tenho informação suficiente"
  2. *Query ambígua:* Enviar pergunta que pode ter múltiplas respostas → Esperado: Listar alternativas com nível de confiança
  3. *Query com dados conflitantes:* Injetar documentos contraditórios → Esperado: Sinalizar conflito
  4. *Injection attack:* Enviar prompt injection → Esperado: Rejeitar ou ignorar instrução maliciosa
- **Métricas de Alucinação:**
  - Taxa de respostas fabricadas (sem fonte no vault): Meta < 2%
  - Taxa de respostas com atribuição incorreta: Meta < 1%
- *Ação:* Adicionar cenários anti-alucinação à suíte de testes dos 4 agentes.

---

## 7. Testes de Qualidade para Código Gerado por IA (FC-013)

### Ensinamento Central
- **Todo código gerado por IA deve passar pelos mesmos critérios de qualidade** que código humano
- **Checklist de validação de código IA:**
  - [ ] Testes unitários cobrindo lógica principal
  - [ ] Testes de integração para APIs e banco
  - [ ] Sem segredos hardcoded
  - [ ] Documentação de funções públicas
  - [ ] Conformidade com engineering guidelines
  - [ ] Performance dentro dos SLOs
- *Ação:* Adicionar checklist de validação como gate obrigatório antes de merge de código gerado por IA.

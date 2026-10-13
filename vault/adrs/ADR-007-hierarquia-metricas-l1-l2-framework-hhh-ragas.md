# ADR-007: Adoção da Hierarquia de Métricas L1/L2 e Framework HHH para Avaliação Contínua de IA

## Status
Aceito

## Data
2026-10-12

## Contexto
O Second Brain utilizava uma estrutura métrica plana dividida em "Métricas de Negócio" e "Métricas de Qualidade do Sistema de IA" sem uma taxonomia formal que diferenciasse **leading indicators** (ações do time que influenciam o resultado) de **performance indicators** (qualidade do motor de IA em si). Isso dificultava:

1. A comunicação entre engenharia e stakeholders de negócio sobre "o que está funcionando".
2. A identificação de **trade-offs** entre precisão e recall ao ajustar modelos.
3. A avaliação objetiva de respostas probabilísticas de LLMs, onde não existe uma única "resposta certa".

A formação **AI Product Specialist** (Lucca Kazan — *"Medindo e provando resultado de produtos com IA"* e *"Avaliação e observabilidade: mantendo o controle dos LLMs"*) forneceu um framework estruturado para resolver esses gaps.

### Problemas Enfrentados
- Métricas técnicas de IA (Grounding Score, Latência P95) estavam no mesmo nível conceitual que métricas de negócio (MTTR, Zero Financial Leakage), dificultando a priorização de ajustes.
- Não existia um método padronizado para avaliar se uma resposta do LLM era *útil*, *honesta* e *segura* (subjetividade não tratada).
- Ausência de métricas padronizadas de RAG (Faithfulness, Context Precision) para monitorar a qualidade do pipeline de busca semântica.
- O **Golden Dataset** (150 questões de score humano curado por Hugo Melo) não tinha um protocolo formal de uso como fonte de verdade de avaliação.

## Alternativas Consideradas

### Opção A: Manter a Estrutura Plana de Métricas (2 Camadas)
- **Prós:** Simples, já implementada nos painéis do dashboard.
- **Contras:** Não distingue métricas acionáveis pelo time (L1) das métricas de motor (L2). Trade-offs de modelo ficam opacos para stakeholders. Sem avaliação padronizada de subjetividade.

### Opção B: Adotar a Hierarquia NSM → L1 → L2 com Framework HHH e RAGAS (Escolhida)
- **Prós:** Taxonomia clara e universal (Lucca Kazan, mercado de AI Products). Permite comunicar impacto de negócio (L1) separadamente da qualidade técnica (L2). HHH converte subjetividade em classificações objetivas. RAGAS é o padrão de mercado para RAG pipelines (open-source, DeepEval-compatível).
- **Contras:** Exige curadoria contínua do Golden Dataset para calibração. Requer definição precisa de "o que é sucesso" para cada contexto operacional.

### Opção C: Utilizar Exclusivamente Benchmarks de Mercado (MMLU, MATH 500, LMSYS)
- **Prós:** Compará-los externamente entre modelos de mercado.
- **Contras:** Benchmarks genéricos não capturam a qualidade do RAG operacional com documentos de ERP/Logística específicos da KIOSK Brands. Insuficientes para avaliar tarefas de domínio.

## Decisão
Adotar a **Hierarquia de Métricas em 3 Níveis** e o **Framework HHH + RAGAS** como padrão oficial de avaliação contínua do Second Brain:

1. **Nível 0 — North Star Metric (NSM):** *Autonomous Mission Throughput (AMT) com Zero Incident Rate* — volume semanal de missões operacionais concluídas e validadas autonomamente sem rollback emergencial (Meta: >= 50/semana).

2. **Nível 1 — L1 Metrics (Leading Indicators de Negócio & Feature):**
   - MTTR de Incidentes: 4h → < 5 min.
   - Zero Financial Leakage: 0 duplicidades em pedidos/etiquetas.
   - Taxa de Resolução na 1ª Interação (FCR Operacional): >= 90%.
   - Time-to-Value (TTV) de Integrações: 15 dias → 48h.

3. **Nível 2 — L2 Metrics (Performance do Motor de IA):**
   - **Framework HHH:** Helpful (>= 96%), Honest/Grounding (>= 98% factualidade com SHA-256), Harmless (0% vazamento/bypass).
   - **Métricas RAGAS:** Faithfulness >= 0.95, Answer Relevancy >= 0.92, Context Precision >= 0.90, Context Recall >= 0.95.
   - **Golden Dataset Benchmark:** Score >= 95.0/100 sobre as 150 questões de score humano.
   - **Latência & Custo:** TTFT < 400ms, P95 < 1.5s busca / < 3.5s orquestração.

4. **Método de Avaliação Dual:**
   - *Human in the Loop:* Hugo Melo cuida da revisão periódica e criação de novos casos no Golden Dataset para cenários ambíguos.
   - *LLM as a Judge:* Para escala, um modelo avaliador (separado do modelo executante) pontua cada interação nos critérios HHH com instruções padronizadas.

5. **Protocolo de Uso do Golden Dataset:**
   - Toda alteração de modelo, prompt ou dados do Vault dispara execução automática do benchmark no CI/CD.
   - Regressão no score > 2 pontos bloqueia a promoção da mudança.

## Consequências

### Positivas
- Stakeholders (Tadeu, Davi) visualizam diretamente o impacto de negócio (L1) sem precisar entender a performance técnica (L2).
- Time de engenharia tem critérios objetivos para discutir trade-offs (ex: "aumentar Faithfulness de 0.93 para 0.95 vai reduzir o FCR Operacional?").
- A combinação HHH + RAGAS é compatível com ferramentas open-source (DeepEval, Langfuse) e escala automaticamente a avaliação via LLM-as-a-Judge.
- O Golden Dataset funciona como *gate de qualidade* no CI, impedindo regressões silenciosas.

### Desafios / Riscos
- O Golden Dataset precisa de revisão periódica (mensal) para incorporar novos cenários operacionais e evitar obsolescência.
- LLM-as-a-Judge pode ter viés quando os modelos avaliados são do mesmo provedor que o juiz — mitigar usando avaliadores de provedores distintos.
- Exige disciplina para não cair na armadilha de "acurácia como métrica de vaidade" (conforme advertência de Lucca Kazan sobre dados desbalanceados).

## Times Impactados
- **Engenharia Full-Cycle (Hugo Melo):** Responsável pela curadoria do Golden Dataset e pela interpretação de trade-offs L1 vs L2.
- **Squad de Avaliação & Evals:** Implementação do pipeline automatizado de HHH + RAGAS no CI.
- **Squad de Knowledge & RAG:** Monitoramento contínuo das métricas RAGAS para garantir qualidade dos chunks recuperados.
- **Stakeholders Executivos (Tadeu, Davi):** Consumidores do dashboard de métricas L1 sem necessidade de conhecimento técnico L2.

## Referências
- [[references/02-medindo-e-provando-resultado-de-produtos-com-ia-lucca-kazan-pdf]]
- [[references/14-avalia-o-e-observabilidade-mantendo-o-controle-dos-llms-ok-pptx-microsoft-powerpoint]]
- [[product/product-vision-ai-specialist]] — Seções 4.1, 4.2 e 4.3 (Hierarquia de Métricas)
- [[ADR-006-implementacao-flowlogger-observabilidade-semaforos]] — Rastreabilidade E2E que alimenta as métricas L2

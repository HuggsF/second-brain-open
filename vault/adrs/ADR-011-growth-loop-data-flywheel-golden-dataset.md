---
type: adr
status: Aceito
date: 2026-10-12
---
# ADR-011: Growth Loop com Data Flywheel Operacional e Golden Dataset como Fonte de Verdade

## Contexto
O Second Brain executa missões operacionais de forma autônoma (diagnósticos de ERP, conciliação de pedidos, auditorias de frete), mas até o momento não existia um **ciclo de retroalimentação formal** que capturasse os resultados das execuções para melhorar continuamente a qualidade dos modelos e prompts. Os aprendizados ficavam implícitos na experiência de Hugo Melo e não eram convertidos em dados de treinamento ou avaliação.

A formação **AI Product Specialist** (Aiman Smaili — *"Go-to-Market e Lançamento de Produtos com IA"*; Lucca Kazan — *"Avaliação e observabilidade: mantendo o controle dos LLMs"*) forneceu o framework de **Growth Loops com IA** e **Data Flywheel** para resolver este gap.

### Problemas Enfrentados
- Execuções bem-sucedidas do copiloto não eram capturadas para expandir o dataset de avaliação.
- Execuções com feedback negativo ou exceções não eram transformadas em novos testes de regressão.
- O Golden Dataset (150 questões) era estático — não recebia novos cenários descobertos em produção.
- Sem loop de retroalimentação, a qualidade do sistema de IA poderia degradar silenciosamente ao longo do tempo (model drift, data drift).
- Operadores das holdings não contribuíam com feedback estruturado sobre a utilidade das respostas do copiloto.

## Alternativas Consideradas

### Opção A: Melhoria Manual sob Demanda (Reativo)
- **Prós:** Simples, sem overhead.
- **Contras:** Melhorias acontecem apenas quando há incidente grave. Não escala. Perde oportunidades de melhoria incremental contínua.

### Opção B: Data Flywheel Operacional com Curadoria Humana (Escolhida)
- **Prós:** Loop fechado e verificável. Cada execução em produção pode gerar novo dado de avaliação. Curadoria humana (Hugo Melo) garante qualidade dos anotações. Golden Dataset cresce organicamente com cenários reais. Compatível com Continuous Improvement (Fine-tuning de prompts, enriquecimento de RAG).
- **Contras:** Exige disciplina na curadoria (tempo de Hugo Melo para revisar casos candidatos). Risco de viés se a curadoria for feita exclusivamente por uma pessoa.

### Opção C: Fine-Tuning Automatizado sem Curadoria Humana
- **Prós:** Escala máxima.
- **Contras:** Sem curadoria, dados ruidosos podem degradar o modelo. Viola o princípio de Human-in-the-Loop para cenários de alta criticidade operacional.

## Decisão
Implementar o **Data Flywheel Operacional** como mecânica central de melhoria contínua do Second Brain, com 5 etapas cíclicas:

### O Ciclo do Data Flywheel

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     DATA FLYWHEEL DO SECOND BRAIN                       │
│                                                                          │
│  1. USO OPERACIONAL                                                      │
│     Holdings Touti, Amavia, Yes! executam missões via copiloto           │
│                         │                                                │
│                         ▼                                                │
│  2. CAPTURA DE TELEMETRIA                                                │
│     FlowLogger registra traces (batch_trace_id), latência, custos,      │
│     resultados HHH e feedback do usuário                                 │
│                         │                                                │
│                         ▼                                                │
│  3. CURADORIA HUMANA                                                     │
│     Hugo Melo revisa:                                                    │
│     • Execuções com feedback negativo                                    │
│     • Exceções e rollbacks capturados                                    │
│     • Casos ambíguos que revelam gaps no Vault                           │
│                         │                                                │
│                         ▼                                                │
│  4. EXPANSÃO DO GOLDEN DATASET                                           │
│     Novos pares (input, output_esperado, score_humano) adicionados       │
│     às 150 questões existentes                                           │
│     Benchmark re-executado automaticamente no CI                         │
│                         │                                                │
│                         ▼                                                │
│  5. REFINAMENTO DE MODELOS & PROMPTS                                     │
│     • Ajuste de system prompts e few-shot examples                       │
│     • Enriquecimento da base de RAG com novos documentos                 │
│     • Re-roteamento de modelos por tier se trade-off custo/quality       │
│                         │                                                │
│                         ▼                                                │
│     Volta ao passo 1: maior adoção e confiança da holding               │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1. Fontes de Dados do Flywheel
- **Logs de decisão do FlowLogger:** Cada missão gera um trace estruturado com `batch_trace_id`, tempo de execução, modelo utilizado, tokens consumidos e resultado dos Quality Gates.
- **Feedback direto de usuários:** Operadores podem pontuar execuções com 👍/👎 no dashboard do copiloto.
- **Monitoramento de exceções:** Exceções, rollbacks e alarmes automaticamente candidatos a novos casos no Golden Dataset.
- **Exploração de logs de interações:** Análise periódica (semanal) de logs para detectar padrões de uso emergentes.

### 2. Protocolo de Curadoria do Golden Dataset
1. Hugo Melo revisa semanalmente os candidatos gerados pelo flywheel.
2. Para cada caso aprovado, define:
   - **Input:** A pergunta/tarefa operacional real que originou a execução.
   - **Output Esperado:** A resposta ou ação ideal com base no conhecimento do Vault.
   - **Score Humano:** Pontuação de 0 a 100 nos critérios HHH (Helpful, Honest, Harmless).
3. O caso é adicionado ao Golden Dataset e o benchmark é re-executado no CI.
4. Se o score do benchmark cair > 2 pontos, é investigada a causa antes de merge.

### 3. Métricas do Flywheel
- **Taxa de Contribuição:** # de novos casos adicionados ao Golden Dataset por mês (Meta: >= 10/mês).
- **Taxa de Cobertura:** % de categorias operacionais (Logística, ERP, CRM, Fiscal) representadas no dataset.
- **Trend de Score:** Evolução do score médio do benchmark ao longo dos trimestres (meta: crescente ou estável).
- **Adoption Rate:** # de missões executadas por semana pelas holdings (correlação com confiança no sistema).

### 4. Boas Práticas de Melhoria Contínua (Lucca Kazan)
- Documento de resumo das avaliações atualizado a cada ciclo.
- Registro de casos identificados por monitoramento.
- Coleta e análise estruturada de feedback.
- Documentação/postmortem de erros críticos.
- Validação de melhorias antes do lançamento via Golden Evals.

## Consequências

### Positivas
- O sistema torna-se **auto-aprimorante**: cada execução operacional contribui potencialmente para a evolução da qualidade.
- O Golden Dataset cresce organicamente com cenários reais das holdings, não com dados sintéticos.
- A curadoria humana mantém a qualidade e evita a contaminação do dataset com ruído.
- Stakeholders executivos podem acompanhar a evolução da qualidade do sistema via trend de score no dashboard.
- O ciclo de retroalimentação cria um **moat competitivo**: quanto mais as holdings usam o Second Brain, melhor ele fica, atraindo ainda mais uso.

### Desafios / Riscos
- Se Hugo Melo não dedicar tempo semanal à curadoria, o flywheel estagna — mitigar automatizando a triagem de candidatos (LLM-as-a-Judge pré-filtra casos com score HHH < 80).
- Viés de curadoria por uma única pessoa — mitigar diversificando a revisão quando operadores das holdings forem onboardados.
- Volume de logs pode crescer rapidamente — mitigar com retenção de 90 dias para logs detalhados e permanente para candidatos aprovados.

## Times Impactados
- **Engenharia Full-Cycle (Hugo Melo):** Curador principal do Golden Dataset e responsável por interpretar os resultados do flywheel.
- **Squad de Avaliação & Evals:** Mantém o pipeline de benchmark automatizado no CI e gera relatórios de trend.
- **Squad de Knowledge & RAG:** Enriquece a base de RAG com novos documentos identificados pelo flywheel.
- **Operações (Touti, Amavia, Yes!):** Geradores de feedback e casos de uso reais que alimentam o ciclo.

## Referências
- [[references/20-go-to-market-e-lancamento-de-produtos-com-ia-aiman-mustafa-smaili]]
- [[references/14-avaliacao-e-observabilidade-mantendo-o-controle-dos-llms]]
- [[references/02-medindo-e-provando-resultado-de-produtos-com-ia-lucca-kazan]]
- [[product/product-vision-ai-specialist]] — Seção 9 (Growth Loop & Data Flywheel)
- [[ADR-007-hierarquia-metricas-l1-l2-framework-hhh-ragas]] — Framework HHH usado na curadoria
- [[ADR-006-implementacao-flowlogger-observabilidade-semaforos]] — FlowLogger alimenta o flywheel

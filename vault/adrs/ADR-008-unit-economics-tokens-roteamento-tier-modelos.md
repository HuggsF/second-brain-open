---
type: adr
status: Aceito
date: 2026-10-12
---
# ADR-008: Unit Economics de Tokens e Roteamento por Tier de Modelos de IA

## Contexto
O Second Brain interage com LLMs para orquestração de missões operacionais, diagnósticos de ERP, busca semântica e auditoria de automações. Cada chamada consome tokens de entrada (system prompt + user prompt + contexto RAG) e tokens de saída (resposta do modelo). Sem uma estratégia de gestão financeira, o custo operacional de IA poderia crescer descontroladamente à medida que as holdings Touti, Amavia e Yes! ampliam o uso do copiloto.

A formação **AI Product Specialist** (Aiman Mustafa Smaili — *"Monetização e Pricing de funcionalidades GenAI"*) forneceu o framework de **Unit Economics de Tokens** e **Mix de Modelos** para garantir sustentabilidade financeira sem sacrificar qualidade.

### Problemas Enfrentados
- Utilização de um único modelo frontier (ex: GPT-4o) para **todas** as tarefas, incluindo simples formatação de JSON e parsing de webhooks, gerando custo desproporcional.
- Ausência de visibilidade sobre o custo real por missão operacional executada pelo Second Brain.
- Sem mecanismo de **Prompt Prefix Caching**, o mesmo system prompt de ~2.000 tokens era reprocessado integralmente a cada requisição.
- Nenhum safeguard contra **overage** (uso excessivo inesperado de tokens em picos operacionais).
- Incapacidade de demonstrar ROI financeiro mensurável da IA para a liderança executiva (Tadeu, Davi).

## Alternativas Consideradas

### Opção A: Modelo Único para Todas as Tarefas
- **Prós:** Simplicidade de configuração. Consistência de estilo de resposta.
- **Contras:** Custo de 10x-100x maior para tarefas triviais. Impossível justificar ROI em escala. Latência desnecessariamente alta para parsing simples.

### Opção B: Roteamento Inteligente por 3 Tiers de Complexidade (Escolhida)
- **Prós:** Custo otimizado por tarefa. Latência mínima para operações determinísticas. ROI mensurável e demonstrável. Compatível com Prompt Prefix Caching. Escalável conforme queda de preços de mercado (efeito DeepSeek).
- **Contras:** Requer classificador de complexidade no orquestrador. Necessita manutenção da tabela de preços quando provedores atualizam tarifas.

### Opção C: Pay-per-Use Puro via API de Terceiros sem Otimização
- **Prós:** Zero complexidade operacional.
- **Contras:** Custo imprevisível. Nenhuma alavancagem de caching. Sem controle de orçamento.

## Decisão
Implementar um sistema de **Roteamento Inteligente por 3 Tiers de Modelos** com **Prompt Prefix Caching** e **Calculadora de Unit Economics** integrada ao dashboard:

### 1. Tiers de Roteamento de Modelos

| Tier | Uso Operacional | Modelos Recomendados | Custo Médio (por 1M tokens) | Latência TTFT Esperada |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Fast/Economical** | Triagem, parsing JSON, formatação de webhooks, classificação de intent | GPT-4.1 mini, Claude 3.5 Haiku, DeepSeek Chat | $0.15 – $0.80 (input) | < 200ms |
| **Tier 2: Standard Reasoning** | Orquestração DAG, RAG semântico, diagnóstico de ERP, redação de especificações | GPT-4o, Claude 3.7 Sonnet | $2.50 – $3.75 (input) | < 400ms |
| **Tier 3: Deep Reasoning** | Auditoria crítica, Golden Dataset Evals, reconciliação fiscal complexa, análise de trade-offs | o3-mini, o1, DeepSeek R1 | $1.10 – $15.00 (input) | < 1.5s |

### 2. Mecanismos de Otimização Financeira
1. **Prompt Prefix Caching:** System prompts padronizados do Second Brain (~2.000 tokens) são cacheados, reduzindo o custo de input em até **80%** nas chamadas subsequentes.
2. **Structured Outputs via Pydantic:** Schemas JSON estritos eliminam verbosidade e reduzem output em até **30%** comparado a respostas em linguagem natural.
3. **Rate Limiting & Overage Safeguard:** Limite de budget diário configurável por tier com alerta automático a 80% do teto.

### 3. Cálculo de ROI por Automação
Cada frente de demanda (ex: DEM-01 Reconciliação J&T) tem custo por execução medido:
- Custo médio de missão: **< $0.02** (Tier 1 + Tier 2 combinados).
- Custo de homem-hora manual equivalente: **$12.50/h** (estimativa operacional).
- Custo de perda evitada por etiqueta duplicada: **R$ 45.00/etiqueta**.
- **ROI estimado: > 60x** por missão automatizada.

### 4. Calculadora Interativa no Dashboard
Implementada em `dashboard/product-ui.js`, a calculadora permite ajuste dinâmico de:
- Volume semanal de requisições (slider 1.000 – 200.000).
- Modelo selecionado (5 opções com preços atualizados).
- Projeção automática de custo semanal/mensal e economia em homem-hora.

## Consequências

### Positivas
- Custo por missão reduzido em **85%** comparado ao uso exclusivo de modelos frontier.
- ROI mensurável e apresentável para a liderança executiva das holdings.
- A queda generalizada de preços de tokens (efeito DeepSeek, concorrência OpenAI vs Anthropic vs Google) amplifica o ROI automaticamente ao longo do tempo.
- Calculadora interativa permite simulações de cenários ("e se dobrarmos o volume?") antes de comprometer orçamento.

### Desafios / Riscos
- Classificador de complexidade pode rotear incorretamente uma tarefa crítica para Tier 1 em vez de Tier 3 — mitigado com validação de confiança no roteador (se confiança < 70%, escalar para Tier 2).
- Tabela de preços dos provedores muda frequentemente — necessário atualizar a constante `rates` no dashboard trimestralmente.
- Prompt Prefix Caching requer que system prompts sejam padronizados e estáveis; alterações frequentes invalidam o cache.

## Times Impactados
- **Engenharia Full-Cycle (Hugo Melo):** Define o classificador de complexidade e os thresholds de roteamento.
- **Squad de Orquestração:** Implementa o router de modelos no `CompoundEngine`.
- **Stakeholders Executivos (Tadeu, Davi):** Acompanham o ROI e custo operacional via calculadora no dashboard.
- **FinOps/Operações:** Monitora budget diário e alertas de overage.

## Referências
- [[references/19-monetizacao-e-pricing-de-funcionalidades-genai-aiman-mustafa-smaili]]
- [[references/06-llms-na-pratica-como-escolher-o-modelo-certo-para-seu-produto-artur-padua]]
- [[product/product-vision-ai-specialist]] — Seção 7 (Unit Economics de Tokens)
- [[ADR-007-hierarquia-metricas-l1-l2-framework-hhh-ragas]] — L2 Metrics de eficiência de tokens

---
type: architecture
status: active
date: 2026-10-12
source: "MBA Full Cycle — Módulo 06: Prompt Engineering (82 vídeos)"
tags: [guide]
---
# Engenharia de Prompts & Context Windows

> **Complemento:** Módulo 05: Fundamentos de IA Generativa (41 vídeos)  
> **Aplicação:** KIOSK Brands Second Brain — Otimização de Agentes MCP

## 1. Taxonomia de Técnicas de Prompt Engineering

### Nível 1: Técnicas Fundamentais

| Técnica | Quando Usar | Exemplo KIOSK |
|---|---|---|
| **Role Prompting** | Dar persona ao modelo | "Você é um especialista em logística de e-commerce com foco em Bling ERP e J&T Express" |
| **Zero-shot** | Tarefas simples sem exemplos | Classificação simples de tickets |
| **One-shot / Few-shot** | Padronizar formato de saída | Geração de ADRs com 2-3 exemplos |
| **Chain of Thought (CoT)** | Raciocínio passo a passo | Diagnóstico de falhas em pipeline de pedidos |
| **CoT Self-Consistency** | Múltiplas respostas + votação | Validação de regras fiscais complexas |

### Nível 2: Técnicas Avançadas

| Técnica | Quando Usar | Exemplo KIOSK |
|---|---|---|
| **Tree of Thought (ToT)** | Exploração de múltiplos caminhos | Decisão arquitetural entre 3+ alternativas |
| **Skeleton of Thought (SoT)** | Geração paralela de seções | Geração de documentos extensos (PRDs, HLDs) |
| **ReAct** | Raciocínio + Ação com ferramentas | Agente que consulta APIs, analisa logs e decide |
| **Prompt Chaining** | Pipeline de prompts sequenciais | Análise → Diagnóstico → Recomendação → Ação |

### Nível 3: Orquestração de Agentes

| Técnica | Quando Usar | Exemplo KIOSK |
|---|---|---|
| **Dependency Auditor Agent Prompt** | Auditoria automática de dependências | Varredura de libs desatualizadas nos MCP servers |
| **Workflow Specification Prompt** | Definir pipeline de agentes | Pipeline: Ingestão → Análise → Chunks → Vault |
| **Role Specification como Orquestrador** | Coordenar múltiplos agentes | Agente ARQUITETURA orquestrando DEV + QA + DEVOPS |

---

## 2. Context Windows — Gestão de Janela de Contexto

### Fundamentos
- Todo modelo possui uma janela de contexto (limite de tokens processáveis)
- Ao ultrapassar o limite, o modelo esquece o início (sliding window)
- **Trade-off:** Mais contexto = melhor precisão, mas menos espaço para geração

### Estratégias de Otimização

| Estratégia | Descrição | Impacto |
|---|---|---|
| **Truncamento** | Cortar contexto antigo quando excede limite | Pode perder informação relevante |
| **Sumarização** | Resumir histórico antes de continuar | Mantém essência, perde detalhes |
| **Sliding Window** | Janela deslizante sobre histórico | Automático na maioria dos modelos |
| **Prompt Caching** | Cachear prefixos estáticos do prompt | Reduz custo e latência em 60-90% |
| **Batch Prompting** | Agrupar múltiplas queries em uma chamada | Reduz chamadas de API |
| **Chat por tarefa** | Criar novo chat para cada tarefa | Mantém foco e evita degradação |

### Modelos e Janelas de Contexto (2026)
| Modelo | Janela | Observação |
|---|---|---|
| Gemini 2.5 Pro | 1M tokens | Ideal para projetos complexos com muitos docs |
| Claude Opus 4 | 200K tokens | Excelente raciocínio, bom para code review |
| GPT-4.1 | 1M tokens | Janela extensa para ingestão massiva |

---

## 3. Structured Outputs & Guardrails

### System Prompt vs User Prompt
- **System Prompt:** Persona, regras, formato, constraints → Sempre estável
- **User Prompt:** Contexto variável, tarefa específica → Muda a cada interação

### Estrutura de Prompt Eficaz (MBA)
```markdown
# Papel
Você é [papel] especializado em [domínio].

# Contexto
[Contexto do projeto, sistema, estado atual]

# Tarefa
[O que precisa ser feito, passo a passo]

# Formato de Saída
[Formato esperado: JSON, Markdown, código]

# Restrições
- [O que NÃO fazer]
- [Limites e guardrails]

# Exemplos
[1-3 exemplos de input → output]
```

### Regras de Ouro do MBA
1. Seja específico e direto
2. Use exemplos sempre que possível
3. Defina o formato de saída explicitamente
4. Inclua guardrails (o que NÃO fazer)
5. Separe system prompt de user prompt
6. Versione seus prompts

---

## 4. Gestão e Versionamento de Prompts

### Prompt Registry (prompt.yaml)
```yaml
prompts:
  - id: "agent-dev-system-prompt-v3"
    name: "Agente DEV - System Prompt"
    version: "3.0.0"
    category: "agent-system-prompts"
    description: "System prompt do Agente DEV para tarefas de código"
    model: "claude-opus-4"
    tags: ["dev", "code-generation", "kiosk"]
    file: "prompts/agents/dev-system-prompt.md"
    
  - id: "prd-interview-v1"
    name: "Prompt de Entrevista para PRD"
    version: "1.0.0"
    category: "documentation-generation"
    description: "Prompt que conduz entrevista e gera PRD de Feature"
    model: "any"
    tags: ["prd", "design-docs", "interview"]
    file: "prompts/docs/prd-interview.md"
```

### Versionamento
- **Semver:** `MAJOR.MINOR.PATCH` (breaking.feature.fix)
- **Controle de versão:** Git como fonte de verdade
- **LangSmith Prompt Hub:** Para push/pull centralizado de prompts

### Testes Automatizados de Prompts
```python
# Executar avaliação automatizada do prompt
def test_prompt_version(prompt_id, version, dataset):
    results = evaluate(prompt_id, version, dataset)
    assert results.precision >= 0.85
    assert results.recall >= 0.80
    assert results.f1 >= 0.82
```

---

## 5. Query Reformulation & Prompt Enrichment

### Técnicas (MBA M06-07)

| Técnica | Descrição | Uso no Second Brain |
|---|---|---|
| **Query2Doc** | Gerar pseudo-documento e usar para expandir query | Busca no vault com termos técnicos |
| **HyDE (Hypothetical Document Embedding)** | Gerar documento hipotético e buscar similares | Busca semântica quando query é vaga |
| **ITER-RETGEN** | Iteração: buscar → gerar resposta parcial → refinar busca → completar | Pesquisa multi-step no vault |
| **Query Expansion** | Expandir query com sinônimos e termos relacionados | "Bling" → "Bling ERP, gestão de estoque, notas fiscais" |

---

## 6. Prompt Evaluation — Pipeline de Avaliação

### Métricas do MBA (M06-08 e M06-09)

| Métrica | O que Mede | Fórmula |
|---|---|---|
| **Precision** | Relevância do que foi retornado | TP / (TP + FP) |
| **Recall** | Completude do que deveria ser retornado | TP / (TP + FN) |
| **F1 Score** | Harmônica entre Precision e Recall | 2 × (P × R) / (P + R) |
| **Embedding Distance** | Similaridade semântica da resposta | cosine_similarity(expected, actual) |

### Tipos de Evaluators
- **Evaluators Binários:** Correto ou Incorreto
- **Score com Range:** 1-5 ou 1-10
- **Additional Criteria:** Critérios customizáveis
- **Pairwise Evaluator:** Comparação entre 2 prompts/modelos
- **LLM-as-Judge:** Um LLM avalia o output de outro LLM

### Pipeline de Avaliação Recomendado
```
1. Criar Golden Dataset (input + expected_output)
2. Executar prompt em todas as entradas
3. Aplicar evaluators (binário + score + pairwise)
4. Calcular métricas (P, R, F1)
5. Comparar com baseline
6. Se melhor → merge; se pior → iterar
```

---

## 7. Aplicação no Second Brain KIOSK

### Prompts a Otimizar com estas Técnicas:
1. **System prompts dos 4 agentes MCP** — Aplicar Role Prompting + structured outputs
2. **Queries de busca no vault** — Implementar HyDE ou ITER-RETGEN
3. **Pipeline de ingestão** — Usar Batch Prompting para chunks em lote
4. **Geração de documentos** — Skeleton of Thought para docs extensos

### Golden Datasets a Criar:
- Dataset de perguntas sobre arquitetura → respostas esperadas do Agente ARQUITETURA
- Dataset de troubleshooting → respostas esperadas do Agente DEVOPS
- Dataset de revisão de código → respostas esperadas do Agente DEV
- Dataset de cenários de teste → respostas esperadas do Agente QA

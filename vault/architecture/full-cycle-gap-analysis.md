# 🔍 Gap Analysis: Second Brain vs Padrões MBA Full Cycle

> **Data:** 2026-10-12  
> **Fonte de Referência:** MBA Full Cycle — Engenharia de Software com IA 2026  
> **Repositório Auditado:** `c:\Huggs\seccond-brain` (core/, dashboard/, mcp_servers/, vault/, tests/)  
> **Status:** `#status/active` | `#type/gap-analysis`

---

## Resumo Executivo

O Second Brain da KIOSK Brands já possui uma base sólida com 12 ADRs, 6 guias de System Design, 4 bases de inteligência por time, dashboard com grafo navegável, pipeline de ingestão de conteúdo (Drive, PM3, System Design), e infraestrutura de observabilidade. No entanto, comparado com as melhores práticas ensinadas no MBA Full Cycle, **identificamos 14 gaps críticos** organizados em 5 dimensões.

---

## Dimensão 1: Design Docs & Documentação Assistida por IA

### ✅ O que já temos
- 12 ADRs formalizados (ADR-001 a ADR-012)
- Templates de ADR no vault
- PRD do Second Brain Platform v2
- Index de System Design

### ❌ Gaps Identificados

| # | Gap | MBA Referência | Impacto | Prioridade |
|---|---|---|---|---|
| G-01 | **Ausência de PRDs de Feature padronizados** — Não temos o modelo de PRD de Feature com 12 seções estruturadas (Resumo, Contexto, Objetivos/Métricas, Escopo, RFs, RNFs, Arquitetura, Decisões/Trade-offs, Dependências, Riscos, Critérios de Aceitação, Testes) | M07-03 (PRDs) | Alto | 🔴 Crítico |
| G-02 | **Sem prompt de entrevista para geração de PRD** — O MBA ensina um prompt estruturado de 12 etapas que conduz entrevista e gera PRD automaticamente. Não temos nenhum prompt equivalente no vault | M07-03 (Prompt Entrevista) | Alto | 🔴 Crítico |
| G-03 | **Sem Feature Design Docs (FDD)** — Não temos documentação de design de feature com HLD/FDD. O MBA ensina HLD (High Level Design) e FDD com prompts de geração | M07-04 (Design & Arquitetura) | Alto | 🔴 Crítico |
| G-04 | **Sem diagramas C4 formalizados** — Os ADRs e guias existentes não possuem diagramas C4 (Context, Container, Component, Code). O MBA dedica 14 aulas a diagramas com geração por IA | M07-05 (Diagramas C4 + Mermaid) | Médio | 🟡 Alto |
| G-05 | **Engineering Guidelines inexistentes** — Não temos um documento formal de Software Development Guidelines cobrindo stack, padrões de código, pre-commit, linting e formatação | M07-07 (Engineering Guidelines) | Alto | 🔴 Crítico |

---

## Dimensão 2: Prompt Engineering & Gestão de Prompts

### ✅ O que já temos
- Prompts nos agentes MCP (embutidos no código)
- System prompts nos `mcp_servers/`
- CLAUDE.md com regras básicas

### ❌ Gaps Identificados

| # | Gap | MBA Referência | Impacto | Prioridade |
|---|---|---|---|---|
| G-06 | **Sem prompt registry centralizado** — Prompts estão espalhados no código dos MCP servers sem versionamento, categorização ou arquivo `prompt.yaml` | M06-06 (Gestão e versionamento) | Alto | 🔴 Crítico |
| G-07 | **Sem pipeline de Prompt Evaluation** — Não temos evaluators, datasets de referência, métricas (Precision, Recall, F1) ou LLM-as-Judge para avaliar qualidade dos prompts dos agentes | M06-08 e M06-09 (Evaluation) | Alto | 🔴 Crítico |
| G-08 | **Sem técnicas de Query Reformulation/Enrichment** — A busca no vault não implementa Query2Doc, HyDE ou ITER-RETGEN para melhorar recall | M06-07 (Query reformulation) | Médio | 🟡 Alto |
| G-09 | **Sem batch prompting para processamento em lote** — O pipeline de ingestão processa documentos um a um sem batch prompting | M06-03 (Batch Prompting) | Médio | 🟡 Alto |

---

## Dimensão 3: Desenvolvimento de Aplicações com IA & Skills

### ✅ O que já temos
- CLAUDE.md como arquivo de inicialização
- MCP servers funcionais (4 servidores)
- Pipeline de ingestão automatizado
- Docker-compose para infra local

### ❌ Gaps Identificados

| # | Gap | MBA Referência | Impacto | Prioridade |
|---|---|---|---|---|
| G-10 | **Sem Project Skills formalizados** — O MBA ensina Skills como unidades de conhecimento reutilizável com SKILL.md, frontmatter, progressive disclosure e conditional details. Não temos skills personalizadas para os 4 agentes | M08-core (vídeos 25-47) | Alto | 🔴 Crítico |
| G-11 | **Sem Spec Driven Development** — Não temos especificações técnicas que dirigem o desenvolvimento antes do código. O MBA ensina SDD como pilar | M08-core (vídeo 06) | Médio | 🟡 Alto |
| G-12 | **Sem State.local.md** — O MBA ensina o uso de `State.local.md` para manter o estado atual do desenvolvimento. Não temos equivalente | M03-01 (Quick Wins) | Baixo | 🟢 Médio |

---

## Dimensão 4: Avaliação Contínua & Qualidade

### ✅ O que já temos
- Evals básicos no diretório `evals/`
- pytest.ini configurado
- Diretório `tests/` com estrutura

### ❌ Gaps Identificados

| # | Gap | MBA Referência | Impacto | Prioridade |
|---|---|---|---|---|
| G-13 | **Sem datasets de golden examples para avaliação** — O MBA ensina a criar datasets estruturados com input/expected_output para Prompt Evaluation. Não temos golden datasets | M06-08 (Datasets) | Alto | 🔴 Crítico |
| G-14 | **Sem PRP (Product Requirement Prompt) workflow** — O MBA demonstra PRPs como unidade de trabalho atômica que combina PRD + contexto de código + agente para gerar código pronto para produção. Não temos esse workflow | M03-01 (PRPs) | Alto | 🔴 Crítico |

---

## Matriz de Priorização

```
🔴 CRÍTICOS (Implementar imediato — Fase 1):
├── G-01: PRDs de Feature padronizados
├── G-02: Prompt de entrevista para PRD
├── G-05: Engineering Guidelines
├── G-06: Prompt Registry centralizado
├── G-07: Pipeline de Prompt Evaluation
├── G-10: Project Skills formalizados
├── G-13: Golden Datasets de avaliação
└── G-14: PRP Workflow

🟡 ALTOS (Implementar em 30 dias — Fase 2):
├── G-03: Feature Design Docs (FDD)
├── G-04: Diagramas C4 formalizados
├── G-08: Query Reformulation/Enrichment
├── G-09: Batch Prompting
└── G-11: Spec Driven Development

🟢 MÉDIOS (Implementar em 60 dias — Fase 3):
└── G-12: State.local.md
```

---

## Plano de Ação Consolidado

| Fase | Prazo | Gaps Endereçados | Entregáveis |
|---|---|---|---|
| **Fase 1 — Foundation** | Semana 1-2 | G-01, G-02, G-05, G-06 | Templates PRD/FDD no vault, Prompt Registry YAML, Engineering Guidelines |
| **Fase 2 — Evaluation** | Semana 3-4 | G-07, G-13, G-14 | Pipeline Eval com LangSmith, Golden Datasets, PRP Templates |
| **Fase 3 — Skills & SDD** | Semana 5-6 | G-10, G-11 | Skills KIOSK para 4 agentes, Spec Driven Dev workflow |
| **Fase 4 — Advanced** | Semana 7-8 | G-03, G-04, G-08, G-09 | FDDs, C4 Diagrams, Query Enrichment, Batch Prompting |
| **Fase 5 — Polish** | Semana 9-10 | G-12 | State tracking, dashboard updates |

---

> [!IMPORTANT]
> Os gaps G-06 (Prompt Registry) e G-07 (Prompt Evaluation) são os mais estratégicos: sem eles, qualquer melhoria nos prompts dos agentes é feita "no escuro", sem métricas de qualidade.

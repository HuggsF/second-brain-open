---
type: adr
status: Aceito
date: 2026-10-12
author: Huggs (via Agente ARQUITETURA)
related: [ADR-007, ADR-011, ADR-012]
---
# ADR-013: Adoção de Padrões do MBA Full Cycle em Engenharia de Software com IA

## Contexto

A KIOSK Brands adquiriu o MBA Full Cycle em Engenharia de Software com IA 2026, uma formação completa com 321 vídeos, 22 PDFs, 7 pacotes de código e desafios técnicos cobrindo:

1. **Fundamentos de IA Generativa** — Transformers, tokens, LLMs, RAG, embeddings
2. **Prompt Engineering** — 82 aulas cobrindo técnicas de zero-shot a LLM-as-Judge
3. **Design Docs com IA** — PRDs, HLDs, FDDs, C4, ADRs, Engineering Guidelines
4. **Desenvolvimento de Aplicações com IA** — Skills, Context Engineering, PRPs, SDD
5. **System Design (Bônus)** — Estudos de caso Uber/Instagram, DevOps, SRE, resiliência

O Second Brain da KIOSK já possui uma base sólida (12 ADRs, 6 guias de System Design, 4 bases de inteligência por time, dashboard), mas a análise de gaps revelou 14 gaps distribuídos em 5 dimensões ao comparar com os padrões do MBA.

## Alternativas Consideradas

### 1. Não adotar padrões formais (manter ad-hoc)
- **Prós:** Zero overhead
- **Contras:** Inconsistência crescente, prompts não avaliados, documentação fragmentada
- **Rejeitada:** Os 14 gaps identificados mostram que o approach ad-hoc já está gerando dívida técnica

### 2. Adotar apenas Design Docs sem Prompt Engineering
- **Prós:** Menor escopo de mudança
- **Contras:** Perde-se a dimensão de avaliação contínua dos agentes
- **Rejeitada:** Os agentes MCP são o core do Second Brain; sem eval, operamos no escuro

### 3. Adotar um framework externo (ex: DORA, Team Topologies)
- **Prós:** Frameworks bem estabelecidos
- **Contras:** Não cobrem IA generativa, prompts e skills
- **Rejeitada:** O MBA Full Cycle é mais específico para nosso contexto de engenharia com IA

---

## Decisão

Adotar formalmente os seguintes padrões do MBA Full Cycle como referência para o ecossistema do Second Brain e para os 4 Agentes Especialistas da KIOSK:

### 1. PRD de Feature como documento padrão de especificação
- Estrutura de 12 seções (Resumo, Contexto, Objetivos, Escopo, RFs, RNFs, Arquitetura, Decisões, Dependências, Riscos, Critérios, Testes)
- Prompt de entrevista estruturado para geração automatizada
- Exportação opcional em JSON com chaves em inglês
- **Template:** `vault/_templates/prd-feature-template.md`

### 2. Prompt Registry centralizado com versionamento
- Arquivo `vault/prompts/prompt-registry.yaml` como catálogo central
- Versionamento semântico (MAJOR.MINOR.PATCH)
- Categorização por domínio (agent-system, documentation, evaluation)
- Integração futura com LangSmith Prompt Hub

### 3. Pipeline de Prompt Evaluation
- Golden Datasets para cada agente
- Evaluators: binário + score + pairwise + LLM-as-Judge
- Métricas obrigatórias: Precision ≥ 0.85, Recall ≥ 0.80, F1 ≥ 0.82
- Execução automatizada em CI/CD

### 4. Project Skills para os 4 Agentes
- Cada agente terá seu diretório de skills com SKILL.md
- Progressive disclosure e conditional details
- Skills reutilizáveis entre agentes quando aplicável

### 5. Context Engineering como prática padrão
- Documentos de contexto obrigatórios: README indexado, ADRs, Guidelines, State.local.md
- Uso de Context7 via MCP Server para documentação de libs
- PRPs (Product Requirement Prompts) como unidade de trabalho para features complexas

### 6. Engineering Guidelines formalizadas
- Stack de tecnologias documentada
- Padrões de código, testes e deployment
- Pre-commit hooks para validação automática

## Consequências

### Positivas
- **Padronização:** Todos os documentos técnicos seguem templates validados por profissionais de mercado
- **Rastreabilidade:** Cada feature terá PRD → FDD → ADR → Código → Testes
- **Qualidade mensurável:** Pipeline de eval com métricas objetivas
- **Produtividade:** Skills e PRPs reduzem tempo de onboarding de novos chats/agentes
- **Governança:** Prompt Registry evita drift e prompts não versionados

### Negativas
- **Overhead inicial:** Criação de templates, golden datasets e skills demanda esforço upfront
- **Curva de aprendizado:** Times precisam se familiarizar com novos workflows
- **Manutenção:** Prompt Registry e Skills precisam de manutenção contínua

## Implementação

| Fase | Prazo | Entregáveis |
|---|---|---|
| Fase 1 (Foundation) | Semana 1-2 | Templates PRD/FDD, Prompt Registry, Guidelines |
| Fase 2 (Evaluation) | Semana 3-4 | Pipeline Eval, Golden Datasets, PRP Templates |
| Fase 3 (Skills & SDD) | Semana 5-6 | Skills dos 4 agentes, SDD workflow |
| Fase 4 (Advanced) | Semana 7-8 | Query Enrichment, Batch Prompting, C4 |
| Fase 5 (Polish) | Semana 9-10 | State tracking, dashboard updates |

## Referências
- MBA Full Cycle — Engenharia de Software com IA 2026 (Módulos 04-08)
- `vault/architecture/full-cycle-gap-analysis.md` — Análise de gaps completa
- `vault/architecture/full-cycle/` — Guias técnicos (01 a 04)
- `extracted_full_cycle/full_cycle_manifest.json` — Manifesto do material

# 📐 Design Docs com IA — Padrão de Especificação Técnica

> **Origem:** MBA Full Cycle — Módulo 07: Design Docs com IA  
> **Aplicação:** KIOSK Brands Second Brain — Templates para 4 Agentes Especialistas  
> **Status:** `#status/active` | `#type/guide` | **Data:** 2026-10-12

---

## 1. Visão Geral

O MBA Full Cycle estabelece uma hierarquia completa de documentação técnica assistida por IA, dividida em:

```
📋 PRD (Product Requirement Document)
├── PRD de Alto Nível (visão de produto)
└── PRD de Feature (requisitos detalhados por feature)

📐 Design & Arquitetura
├── HLD (High Level Design Document)
├── FDD (Feature Design Document)
└── Diagramas C4 + Mermaid

📝 Architecture Decision Records (ADRs)
├── ADR Clássico
└── MADR (Markdown Any Decision Record)

📏 Engineering Guidelines
└── Software Development Guidelines
```

---

## 2. PRD de Feature — Estrutura Completa (12 seções)

O PRD de Feature é o documento central que conecta negócio e engenharia. Baseado nos exemplos do MBA (Catálogo eCommerce e Rate Limiter):

### Seções Obrigatórias:

1. **Resumo** — 2-3 frases explicando o que a feature faz e por que existe
2. **Contexto e Problema** — Público-alvo, cenários de uso, local de implantação, problemas priorizados
3. **Objetivos e Métricas** — Tabela `Objetivo | Métrica | Meta`
4. **Escopo** — Incluso / Fora de escopo
5. **Requisitos Funcionais** — Para cada RF: nome, descrição, fluxo principal, fluxos alternativos, erros previstos, prioridade
6. **Requisitos Não-Funcionais** — Performance (P95), disponibilidade (%), segurança, observabilidade, confiabilidade, compliance, acessibilidade
7. **Arquitetura e Abordagem** — Abordagem geral, componentes, integrações
8. **Decisões e Trade-offs** — Cada decisão com justificativa e trade-off
9. **Dependências** — Técnicas, organizacionais, externas
10. **Riscos e Mitigação** — Para cada risco: probabilidade, impacto, mitigação (pode ser lista), plano de contingência
11. **Critérios de Aceitação** — Checklist objetivo e verificável
12. **Testes e Validação** — Tipos de teste obrigatórios + estratégia

### Prompt de Entrevista para Geração de PRD

O MBA disponibiliza um prompt de entrevista estruturado em 12 etapas que:
- Faz uma pergunta por vez e aguarda resposta
- Ao final de cada etapa, resume e pede confirmação
- Aplica defaults inteligentes (P95 < 150ms, 99.9% uptime, etc.)
- Gera PRD em Markdown + exporta opcionalmente em JSON com chaves em inglês
- Executa checagens de consistência antes de finalizar

### JSON Schema do PRD (chaves em inglês)

```json
{
  "meta": {"product": "", "feature": "", "prd_owner": "", "version": "", "date": ""},
  "context": {
    "summary": "",
    "target_audience": [],
    "key_use_cases": [],
    "deployment_context": {"type": "existing_system|new_system", "description": ""},
    "problems": [{"description": "", "impact": "", "priority": "high|medium|low"}]
  },
  "goals": [{"goal": "", "metric": "", "target": ""}],
  "scope": {"in_scope": [], "out_of_scope": []},
  "functional_requirements": [{"id": "FR-001", "name": "", "description": "", "main_flow": [], "alternative_flows": [], "known_errors": [], "priority": ""}],
  "non_functional_requirements": [{"category": "", "specifications": []}],
  "architecture": {"approach": "", "components": [], "integrations": []},
  "decisions_tradeoffs": [{"decision": "", "justification": "", "trade_off": ""}],
  "dependencies": [{"type": "", "title": "", "description": ""}],
  "risks": [{"risk": "", "probability": "", "impact": "", "mitigation": [], "contingency_plan": ""}],
  "acceptance_criteria": [],
  "testing_validation": {"test_types": [], "strategy": ""}
}
```

---

## 3. HLD (High Level Design Document)

Documento de visão arquitetural de alto nível que precede o código:
- Visão geral do sistema/módulo
- Componentes principais e suas responsabilidades
- Fluxos de dados de alto nível
- Decisões arquiteturais fundamentais
- Diagrama C1 (System Context) e C2 (Containers)

### Prompt para geração de HLD
O MBA ensina a usar Deep Research para coletar informações de mercado e tecnologia, adaptar ao formato HLD e gerar o documento com IA.

---

## 4. FDD (Feature Design Document)

Documento de design detalhado para features específicas:
- Detalhamento técnico da implementação
- Modelo de dados e schemas
- Contratos de API (request/response)
- Diagramas de sequência e componentes
- Edge cases e tratamento de erros
- Dependências técnicas específicas

### Prompt para geração de FDD
Workflow: Deep Research → Adaptação ao formato FDD → Geração com IA.

---

## 5. Diagramas C4

### Hierarquia C4:
| Nível | Nome | Mostra | Uso |
|---|---|---|---|
| C1 | System Context | Sistema + atores + sistemas externos | Stakeholders, produto |
| C2 | Containers | Aplicações, bancos, filas, serviços | Arquitetos, devs seniores |
| C3 | Component | Componentes internos de um container | Devs da feature |
| C4 | Code | Classes, funções, interfaces | Devs implementando |

### Geração com IA:
O MBA ensina a gerar diagramas C4 usando prompts que instruem a IA a produzir output em PlantUML ou Mermaid.

---

## 6. ADRs — Melhores Práticas do MBA

### Estrutura MADR (Markdown Any Decision Record):
- **Título**: ADR-NNN: Título conciso
- **Status**: Proposto | Aceito | Depreciado | Substituído por ADR-NNN
- **Contexto**: O que motivou a decisão
- **Decisão**: O que foi decidido
- **Consequências**: Positivas e negativas
- **Alternativas Consideradas**: Opções avaliadas com prós e contras

### Quando usar ADRs (do MBA):
- ✅ Mudança de banco de dados, framework ou linguagem
- ✅ Adoção de novo padrão arquitetural
- ✅ Decisão com trade-off significativo
- ❌ Mudanças triviais de estilo/formatação
- ❌ Decisões já cobertas por guidelines existentes

### Agente de Mapeamento de ADRs:
O MBA demonstra um agente que analisa o codebase e identifica potenciais ADRs que deveriam existir mas não foram documentados.

---

## 7. Engineering Guidelines

### Seções sugeridas:
1. **Project Stack** — Linguagens, frameworks, versões
2. **Coding Standards** — Formatação, naming conventions, documentação
3. **Testing Strategy** — Tipos de teste, cobertura mínima
4. **Git Workflow** — Branches, commits, PRs
5. **Pre-commit Hooks** — Linters, formatters, validações
6. **Deployment** — Pipeline CI/CD, environments
7. **Security** — Práticas de segurança obrigatórias
8. **Observability** — Logs, métricas, tracing

---

## 8. Aplicação no Second Brain KIOSK

### Templates a criar no vault:
- `vault/_templates/prd-feature-template.md` — Template PRD de Feature
- `vault/_templates/hld-template.md` — Template HLD
- `vault/_templates/fdd-template.md` — Template FDD
- `vault/_templates/engineering-guidelines-template.md` — Template Guidelines

### Prompt Registry:
- `vault/prompts/prd-interview-prompt.md` — Prompt de entrevista para PRD
- `vault/prompts/hld-generation-prompt.md` — Prompt para geração de HLD
- `vault/prompts/fdd-generation-prompt.md` — Prompt para geração de FDD
- `vault/prompts/adr-mapping-prompt.md` — Prompt para mapeamento de ADRs
- `vault/prompts/c4-diagram-prompt.md` — Prompt para diagramas C4
- `vault/prompts/guidelines-generation-prompt.md` — Prompt para guidelines

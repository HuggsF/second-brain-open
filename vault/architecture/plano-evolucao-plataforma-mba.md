# 🚀 Plano de Evolução Estrutural da Plataforma Second Brain

> **Origem:** MBA Full Cycle — Engenharia de Software com IA 2026  
> **Status:** `#status/active` | `#type/roadmap`  
> **Data:** 2026-10-12  
> **Objetivo:** Roteiro formal de evolução técnica em fases para transformar o Second Brain da KIOSK Brands em uma plataforma autônoma de engenharia de software de nível MBA.

---

## 1. Visão Estratégica & Diagnóstico de Maturidade

A análise de gaps contra a formação do MBA Full Cycle revelou uma infraestrutura de conhecimento rica (ADRs, System Design, Ingestão de PM3/Drive/System Design), porém com oportunidades de automação e orquestração de IA em 5 dimensões críticas.

```mermaid
timeline
    title Roadmap de Evolução Técnica: Plataforma Autônoma Second Brain
    section Fase 1: Fundação & Especificação (Concluída)
        Mapeamento MBA & Ingestão : Guias 01-04 criados
        ADR-013 & Gap Analysis : Chunks semânticos extraídos
        Templates PRD & HLD : Prompt Registry inicializado
    section Fase 2: Prompt Ops & Avaliação Contínua
        Pipeline de Eval Automatizado : Golden Datasets para 4 Times
        LLM-as-Judge & Guardrails : Integração com CI/CD
    section Fase 3: Autonomia Agêntica & MCP
        ReAct nos MCP Servers : Skills dedicadas por time
        PRPs para features complexas : Docker Compose unificado
    section Fase 4: Busca Híbrida & Alta Escala
        Migração pgvector : HyDE & Query Reformulation
        Dashboard Interativo com métricas : Observabilidade OpenTelemetry
```

---

## 2. Detalhamento das Fases

### 🟢 Fase 1: Fundação, Especificação & Base de Conhecimento (Status: ✅ Concluída)
- [x] **Ingestão e Manifest do MBA Full Cycle:** Varredura dos 8 módulos (321 vídeos, 22 PDFs, 7 ZIPs) e geração de `extracted_full_cycle/full_cycle_manifest.json`.
- [x] **Diagnóstico Formal de Gaps:** Publicação de `vault/architecture/full-cycle-gap-analysis.md` mapeando 14 gaps prioritários.
- [x] **Guias de Referência no Vault:**
  - `01-design-docs-com-ia.md` (PRDs, HLD, FDD, C4 e ADRs)
  - `02-desenvolvimento-aplicacoes-ia.md` (Pilares de Dev com IA, Context Engineering, PRPs)
  - `03-engenharia-prompts-e-context-windows.md` (Taxonomia de Prompts, ReAct, CoT, SoT, ToT)
  - `04-desafios-tecnicos-e-padroes-arquiteturais.md` (RAG, System Design, Integrações KIOSK)
- [x] **Decisão Arquitetural Formal:** Registro do [[ADR-013-adocao-padroes-mba-full-cycle-ia]].
- [x] **Chunks Semânticos dos 4 Times:** Extração de 20 chunks atômicos em `extracted_full_cycle/chunks_full_cycle.json` e incorporação nas 4 bases de inteligência (`inteligencia-time-dev.md`, `inteligencia-time-devops.md`, `inteligencia-time-qa.md`, `inteligencia-time-arquitetura.md`).
- [x] **Templates de Engenharia:** Publicação de `prd-feature-template.md`, `hld-template.md`, `engineering-guidelines.md` e `prompt-registry.yaml`.

---

### 🟡 Fase 2: Prompt Ops & Pipeline de Avaliação Contínua (Status: 📋 Próxima)
- **Objetivo:** Estabelecer controle estatístico e comportamental sobre as respostas dos agentes e prompts de geração de código.
- **Entregáveis:**
  1. **Golden Datasets Curados:** Criação de `evals/golden_datasets/` contendo casos de teste nominais e adversariais para DEV, DEVOPS, QA e ARQUITETURA.
  2. **Pipeline de Teste Automatizado:** Script `evals/evaluate_prompts.py` calculando métricas de Precision (alvo $\ge 0.85$), Recall (alvo $\ge 0.80$), F1-Score e Embedding Distance.
  3. **Quality Gates no Git:** Integração com pre-commit ou pipeline de testes local (`pytest evals/`), bloqueando prompts que regridam em relação ao baseline do `prompt-registry.yaml`.
  4. **Guardrails Anti-Alucinação:** Validação de comportamento gracioso sob falta de evidência e resistência a prompt injection.

---

### 🟠 Fase 3: Autonomia Agêntica com MCP Servers & PRPs (Status: 📋 Planejada)
- **Objetivo:** Transformar os 4 agentes em executores autônomos orientados a especificações técnicas.
- **Entregáveis:**
  1. **Implementação de ReAct nos Servidores MCP:** Habilitar raciocínio passo a passo antes de mutações de banco ou chamadas às APIs de Bling, Hub e ERP.
  2. **Workflows com PRPs (Product Requirement Prompts):** Empacotamento de PRDs + contexto da árvore de código + regras de validação para geração de features complexas em um único ciclo sem intervenção humana.
  3. **Docker Compose Unificado:** Atualização do `docker-compose.yml` para orquestrar serviços MCP, mock servers, redis e instâncias de avaliação com comando único.
  4. **Skills Especializadas:** Criação dos arquivos `.agents/skills/` dedicados para cada papel técnico.

---

### 🔵 Fase 4: Busca Semântica Avançada & Observabilidade Total (Status: 📋 Planejada)
- **Objetivo:** Maximizar o recall do conhecimento corporativo e a visibilidade de telemetria da plataforma.
- **Entregáveis:**
  1. **Motor RAG Híbrido:** Evolução da busca em JSON para PostgreSQL com extensão `pgvector`, combinando Full-Text Search (BM25) e Cosine Similarity.
  2. **Query Reformulation & HyDE:** Implementação de Hypothetical Document Embeddings no endpoint de busca para perguntas complexas ou com vocabulário informal.
  3. **Instrumentação OpenTelemetry:** Tracing distribuído de ponta a ponta em chamadas de agentes, identificando gargalos e custos de tokens em tempo real.
  4. **Dashboard de Governança Agêntica:** Visão unificada de saúde dos times, taxa de aprovação de PRDs, catálogo de prompts e grafo de conhecimento interativo.

---

## 3. Matriz de Responsabilidade por Time

| Time Especialista | Papel Principal na Evolução | Artefatos Chave Sob Tutela |
|---|---|---|
| **DEV** | Implementação de ReAct nos MCPs e adoção de SDD | `mcp_servers/`, `core/`, `tests/` |
| **DEVOPS** | Docker Compose unificado, SLOs de agentes e gates de deploy | `docker-compose.yml`, `observability/` |
| **QA** | Manutenção de Golden Datasets e bateria de testes anti-alucinação | `evals/`, `tests/eval_prompts/` |
| **ARQUITETURA** | Governança de PRDs/HLDs, aprovação de MADRs e Guidelines | `vault/adrs/`, `vault/architecture/`, `vault/_templates/` |

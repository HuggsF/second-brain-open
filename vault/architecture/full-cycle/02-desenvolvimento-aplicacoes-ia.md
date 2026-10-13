# 🤖 Desenvolvimento de Aplicações com IA — Padrões de Código e Agentes

> **Origem:** MBA Full Cycle — Módulo 08: Desenvolvimento de Aplicações com IA  
> **Complemento:** Módulo 03 (Lives) — Quick Wins, Agentes de IA, Docker Offload  
> **Aplicação:** KIOSK Brands Second Brain — 4 Agentes Especialistas  
> **Status:** `#status/active` | `#type/guide` | **Data:** 2026-10-12

---

## 1. Os 7 Pilares do Desenvolvimento com IA (M08)

O MBA Full Cycle define pilares fundamentais para desenvolvimento assistido por IA:

### Pilar 1: Documentação e Artefatos
- Todo projeto precisa de **documentos de contexto** que são ativos de longo prazo
- Tipos essenciais: README.md indexado, ADRs, PRDs, Guidelines, State.local.md
- **Regra de Ouro:** *"Cada novo chat é como um novo desenvolvedor contratado. Reflita sobre o que ele precisa ter em mãos."*

### Pilar 2: Ferramentas e Workflows
- **IDEs com IA:** Cursor, Windsurf, VSCode + Copilot, JetBrains
- **Agentes CLI:** Claude Code, Gemini CLI, OpenAI Codex CLI
- **Paralelização:** Executar múltiplos agentes em paralelo para tarefas independentes

### Pilar 3: Spec Driven Development (SDD)
- Escrever a especificação técnica ANTES do código
- A IA gera código a partir da spec, não o contrário
- Ciclo: Spec → Geração → Review → Testes → Iteração

### Pilar 4: Scripts de Inicialização e Arquivos de Agente
O que DEVE entrar no arquivo de inicialização do agente (CLAUDE.md, .cursor/rules):
- Descrição do projeto e stack
- Regras de código (formatação, naming, documentação)
- Referências a documentos de contexto
- Gotchas e policies específicas do projeto
- Links para ADRs e decisões técnicas

O que NÃO deve entrar:
- Código de implementação extenso
- Dados sensíveis (API keys, secrets)
- Informações que mudam frequentemente

### Pilar 5: Testabilidade
- Todo código gerado por IA deve ser testável
- Escrever testes ANTES ou JUNTO com o código
- A IA deve executar testes automaticamente após gerar código

### Pilar 6: Gotchas e Policies
- Documentar todos os gotchas (armadilhas conhecidas) do projeto
- Policies: regras que a IA NUNCA deve violar
- Exemplo: "Nunca usar `any` em TypeScript", "Sempre validar inputs"

### Pilar 7: Evolução e Otimização
- Otimizar arquivos de contexto existentes continuamente
- Progressive disclosure: revelar informação conforme necessidade
- Conditional details: detalhes que só aparecem quando relevantes

---

## 2. Project Skills — Sistema de Conhecimento Reutilizável (M08)

### O que são Skills
Skills são unidades modulares de conhecimento que estendem a capacidade dos agentes:
- Cada skill é um diretório com `SKILL.md` (instrução principal + frontmatter YAML)
- Podem incluir scripts, exemplos, recursos e referências
- Invocáveis como comandos pelo agente

### Anatomia de uma Skill
```
skills/
└── minha-skill/
    ├── SKILL.md           # Instrução principal (obrigatório)
    ├── scripts/           # Scripts auxiliares
    ├── examples/          # Exemplos de uso
    ├── resources/         # Templates, assets
    └── references/        # Documentação adicional
```

### Frontmatter da Skill
```yaml
---
name: nome-da-skill
description: Descrição curta do que a skill faz
---
```

### Técnicas Avançadas
- **Progressive Disclosure:** Revelar detalhes incrementalmente
- **Conditional Details:** Detalhes condicionados ao contexto
- **Agents.md vs Skills:** Skills são mais modulares e reutilizáveis

### Repositórios de Referência
- [Anthropic Official Skills](https://github.com/anthropics/skills/tree/main/skills)
- [Superpowers Skills](https://github.com/obra/superpowers/tree/main/skills)
- [AgentSkills Marketplace](https://agentskills.io/home)
- [Skills.sh](https://skills.sh/)

---

## 3. Context Engineering (M03-01)

### Definição
Construção de sistemas e workflows que fornecem as informações e ferramentas corretas no formato ideal para a LLM.

### Context Engineering vs Prompt Engineering
| Aspecto | Prompt Engineering | Context Engineering |
|---|---|---|
| Foco | Instruções textuais estáticas | Contextos dinâmicos integrados |
| Escopo | Um prompt | Todo o sistema de contexto |
| Inclui | Texto do prompt | Documentos, ferramentas, APIs, estados |

### Tipos de Documentos de Contexto
1. **Contexto Geral** — Descrição do projeto (produto + técnica)
2. **Stack** — Libs/frameworks com documentação (via Context7 + MCP)
3. **Guidelines** — Regras de formatação, documentação, testes
4. **README** — Informações de execução + índice de docs
5. **ADRs** — Decisões arquiteturais
6. **Plano de Ação** — Visão de alto nível do desenvolvimento
7. **Tarefa** — Itens detalhados com TODO list
8. **State.local.md** — Estado atual do desenvolvimento

### Context7 e MCP Server
```bash
# Adicionar Context7 como MCP Server
claude mcp add --transport http context7 https://mcp.context7.com/mcp

# Prompt para geração de docs de libs
Analise o codebase, identifique libs de terceiros,
use Context7 MCP para buscar documentação e salve em /docs/libs/
```

---

## 4. PRPs — Product Requirement Prompts (M03-01)

### O que é um PRP
> *"Uma PRP é um PRD + inteligência de base de código curada + agente/runbook — o pacote mínimo viável que uma IA precisa para gerar código pronto para produção já na primeira tentativa."*

### Estrutura de um PRP
1. **Purpose** — Objetivo claro da tarefa
2. **Core Principles** — SOLID, patterns, regras globais
3. **Goal** — Meta específica
4. **Why** — Justificativa
5. **What** — Escopo
6. **Success Criteria** — Checklist verificável
7. **All Needed Context:**
   - Documentation & References (URLs + arquivos)
   - Current Codebase Tree
   - Desired Codebase Tree
   - Known Gotchas
8. **Implementation Blueprint** — Modelos de dados + pseudocódigo
9. **Task List** — Tarefas ordenadas com YAML
10. **Validation Loop** — 3 níveis (Syntax, Unit Tests, Integration)
11. **Anti-Patterns** — O que NÃO fazer
12. **Confidence Score** — Autoavaliação

### Repositório de Referência
- [PRPs Agentic Engineering](https://github.com/Wirasm/PRPs-agentic-eng)

---

## 5. Docker Compose for Agents (M03-02)

### Conceito
Usar Docker Compose para criar ambientes de desenvolvimento com IA, simplificando a configuração de:
- Serviços de banco de dados
- Serviços de mensageria
- Servidores MCP
- Agentes de IA

### Referência
- [compose-for-agents](https://github.com/...) — Template Docker Compose para agentes

---

## 6. Subagentes e Orquestração (M03-04)

### Claude Subagents
- Divisão de trabalho em subagentes especializados
- Cada subagente recebe contexto específico da sua tarefa
- Orquestrador coordena resultados dos subagentes
- Referência: [claude-subagents](https://github.com/...) — Template de subagentes

---

## 7. Aplicação no Second Brain KIOSK

### Skills a criar para os 4 Agentes:
1. **Skill DEV:** Padrões de código KIOSK, workflow de feature dev, gotchas de integração
2. **Skill DEVOPS:** Pipeline CI/CD, Docker configs, infra como código
3. **Skill QA:** Templates de teste, cenários de carga, checklists de qualidade
4. **Skill ARQUITETURA:** Templates de design doc, ADR workflow, diagramas

### PRPs a criar:
- PRP para nova integração (Bling, SAP, Salesforce)
- PRP para nova feature do Hub
- PRP para refactoring de MCP server
- PRP para novo pipeline de dados

### Context Engineering no Second Brain:
- Criar `docs/libs/` com documentação das libs via Context7
- Atualizar README.md como índice completo
- Implementar State.local.md para tracking de estado

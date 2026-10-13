# 📏 Engineering Guidelines — Padrões Globais de Engenharia de Software

> **Status:** `#status/active` | `#type/guideline`  
> **Data:** 2026-10-12  
> **Origem:** MBA Full Cycle — Módulo 07 (Engineering Guidelines) & Módulo 08 (Dev com IA)  
> **Público:** Desenvolvedores e Agentes Especialistas (DEV, DEVOPS, QA, ARQUITETURA)

---

## 1. Princípios Fundamentais de Design
1. **Spec-Driven Development (SDD):** Toda implementação complexa deve derivar de um PRD ou FDD validado. Agentes de IA atuam a partir de especificações explícitas.
2. **Separação de Preocupações (Separation of Concerns):** Camadas de Domínio, Aplicação e Infraestrutura devem permanecer desacopladas. O núcleo de negócio não depende de frameworks web nem de ORMs específicos.
3. **Idempotência por Padrão:** Qualquer endpoint ou consumidor de fila que execute mutações de estado (criação de pedidos, emissão de nota, movimentação de estoque) deve exigir chave de idempotência (`Idempotency-Key`).
4. **Fail-Fast & Degradação Graciosa:** Validações de entrada falham imediatamente (HTTP 422). Falhas em integrações externas ativam Circuit Breakers e alternativas de fallback.

---

## 2. Padrões de Código (Python & TypeScript)
- **Tipagem Estrita:** Uso obrigatório de Type Hints em 100% das assinaturas públicas de funções e métodos. Uso de `Pydantic` v2 para validação e serialização de dados de entrada/saída.
- **Assincronismo:** Operações de I/O (rede, banco de dados, disco, chamadas LLM) devem ser assíncronas utilizando `async/await` com pools de conexão adequadamente dimensionados.
- **Tratamento de Exceções:**
  - Nunca capturar `Exception` de forma genérica sem relançar ou registrar estruturadamente.
  - Criar hierarquia de exceções de domínio (ex: `DomainException`, `EntityNotFoundException`, `IntegrationTimeoutException`).
  - Mapear exceções de domínio para códigos HTTP sem vazar traces internos para o cliente.

---

## 3. Diretrizes de Observabilidade e Logging
- **Logs Estruturados (JSON):**
  - Todo log deve conter: `timestamp`, `level`, `trace_id`, `span_id`, `service`, `event`, e payload sanitizado.
  - Proibido logar senhas, tokens de API, dados fiscais confidenciais ou PII sem mascaramento.
- **Four Golden Signals:**
  - Toda API deve expor métricas de latência P50/P95/P99, RPS, taxa de erros HTTP 5xx e saturação de workers.

---

## 4. Práticas de Testes Automatizados
- **Pirâmide de Testes:**
  - **Unitários:** Rápidos, sem I/O real, usando mocks leves para dependências externas. Cobertura alvo: $\ge 85\%$.
  - **Integração:** Validação de persistência no PostgreSQL/Redis e contratos de API usando `TestClient`.
  - **E2E / Carga:** Testes sintéticos de throughput e latência rodando contra ambientes de homologação.
- **Validação de Código Gerado por IA:**
  - Todo snippet gerado por agentes deve possuir testes associados que validem cenários nominais e de erro.
  - Nenhum commit de IA é aceito sem execução verde da suíte de testes.

---

## 5. Diretrizes para Agentes Autônomos de IA
- **Context Engineering:** Forneça sempre o contexto mínimo viável estruturado (README, PRD, Schemas, ADRs) ao instanciar tarefas complexas.
- **Padrão ReAct:** Agentes integrados com ferramentas externas devem expressar `Thought` antes de disparar `Action`.
- **Anti-Hallucination:** Caso o agente não encontre a informação no vault ou nas ferramentas, deve reportar ausência de evidência em vez de extrapolar ou inventar parâmetros.

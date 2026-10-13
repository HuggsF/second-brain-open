---
id: ADR-017
title: "DDD Phase 1 — Fonte de verdade única para roles Nexus e schema canônico de Playbooks"
status: active
date: 2026-10-13
authors: [Antigravity, Hugo Melo]
---

## Contexto

A análise DDD do projeto identificou cinco inconsistências críticas (IC-1 a IC-5) causando
falhas silenciosas em produção:

- **IC-1**: `DagGate.ALLOWED_ROLES` continha `architect`, `dev`, `qa`, `devops` — papéis que
  não existem no Orchestrator/Nexus. Os papéis reais (`manager`, `coder`) estavam ausentes,
  fazendo qualquer plano do Orchestrator ser rejeitado com RED pelo gate.

- **IC-2**: `PB-008` e `PB-009` foram criados no formato "Runbook de Incidente" sem os campos
  obrigatórios do schema canônico (`id`, `status`, `validates`, `environment`, `targets`).
  `PB-010` usava `environment: prod/hml` que não pertence ao enum `('hml', 'production', 'local')`.
  Os três eram silenciosamente ignorados por `load_definitions()`, sendo invisíveis para o
  motor de evidências e para o `lint()`. Dois testes de `test_evidence_seed.py` falhavam.

## Decisão

### 1. `core/domain/nexus/entities.py` — fonte de verdade única

Criado arquivo com `AGENT_ROLES`, `ROOMS`, `TOOL_REGISTRY`, `ALLOWED_ROLES`, `ALLOWED_TOOLS`,
`AGENT_STATUSES` e `HANDOFF_TYPES`. Todos os módulos que precisam dessas definições
(DagGate, Orchestrator, nexus/src/constants3d.js) devem derivar desse arquivo.

### 2. `core/gates/dag_gate.py` — deriva de `domain/nexus/entities.py`

Removidos os sets hardcoded `ALLOWED_ROLES` e `ALLOWED_TOOLS`. Substituídos por imports de
`core.domain.nexus.entities`. O gate agora aceita `manager`, `researcher`, `coder`, `writer`,
`reviewer` e rejeita papéis não definidos no domínio Nexus.

### 3. Frontmatters PB-008, PB-009, PB-010 migrados para schema canônico

- **PB-008**: adicionados `id: PB-008`, `status: active`, `validates: [RULE-001, RULE-002]`,
  `environment: production`, `targets: [Hub Logístico, Bling OAuth, J&T Adapter]`.
  Campos originais (`severity`, `trigger`, `tags`) preservados no frontmatter como metadados.
- **PB-009**: adicionados `id: PB-009`, `status: active`, `validates: [RULE-001, RULE-002]`,
  `environment: production`, `targets: [Hub Logístico, Srv-API, PM2, SQLite]`.
  Campo `origin` e `tags` preservados.
- **PB-010**: `environment: prod/hml` → `environment: hml` (valor válido do enum).

## Consequências

- `lint()` retorna `[]` para todos os 10 playbooks ativos.
- `load_definitions()` carrega todos os 10 playbooks sem erros.
- `test_evidence_seed.py` passa (os 2 testes que falhavam estão verdes).
- Qualquer plano de agente do Orchestrator com `manager` ou `coder` passa pelo `DagGate`.
- Adicionar um novo agente exige editar **apenas** `core/domain/nexus/entities.py`.
  O DagGate e o Orchestrator refletem a mudança automaticamente.

## Próximos passos (Fase 2)

- `core/domain/nexus/entities.py` → gerar `nexus/src/domain-spec.js` automaticamente
  (script de sincronização Python → JavaScript).
- `PlaybooksApi` em `dashboard/serve.py` → usar `load_definitions()` + `EvidenceStore.record()`
  em vez de parser local e SQL raw (IC-3).
- `core/domain/observation/` → entidades `ServiceHealth`, `ObservationSnapshot`, `Contradiction`
  e domain service `detect_contradictions()` (IC-4 parcial).

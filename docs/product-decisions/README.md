# Product Decisions (PD-OVR)

Catálogo de decisões soberanas de produto que **vencem** o texto das skills normativas.

## Formato

Cada decisão é um arquivo `PD-OVR-NNN-<slug>.md` com:

```yaml
---
id: PD-OVR-NNN
date: YYYY-MM-DD
status: APPROVED | SUPERSEDED
decision: Resumo em uma linha
context: Qual trade-off motivou a decisão
alternatives_considered: Opções avaliadas
rationale: Por que esta alternativa foi escolhida
---
```

## Índice

| ID | Decisão | Data | Status |
|----|---------|------|--------|
| PD-OVR-001 | F-IP-05 × F-BR-01 — Implementação independente | 2026-10-15 | APPROVED |
| PD-OVR-002 | Unicode normaliza apenas para injection scan | 2026-10-15 | APPROVED |
| PD-OVR-003 | Reset mission_start após HITL, TTL 30s fixo | 2026-10-15 | APPROVED |
| PD-OVR-004 | Fail-open (CB, RL) / Fail-closed (RBAC, FT, Autonomy, Input) | 2026-10-15 | APPROVED |
| PD-OVR-005 | Forbidden topics: base imutável + merge, payload nunca substitui | 2026-10-15 | APPROVED |
| PD-OVR-006 | Sem persona_id: gates globais sempre rodam; GAP-10 remediado | 2026-10-15 | APPROVED |

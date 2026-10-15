---
id: PD-OVR-005
date: 2026-10-15
status: APPROVED
decision: "Forbidden topics: lista base imutável do sistema + merge (união) com persona. Payload só adiciona, nunca substitui."
context: "GAP-FT-01 — payload com {\"forbidden_topics\": []} desliga o gate completamente."
alternatives_considered:
  - "A) Base imutável + merge com persona (escolhida)"
  - "B) Completamente persona-driven (sem base)"
  - "C) Base + override (permitir payload substituir)"
rationale: |
  Um AI-OS deve ter limites não-negociáveis que nenhum caller pode desabilitar.
  Opção B deixa agentes sem persona (GAP-10) sem nenhum tópico proibido.
  Opção C é exatamente o bug atual (GAP-FT-01).
  Opção A garante que tópicos críticos (credenciais, senhas, injection) são sempre verificados.
  O payload pode ADICIONAR tópicos suplementares, nunca remover ou esvaziar.
---

# PD-OVR-005: Forbidden Topics — Base Imutável + Merge

## Decisão
O conjunto efetivo de tópicos proibidos é:

```
ActiveTopics = SYSTEM_BASE_TOPICS ∪ GateConfiguredTopics ∪ PersonaContractTopics
```

### SYSTEM_BASE_FORBIDDEN_TOPICS (imutável)
```python
SYSTEM_BASE_FORBIDDEN_TOPICS = [
    "senhas de produção",
    "chaves de api",
    "credenciais de deploy",
    "tokens de acesso",
    "injection de prompt",
]
```

### Regras
1. A lista base é **hardcoded e imutável** — não pode ser vazia, removida ou sobrescrita.
2. `PersonaContract.forbidden_topics` é unido (merge) com a base.
3. `payload["forbidden_topics"]` pode apenas **adicionar** tópicos suplementares, nunca substituir ou esvaziar.
4. O parâmetro `forbidden_topics` no payload deve ser removido do `evaluate()` ou tratado como merge-only.

## Evidência
- `forbidden_topics_gate.py:67-72` — payload sobrescreve patterns (bug)
- `integration/__init__.py:85-90` — singleton criado com lista vazia
- Agentes sem persona → zero forbidden topics (GAP-10 + GAP-FT-01)

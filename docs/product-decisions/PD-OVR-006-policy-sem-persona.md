---
id: PD-OVR-006
date: 2026-10-15
status: APPROVED
decision: "Callers sem persona_id: executar gates globais (CB, RL, FT base, decide(), audit). Gates persona-específicos só com persona_id."
context: "GAP-12 — pipeline opt-in. persona_id=None desativa todo o pipeline de segurança."
alternatives_considered:
  - "A) Fail-closed reject (DENY sem persona_id)"
  - "B) Persona default com permissões mínimas"
  - "C) Executar gates globais sem persona-specific checks (escolhida)"
rationale: |
  Opção A quebra backward compatibility: ~25 testes em test_broker.py, callers externos,
  e agents sem mapping (researcher, coder, writer) seriam rejeitados imediatamente.
  Opção B requer definir permissões mínimas que podem conflitar com o TOOL_REGISTRY existente.
  Opção C preserva 100% de compatibilidade enquanto garante que nenhuma chamada
  passa sem inspeção de resiliência, forbidden topics base, e audit trail.
  Complementada por remediar GAP-10 mapeando researcher/coder/writer a personas.
---

# PD-OVR-006: Política para Callers sem persona_id

## Decisão
O pipeline NÃO deve ser completamente ignorado quando `persona_id is None`.

### Gates que SEMPRE executam (independente de persona_id)
1. **Circuit Breaker** — proteção contra cascade (por tool, não por persona)
2. **Rate Limiter** — proteção contra flood (por tool)
3. **Forbidden Topics (base)** — `SYSTEM_BASE_FORBIDDEN_TOPICS` (PD-OVR-005)
4. **Legacy `decide(identity, tool, args)`** — já enforça role allowlists via TOOL_REGISTRY
5. **WORM Audit Log** — toda chamada é auditada

### Gates que executam APENAS com persona_id
1. **RBAC (persona-specific)** — requer PersonaContract para determinar permissões extras
2. **Autonomy Evaluation** — requer autonomy_level e auto_approve_up_to_brl do contrato
3. **IO Contract Validation** — requer required_input_fields/output_fields do contrato

### Remediação de GAP-10
Mapear `researcher`, `coder` e `writer` a personas builtin no `AGENT_PERSONA_MAP`:
```python
AGENT_PERSONA_MAP = {
    "manager": "maia-orchestrator",
    "reviewer": "eva-supervisor",
    "researcher": "persona-researcher",  # NOVO — builtin com read-only + auto_execute
    "coder": "persona-devops",           # EXISTENTE — reuse
    "writer": "persona-writer",          # NOVO — builtin com content + auto_execute
}
```

## Evidência
- `broker.py:79` — `if persona_id:` é guard único do pipeline
- `orchestrator.py:41-45` — AGENT_PERSONA_MAP sem researcher/coder/writer
- `tests/test_broker.py` — ~25 testes sem persona_id que não podem quebrar
- `tests/test_integration.py:248-256` — teste explícito `test_call_without_persona_works_unchanged`

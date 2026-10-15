---
id: PD-OVR-004
date: 2026-10-15
status: APPROVED
decision: "Fail-open para gates de resiliência (CB, RL); fail-closed para gates de segurança (RBAC, FT, Autonomy, InputContract)"
context: "F-IP-01 — exceção em qualquer gate crasha o pipeline inteiro. Precisa de política formal por gate."
alternatives_considered:
  - "A) Fail-closed para TODOS os gates"
  - "B) Fail-open para TODOS os gates"
  - "C) Política diferenciada por tipo de gate (escolhida)"
rationale: |
  Gates de resiliência (CB, RL) protegem contra cascade/flood. False positive = outage sistêmico.
  False negative = tool é chamada sem proteção, mas falha normalmente se serviço estiver down.
  Gates de segurança (RBAC, FT, Autonomy, Input) protegem contra breach. False positive = task bloqueada.
  False negative = execução não autorizada, bypass de guardrails, perda financeira.
  Consequência de FN em security é catastrófica; em resilience é tolerável.
---

# PD-OVR-004: Fail-Open vs Fail-Closed por Gate

## Decisão
Cada gate do `pre_call_pipeline` deve ter isolamento individual (`try/except`) com política diferenciada:

| Gate | Tipo | Política | Justificativa |
|------|------|----------|---------------|
| Circuit Breaker | Resiliência | **Fail-Open** | FP = outage sistêmico. FN = tool tenta e falha normalmente |
| Rate Limiter | Tráfego | **Fail-Open** | FP = denial indevido. FN = requisição sem quota |
| RBAC | Segurança | **Fail-Closed** | FN = privilege escalation / RCE |
| Forbidden Topics | Conteúdo | **Fail-Closed** | FN = bypass de guardrail / injection |
| Autonomy | Governança | **Fail-Closed (ESCALATE)** | FN = ação financeira sem supervisão humana |
| Input Contract | Integridade | **Fail-Closed** | FN = tool com params corrompidos |

## Implementação
```python
# Resilience gates — fail-open
try:
    cb_result = check_circuit_breaker(tool_name)
except Exception:
    print("warn: CB check failed, allowing", file=sys.stderr)
    cb_result = PreCallResult(True, "cb_error_failopen")

# Security gates — fail-closed
try:
    rbac_result = check_rbac(persona_id, tool_name)
except Exception:
    rbac_result = PreCallResult(False, "rbac_internal_error")
```

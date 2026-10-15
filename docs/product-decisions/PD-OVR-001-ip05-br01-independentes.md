---
id: PD-OVR-001
date: 2026-10-15
status: APPROVED
decision: F-IP-05 e F-BR-01 são implementáveis de forma independente
context: Ambos os fixes alteram broker.py. Questão se há conflito no bloco finally.
alternatives_considered:
  - A) Implementar em sequência (F-IP-05 primeiro, depois F-BR-01)
  - B) Implementar de forma independente (em paralelo)
  - C) Refatorar broker.py primeiro, depois aplicar ambos
rationale: |
  F-IP-05 altera a **condição** de quando record_failure() é chamado no post_call_pipeline
  (não chamar quando pre_call bloqueou). F-BR-01 adiciona asyncio.wait_for() na chamada de
  tool em _execute(). Os dois operam em caminhos de código distintos:
  - F-IP-05: fluxo de pre_call blocked → finally → post_call_pipeline
  - F-BR-01: fluxo de _execute() → await IMPLEMENTATIONS[tool](**args)
  Não há conflito no finally — um altera a condição de entrada, o outro altera a execução.
---

# PD-OVR-001: F-IP-05 × F-BR-01 — Implementação Independente

## Decisão
Implementar F-IP-05 (RBAC deny não deve abrir Circuit Breaker) e F-BR-01 (timeout de tool via `asyncio.wait_for`) de forma independente. Não há conflito no bloco `finally` do `broker.py`.

## Contexto
Ambos os bugs requerem alterações no `broker.py`. F-IP-05 trata do fluxo de pré-chamada (quando `pre_call_pipeline` bloqueia, `post_call_pipeline` ainda executa e registra failure no CB). F-BR-01 trata do fluxo de execução (sem timeout na chamada de tool).

## Evidência
- `broker.py:79-94` — F-IP-05: `pre_call_pipeline` bloqueia → return na L94 → `finally` na L126 → `post_call_pipeline` com `success=False`
- `broker.py:56` — F-BR-01: `await IMPLEMENTATIONS[tool](**args)` sem `asyncio.wait_for()`
- Os dois caminhos são ortogonais: F-IP-05 altera quando `post_call_pipeline` é chamado, F-BR-01 altera como `_execute` é invocado.

---
id: PD-OVR-003
date: 2026-10-15
status: APPROVED
decision: Reset mission_start após HITL, manter TTL 30s fixo
context: TTL de 30s inclui tempo de aprovação HITL (até 300s), causando timeout imediato.
alternatives_considered:
  - A) Resetar mission_start após HITL retornar + TTL fixo 30s (escolhida)
  - B) TTL configurável por persona via PersonaContract
  - C) Pausar o timer durante HITL wait
rationale: |
  A opção A é o fix mínimo: resolve o bug sem alterar a API do PersonaContract.
  O TTL configurável (opção B) é uma feature nova que requer alterações no schema
  do contrato e pode introduzir novos bugs — fica adiada para P2.
  A opção C é complexa (requer timer com pause/resume) sem benefício adicional
  sobre resetar o timer.
---

# PD-OVR-003: TTL Reset — Fix Mínimo

## Decisão
Resetar `mission_start = time.time()` imediatamente **após** a aprovação HITL retornar (antes do loop de execução de steps). Manter o TTL de 30s sem alteração.

## Contexto
F-OR-05: `mission_start` é marcado no início da missão (L224), ANTES de `_wait_approval()` que pode levar até 300s. Se o operador leva >30s para aprovar, o TTL já expirou quando o primeiro step executa.

## Adiamentos
- F-OR-04 (TTL configurável por persona via PersonaContract) → adiado para P2.

## Evidência
- `orchestrator.py:224` — `mission_start = time.time()` no início
- `orchestrator.py:258` — `_wait_approval(timeout=300s)` pode bloquear por minutos
- `orchestrator.py:297` — `time.time() - mission_start > 30` → TTL check inclui espera

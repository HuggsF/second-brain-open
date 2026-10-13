"""Submódulo de Quality Gates Determinísticos do Compound AI System."""
from typing import Any, Dict, List

from core.gates.base import BaseGate, GateResult, Semaphore
from core.gates.grounding_gate import GroundingGate
from core.gates.dag_gate import DagGate
from core.gates.rule_gate import RuleComplianceGate
from core.gates.idempotency_gate import IdempotencyGate


class CompoundGatePipeline:
    """Executa a bateria de gates em sequência ou sob demanda."""

    def __init__(self):
        self.grounding = GroundingGate()
        self.dag = DagGate()
        self.rules = RuleComplianceGate()
        self.idempotency = IdempotencyGate()

    def run_all(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        results: List[GateResult] = []

        if "citations" in payload:
            results.append(self.grounding.evaluate(payload))
        if "plan" in payload or "steps" in payload:
            results.append(self.dag.evaluate(payload))
        if "rules_checked" in payload or "parameters" in payload:
            results.append(self.rules.evaluate(payload))
        if "is_mutation" in payload or "idempotency_key" in payload:
            results.append(self.idempotency.evaluate(payload))

        all_passed = all(r.passed for r in results) if results else True
        has_red = any(r.semaphore == Semaphore.RED for r in results)
        has_yellow = any(r.semaphore == Semaphore.YELLOW for r in results)

        global_semaphore = Semaphore.RED if has_red else (Semaphore.YELLOW if has_yellow else Semaphore.GREEN)

        return {
            "all_passed": all_passed,
            "global_semaphore": global_semaphore.value,
            "gate_results": [r.to_dict() for r in results],
        }


__all__ = [
    "BaseGate",
    "GateResult",
    "Semaphore",
    "GroundingGate",
    "DagGate",
    "RuleComplianceGate",
    "IdempotencyGate",
    "CompoundGatePipeline",
]

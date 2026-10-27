"""Testes unitários para a camada de Quality Gates do Compound AI System."""
import unittest
from core.gates import (
    GroundingGate,
    DagGate,
    RuleComplianceGate,
    IdempotencyGate,
    CompoundGatePipeline,
    Semaphore,
)


class TestQualityGates(unittest.TestCase):


    def test_grounding_gate_rejects_hallucinated_document(self):
        gate = GroundingGate()
        payload = {
            "citations": [
                {
                    "document": "adrs/ADR-999-documento-inexistente.md",
                    "sha256": "abcdef1234567890",
                }
            ]
        }
        result = gate.evaluate(payload)
        assert result.passed is False
        assert result.semaphore == Semaphore.RED


    def test_dag_gate_accepts_valid_dag(self):
        gate = DagGate()
        valid_plan = {
            "version": 1,
            "steps": [
                {"id": "step_1", "role": "researcher", "dependsOn": [], "tools": ["search_knowledge_base"], "budgetSeconds": 30},
                {"id": "step_2", "role": "reviewer", "dependsOn": ["step_1"], "tools": ["get_rule_evidence"], "budgetSeconds": 45},
                {"id": "step_3", "role": "coder", "dependsOn": ["step_2"], "tools": ["run_safe_command"], "budgetSeconds": 60},
            ],
        }
        result = gate.evaluate(valid_plan)
        assert result.passed is True
        assert result.semaphore == Semaphore.GREEN


    def test_dag_gate_rejects_cycle(self):
        gate = DagGate()
        cyclic_plan = {
            "version": 1,
            "steps": [
                {"id": "step_a", "role": "coder", "dependsOn": ["step_b"], "tools": ["run_safe_command"], "budgetSeconds": 30},
                {"id": "step_b", "role": "reviewer", "dependsOn": ["step_a"], "tools": ["get_rule_evidence"], "budgetSeconds": 30},
            ],
        }
        result = gate.evaluate(cyclic_plan)
        assert result.passed is False
        assert result.semaphore == Semaphore.RED
        assert "Ciclo de dependência" in result.details["errors"][0]


    def test_idempotency_gate_enforces_key_and_trace(self):
        gate = IdempotencyGate()
        # Mutação sem chave de idempotência deve falhar
        bad_payload = {
            "is_mutation": True,
            "operation": "POST /api/v1/shipments/issue",
        }
        result = gate.evaluate(bad_payload)
        assert result.passed is False
        assert result.semaphore == Semaphore.RED

        # Mutação com chave válida e trace_id deve passar
        good_payload = {
            "is_mutation": True,
            "operation": "POST /api/v1/shipments/issue",
            "idempotency_key": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "batch_trace_id": "e74f9d2a1b8c0e5a4f7e2d1c9a8b7e6d",
            "lock_ttl_seconds": 15,
        }
        result_good = gate.evaluate(good_payload)
        assert result_good.passed is True
        assert result_good.semaphore == Semaphore.GREEN




if __name__ == "__main__":
    unittest.main()

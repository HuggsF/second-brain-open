"""Testes unitários para a camada de Quality Gates do Compound AI System."""
import pytest
from core.gates import (
    GroundingGate,
    DagGate,
    RuleComplianceGate,
    IdempotencyGate,
    CompoundGatePipeline,
    Semaphore,
)


def test_grounding_gate_with_real_adr():
    gate = GroundingGate()
    # ADR-006 existe e tem hash conhecido
    payload = {
        "citations": [
            {
                "document": "adrs/ADR-006-implementacao-flowlogger-observabilidade-semaforos.md",
                "sha256": "086f70082f1cf5bf64f0634b83ccee8be539fed32bf24082faaeb2fcf5345c31",
            }
        ]
    }
    result = gate.evaluate(payload)
    assert result.passed is True
    assert result.semaphore == Semaphore.GREEN


def test_grounding_gate_rejects_hallucinated_document():
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


def test_dag_gate_accepts_valid_dag():
    gate = DagGate()
    valid_plan = {
        "version": 1,
        "steps": [
            {"id": "step_1", "role": "researcher", "dependsOn": [], "tools": ["search"], "budgetSeconds": 30},
            {"id": "step_2", "role": "architect", "dependsOn": ["step_1"], "tools": ["validate_plan"], "budgetSeconds": 45},
            {"id": "step_3", "role": "dev", "dependsOn": ["step_2"], "tools": ["generate_patch"], "budgetSeconds": 60},
        ],
    }
    result = gate.evaluate(valid_plan)
    assert result.passed is True
    assert result.semaphore == Semaphore.GREEN


def test_dag_gate_rejects_cycle():
    gate = DagGate()
    cyclic_plan = {
        "version": 1,
        "steps": [
            {"id": "step_a", "role": "dev", "dependsOn": ["step_b"], "tools": ["generate_patch"], "budgetSeconds": 30},
            {"id": "step_b", "role": "qa", "dependsOn": ["step_a"], "tools": ["run_concurrency_test"], "budgetSeconds": 30},
        ],
    }
    result = gate.evaluate(cyclic_plan)
    assert result.passed is False
    assert result.semaphore == Semaphore.RED
    assert "Ciclo de dependência" in result.details["errors"][0]


def test_idempotency_gate_enforces_key_and_trace():
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


def test_pipeline_runner():
    pipeline = CompoundGatePipeline()
    payload = {
        "citations": [
            {"document": "adrs/ADR-006-implementacao-flowlogger-observabilidade-semaforos.md"}
        ],
        "is_mutation": True,
        "idempotency_key": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
        "batch_trace_id": "e74f9d2a1b8c0e5a4f7e2d1c9a8b7e6d",
        "lock_ttl_seconds": 15,
    }
    result = pipeline.run_all(payload)
    assert result["all_passed"] is True
    assert result["global_semaphore"] == "GREEN"

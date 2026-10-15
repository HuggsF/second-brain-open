"""Tests for GAP-13: Persona ID attestation (INV-N14)."""
import pytest
from core.schema.persona_contract import get_builtin_contract, list_builtin_personas
from core.broker import _validate_persona


def test_validate_known_persona():
    contract = _validate_persona("maia-orchestrator")
    assert contract is not None


def test_validate_unknown_raises():
    with pytest.raises(ValueError, match="Unknown persona"):
        _validate_persona("attacker-fake")


def test_researcher_builtin_exists():
    contract = get_builtin_contract("persona-researcher")
    assert contract is not None
    assert contract.role == "specialist"


def test_writer_builtin_exists():
    contract = get_builtin_contract("persona-writer")
    assert contract is not None
    assert contract.role == "specialist"


def test_list_includes_new_personas():
    personas = list_builtin_personas()
    assert "persona-researcher" in personas
    assert "persona-writer" in personas

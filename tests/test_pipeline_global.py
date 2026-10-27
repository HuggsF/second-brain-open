# Em tests/test_pipeline_global.py (novo)
import pytest
from unittest import mock
from core.integration import pre_call_pipeline, PreCallResult
from backend.orchestrator import AGENT_PERSONA_MAP


def test_pipeline_runs_without_persona():
    """CB + RL + FT devem rodar mesmo sem persona_id."""
    result = pre_call_pipeline(None, "some_tool", {}, "texto normal")
    assert result.allowed is True  # gates globais passam


def test_pipeline_blocks_forbidden_topic_without_persona():
    """FT deve bloquear mesmo sem persona_id."""
    result = pre_call_pipeline(None, "some_tool", {}, "chaves de api expostas")
    assert result.allowed is False


def test_agent_persona_map_complete():
    """Todos os 5 agentes devem ter persona mapeada."""
    expected = {"manager", "reviewer", "researcher", "coder", "writer"}
    assert set(AGENT_PERSONA_MAP.keys()) == expected


def test_agent_persona_map_values():
    assert AGENT_PERSONA_MAP["researcher"] == "persona-researcher"
    assert AGENT_PERSONA_MAP["coder"] == "persona-devops"
    assert AGENT_PERSONA_MAP["writer"] == "persona-writer"

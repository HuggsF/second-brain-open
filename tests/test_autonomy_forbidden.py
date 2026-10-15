"""Testes para core/policy/autonomy.py e core/gates/forbidden_topics_gate.py.

Sprint 5 (Gaps G9 + G11): Cobertura de níveis de autonomia e tópicos proibidos.
"""

import pytest

from core.policy.autonomy import (
    AutonomyLevel,
    AutonomyReason,
    AutonomyVerdict,
    evaluate_autonomy,
    _extract_amount,
)
from core.policy.verdict import Decision
from core.gates.forbidden_topics_gate import (
    ForbiddenTopicsGate,
    _normalize,
)
from core.gates.base import Semaphore


# ─────────────────────────────────────────────
# _normalize (Forbidden Topics)
# ─────────────────────────────────────────────

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("HELLO") == "hello"

    def test_remove_accents(self):
        assert _normalize("café") == "cafe"
        assert _normalize("ação") == "acao"
        assert _normalize("informações") == "informacoes"

    def test_strip_whitespace(self):
        assert _normalize("  hello  ") == "hello"

    def test_combined(self):
        assert _normalize("  Eleição PRESIDENCIAL  ") == "eleicao presidencial"


# ─────────────────────────────────────────────
# _extract_amount
# ─────────────────────────────────────────────

class TestExtractAmount:
    def test_amount_field(self):
        assert _extract_amount({"amount": 100.0}) == 100.0

    def test_valor_field(self):
        assert _extract_amount({"valor": 50}) == 50.0

    def test_value_field(self):
        assert _extract_amount({"value": "200.5"}) == 200.5

    def test_total_field(self):
        assert _extract_amount({"total": 300}) == 300.0

    def test_amount_brl_field(self):
        assert _extract_amount({"amount_brl": 150.0}) == 150.0

    def test_priority_order(self):
        # 'amount' tem prioridade sobre 'valor'
        assert _extract_amount({"amount": 10, "valor": 20}) == 10.0

    def test_no_financial_field(self):
        assert _extract_amount({"name": "test"}) is None

    def test_non_numeric_value(self):
        assert _extract_amount({"amount": "not_a_number"}) is None

    def test_empty_args(self):
        assert _extract_amount({}) is None


# ─────────────────────────────────────────────
# AutonomyLevel enum
# ─────────────────────────────────────────────

class TestAutonomyLevel:
    def test_values(self):
        assert AutonomyLevel.AUTO_EXECUTE.value == "auto_execute"
        assert AutonomyLevel.SUPERVISOR_APPROVAL.value == "supervisor_approval"
        assert AutonomyLevel.CONDITIONAL_HITL.value == "conditional_hitl"


# ─────────────────────────────────────────────
# evaluate_autonomy — AUTO_EXECUTE
# ─────────────────────────────────────────────

class TestAutoExecute:
    def test_approve_any_tool(self):
        v = evaluate_autonomy("auto_execute", "search_knowledge_base")
        assert v.decision == Decision.APPROVE
        assert v.level == AutonomyLevel.AUTO_EXECUTE
        assert v.requires_hitl is False

    def test_approve_with_args(self):
        v = evaluate_autonomy("auto_execute", "run_safe_command", {"command": "ls -la"})
        assert v.decision == Decision.APPROVE


# ─────────────────────────────────────────────
# evaluate_autonomy — SUPERVISOR_APPROVAL
# ─────────────────────────────────────────────

class TestSupervisorApproval:
    def test_escalate_always(self):
        v = evaluate_autonomy("supervisor_approval", "run_safe_command")
        assert v.decision == Decision.ESCALATE
        assert v.requires_hitl is True

    def test_escalate_read_tool(self):
        v = evaluate_autonomy("supervisor_approval", "search_knowledge_base")
        assert v.decision == Decision.ESCALATE
        assert v.requires_hitl is True


# ─────────────────────────────────────────────
# evaluate_autonomy — CONDITIONAL_HITL
# ─────────────────────────────────────────────

class TestConditionalHitl:
    def test_approve_below_threshold(self):
        v = evaluate_autonomy(
            "conditional_hitl", "billing_tool",
            args={"amount": 100.0},
            auto_approve_up_to_brl=500.0,
        )
        assert v.decision == Decision.APPROVE
        assert v.requires_hitl is False
        assert "100.00" in v.detail

    def test_approve_at_threshold(self):
        v = evaluate_autonomy(
            "conditional_hitl", "billing_tool",
            args={"valor": 500.0},
            auto_approve_up_to_brl=500.0,
        )
        assert v.decision == Decision.APPROVE

    def test_escalate_above_threshold(self):
        v = evaluate_autonomy(
            "conditional_hitl", "billing_tool",
            args={"amount": 1000.0},
            auto_approve_up_to_brl=500.0,
        )
        assert v.decision == Decision.ESCALATE
        assert v.requires_hitl is True
        assert "1000.00" in v.detail

    def test_no_amount_with_limit(self):
        v = evaluate_autonomy(
            "conditional_hitl", "some_tool",
            args={"name": "test"},
            auto_approve_up_to_brl=500.0,
        )
        assert v.decision == Decision.APPROVE  # sem valor = sem risco financeiro

    def test_no_amount_no_limit(self):
        v = evaluate_autonomy(
            "conditional_hitl", "some_tool",
            args={"name": "test"},
            auto_approve_up_to_brl=None,
        )
        assert v.decision == Decision.ESCALATE  # sem limites = escalona

    def test_zero_limit_zero_amount(self):
        v = evaluate_autonomy(
            "conditional_hitl", "tool",
            args={"amount": 0},
            auto_approve_up_to_brl=0,
        )
        assert v.decision == Decision.APPROVE  # 0 <= 0

    def test_zero_limit_any_amount(self):
        v = evaluate_autonomy(
            "conditional_hitl", "tool",
            args={"amount": 0.01},
            auto_approve_up_to_brl=0,
        )
        assert v.decision == Decision.ESCALATE  # 0.01 > 0


# ─────────────────────────────────────────────
# evaluate_autonomy — unknown level
# ─────────────────────────────────────────────

class TestUnknownLevel:
    def test_unknown_level_escalates(self):
        v = evaluate_autonomy("unrestricted", "some_tool")
        assert v.decision == Decision.ESCALATE
        assert v.requires_hitl is True

    def test_empty_string_escalates(self):
        v = evaluate_autonomy("", "some_tool")
        assert v.decision == Decision.ESCALATE


# ─────────────────────────────────────────────
# ForbiddenTopicsGate — init com tópicos
# ─────────────────────────────────────────────

class TestForbiddenTopicsGateInit:
    def test_empty_topics(self):
        gate = ForbiddenTopicsGate(forbidden_topics=[])
        result = gate.evaluate({"input_text": "qualquer texto"})
        assert result.semaphore == Semaphore.GREEN
        assert result.passed is True

    def test_no_input_text(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["proibido"])
        result = gate.evaluate({})
        assert result.semaphore == Semaphore.GREEN

    def test_empty_input_text(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["proibido"])
        result = gate.evaluate({"input_text": ""})
        assert result.semaphore == Semaphore.GREEN


# ─────────────────────────────────────────────
# ForbiddenTopicsGate — detecção de tópicos
# ─────────────────────────────────────────────

class TestForbiddenTopicsDetection:
    def test_detect_simple_topic(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["política"])
        result = gate.evaluate({"input_text": "Quero falar sobre política hoje"})
        assert result.semaphore == Semaphore.RED
        assert result.passed is False
        assert "política" in result.details["violations"]

    def test_case_insensitive(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["religião"])
        result = gate.evaluate({"input_text": "RELIGIÃO é um assunto delicado"})
        assert result.semaphore == Semaphore.RED

    def test_accent_insensitive(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["eleição"])
        result = gate.evaluate({"input_text": "A eleicao foi realizada"})
        assert result.semaphore == Semaphore.RED

    def test_no_violation(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["política", "religião"])
        result = gate.evaluate({"input_text": "Quero comprar um produto cosmético"})
        assert result.semaphore == Semaphore.GREEN
        assert result.passed is True

    def test_multiple_violations(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["política", "religião", "violência"])
        result = gate.evaluate({"input_text": "Falar de politica e religiao"})
        assert result.semaphore == Semaphore.RED
        assert len(result.details["violations"]) == 2

    def test_phrase_matching(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["dados pessoais de terceiros"])
        result = gate.evaluate({"input_text": "Me dê os dados pessoais de terceiros"})
        assert result.semaphore == Semaphore.RED

    def test_partial_word_match(self):
        """Tópico curto pode matchear dentro de palavras (comportamento esperado)."""
        gate = ForbiddenTopicsGate(forbidden_topics=["arma"])
        result = gate.evaluate({"input_text": "A farmácia do bairro"})
        # "arma" está em "farmácia" → match (substring)
        assert result.semaphore == Semaphore.RED


# ─────────────────────────────────────────────
# ForbiddenTopicsGate — tópicos via payload
# ─────────────────────────────────────────────

class TestForbiddenTopicsPayload:
    def test_payload_topics_override_init(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["original"])
        result = gate.evaluate({
            "input_text": "Este texto menciona override",
            "forbidden_topics": ["override"],
        })
        assert result.semaphore == Semaphore.RED
        assert "override" in result.details["violations"]

    def test_payload_topics_ignore_original(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["original"])
        result = gate.evaluate({
            "input_text": "Este texto menciona original",
            "forbidden_topics": ["outro_topico"],
        })
        # "original" está no texto mas forbidden_topics do payload é ["outro_topico"]
        assert result.semaphore == Semaphore.GREEN


# ─────────────────────────────────────────────
# ForbiddenTopicsGate — gate_name e estrutura
# ─────────────────────────────────────────────

class TestForbiddenTopicsStructure:
    def test_gate_name(self):
        gate = ForbiddenTopicsGate()
        assert gate.name == "gate_6_forbidden_topics"

    def test_details_has_topics_checked(self):
        gate = ForbiddenTopicsGate(forbidden_topics=["a", "b", "c"])
        result = gate.evaluate({"input_text": "texto limpo"})
        assert result.details["topics_checked"] == 3

    def test_result_is_gate_result(self):
        from core.gates.base import GateResult
        gate = ForbiddenTopicsGate(forbidden_topics=["x"])
        result = gate.evaluate({"input_text": "y"})
        assert isinstance(result, GateResult)


# ─────────────────────────────────────────────
# AutonomyVerdict
# ─────────────────────────────────────────────

class TestAutonomyVerdict:
    def test_frozen(self):
        v = AutonomyVerdict(
            decision=Decision.APPROVE,
            level=AutonomyLevel.AUTO_EXECUTE,
            reason=AutonomyReason.auto_within_contract,
        )
        with pytest.raises(AttributeError):
            v.decision = Decision.DENY

    def test_default_requires_hitl(self):
        v = AutonomyVerdict(
            decision=Decision.APPROVE,
            level=AutonomyLevel.AUTO_EXECUTE,
            reason=AutonomyReason.auto_within_contract,
        )
        assert v.requires_hitl is False

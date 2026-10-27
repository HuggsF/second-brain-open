"""Testes para hardening de autonomia (F-AU-01, F-AU-02, GAP-03)."""

from core.policy.autonomy import _extract_amount, _parse_brl, UNPARSEABLE, evaluate_autonomy


def test_parse_brl_standard():
    assert _parse_brl("R$ 50.000,00") == 50000.0


def test_parse_brl_invalid():
    assert _parse_brl("not_a_number") is None


def test_extract_amount_unparseable_string():
    assert _extract_amount({"amount": "not_a_number"}) is UNPARSEABLE


def test_extract_amount_negative():
    assert _extract_amount({"amount": -1000}) is UNPARSEABLE


def test_extract_amount_shadowing():
    assert _extract_amount({"amount": 0, "valor": 90000}) is UNPARSEABLE


def test_extract_amount_empty():
    assert _extract_amount({}) is None


def test_extract_amount_valid_brl():
    assert _extract_amount({"amount": "R$ 50.000,00"}) == 50000.0


def test_evaluate_unparseable_escalates():
    v = evaluate_autonomy("conditional_hitl", "transfer", {"amount": "bad"}, 500)
    assert v.decision.value == "ESCALATE"
    assert v.requires_hitl is True


def test_evaluate_negative_escalates():
    v = evaluate_autonomy("conditional_hitl", "transfer", {"amount": -1000}, 500)
    assert v.decision.value == "ESCALATE"

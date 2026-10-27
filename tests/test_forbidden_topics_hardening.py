"""Testes TDD para ForbiddenTopicsGate hardening: word boundary regex e base imutável."""

from core.gates.forbidden_topics_gate import ForbiddenTopicsGate, SYSTEM_BASE_FORBIDDEN_TOPICS


def test_word_boundary_no_false_positive():
    gate = ForbiddenTopicsGate(["pix"])
    result = gate.evaluate({"input_text": "pixel art é incrível"})
    assert result.passed is True  # "pix" NÃO casa com "pixel"


def test_word_boundary_true_positive():
    gate = ForbiddenTopicsGate(["pix"])
    result = gate.evaluate({"input_text": "usar pix para pagar"})
    assert result.passed is False


def test_base_topics_always_active():
    gate = ForbiddenTopicsGate([])
    result = gate.evaluate({"input_text": "aqui estão as chaves de api"})
    assert result.passed is False


def test_payload_cannot_replace_base():
    gate = ForbiddenTopicsGate(["pix"])
    result = gate.evaluate({
        "forbidden_topics": [],  # tenta esvaziar
        "input_text": "chaves de api expostas",
    })
    assert result.passed is False  # INV-N04: base imutável


def test_payload_can_supplement():
    gate = ForbiddenTopicsGate([])
    result = gate.evaluate({
        "forbidden_topics": ["segredo"],
        "input_text": "isso é um segredo",
    })
    assert result.passed is False


def test_multi_word_boundary():
    gate = ForbiddenTopicsGate([])
    result = gate.evaluate({"input_text": "aqui estão as senhas de produção do servidor"})
    assert result.passed is False

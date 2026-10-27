"""Testes de regressão para findings bloqueantes F-03 e F-04 da Fase 5 Review."""
import unittest


class TestF03WhitespaceBypass(unittest.TestCase):
    """F-03: Forbidden topics multi-word NÃO devem ser bypassáveis com whitespace extra."""

    def test_double_space_bypass_blocked(self):
        from core.gates.forbidden_topics_gate import ForbiddenTopicsGate
        gate = ForbiddenTopicsGate([])
        result = gate.evaluate({"input_text": "aqui estão as senhas  de  produção"})
        self.assertFalse(result.passed, "Double space should NOT bypass forbidden topic")

    def test_tab_bypass_blocked(self):
        from core.gates.forbidden_topics_gate import ForbiddenTopicsGate
        gate = ForbiddenTopicsGate([])
        result = gate.evaluate({"input_text": "aqui estão as senhas\tde\tprodução"})
        self.assertFalse(result.passed, "Tab characters should NOT bypass forbidden topic")

    def test_newline_bypass_blocked(self):
        from core.gates.forbidden_topics_gate import ForbiddenTopicsGate
        gate = ForbiddenTopicsGate([])
        result = gate.evaluate({"input_text": "aqui estão as senhas\nde\nprodução"})
        self.assertFalse(result.passed, "Newline characters should NOT bypass forbidden topic")

    def test_normal_match_still_works(self):
        from core.gates.forbidden_topics_gate import ForbiddenTopicsGate
        gate = ForbiddenTopicsGate([])
        result = gate.evaluate({"input_text": "aqui estão as senhas de produção"})
        self.assertFalse(result.passed, "Normal spacing should still match")

    def test_word_boundary_still_prevents_false_positive(self):
        from core.gates.forbidden_topics_gate import ForbiddenTopicsGate
        gate = ForbiddenTopicsGate(["pix"])
        result = gate.evaluate({"input_text": "pixel art é interessante"})
        self.assertTrue(result.passed, "Word boundary should prevent false positive on 'pixel'")


class TestF04ListPiiRedaction(unittest.TestCase):
    """F-04: _redact_dict_values() DEVE processar listas recursivamente."""

    def test_list_of_strings_with_pii_is_redacted(self):
        from core.integration import _redact_dict_values
        result = {"items": ["CPF: 123.456.789-00", "sem pii aqui"], "status": "ok"}
        redacted = _redact_dict_values(result)
        # CPF deve estar mascarado
        self.assertNotIn("123.456.789-00", str(redacted["items"]))
        # Campo sem PII deve permanecer
        self.assertEqual(redacted["items"][1], "sem pii aqui")
        self.assertEqual(redacted["status"], "ok")

    def test_nested_list_of_dicts_with_pii(self):
        from core.integration import _redact_dict_values
        result = {"records": [{"cpf": "123.456.789-00", "name": "test"}]}
        redacted = _redact_dict_values(result)
        self.assertNotIn("123.456.789-00", str(redacted["records"]))
        self.assertEqual(redacted["records"][0]["name"], "test")

    def test_dict_without_lists_still_works(self):
        from core.integration import _redact_dict_values
        result = {"cpf": "123.456.789-00", "status": "ok"}
        redacted = _redact_dict_values(result)
        self.assertNotIn("123.456.789-00", str(redacted["cpf"]))
        self.assertEqual(redacted["status"], "ok")

    def test_empty_list_is_preserved(self):
        from core.integration import _redact_dict_values
        result = {"items": [], "status": "ok"}
        redacted = _redact_dict_values(result)
        self.assertEqual(redacted["items"], [])

    def test_numeric_values_in_list_preserved(self):
        from core.integration import _redact_dict_values
        result = {"counts": [1, 2, 3], "status": "ok"}
        redacted = _redact_dict_values(result)
        self.assertEqual(redacted["counts"], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()

"""Testes para o Sprint 9 — R7: Input/Output Contract Validation per Persona.

Cobre:
- Dataclass IOContractConfig e seus valores padrão
- Integração de io_contract no PersonaContract
- Roundtrip de to_dict() e from_dict() com io_contract
- Presença e configuração de io_contract em todos os 5 BUILTIN_CONTRACTS
- Função validate_input_contract() (bloqueio por campos faltantes, sucesso, ausência de contrato)
- Função validate_output_contract() (detecção de campos faltantes, strict vs non-strict, sucesso)
- Integração no post_call_pipeline() com soft enforcement (aviso em stderr se strict=True)
- Integração no pre_call_pipeline() com validação de input
- Backward compatibility (dicionários sem io_contract utilizam defaults seguros)
"""

import io
import sys
import unittest
from typing import Any, Dict

from core.schema.persona_contract import (
    PersonaContract,
    IOContractConfig,
    QualityGatesConfig,
    SecurityPolicies,
    MoERoutingConfig,
    ResilienceConfig,
    AuditConfig,
    BUILTIN_CONTRACTS,
    get_builtin_contract,
    list_builtin_personas,
)
from core.integration import (
    validate_input_contract,
    validate_output_contract,
    pre_call_pipeline,
    post_call_pipeline,
    reset_all_singletons,
)


class TestIOContractConfig(unittest.TestCase):
    """Testes unitários para a dataclass IOContractConfig."""

    def test_ioconfig_creation_and_defaults(self):
        """IOContractConfig sem argumentos deve possuir defaults seguros."""
        cfg = IOContractConfig()
        self.assertEqual(cfg.required_input_fields, [])
        self.assertFalse(cfg.output_schema_strict)
        self.assertEqual(cfg.required_output_fields, [])
        self.assertEqual(cfg.validate(), [])

    def test_ioconfig_custom_values(self):
        """IOContractConfig aceita parâmetros customizados e valida sem erros."""
        cfg = IOContractConfig(
            required_input_fields=["query", "session_id"],
            output_schema_strict=True,
            required_output_fields=["result", "confidence"],
        )
        self.assertEqual(cfg.required_input_fields, ["query", "session_id"])
        self.assertTrue(cfg.output_schema_strict)
        self.assertEqual(cfg.required_output_fields, ["result", "confidence"])
        self.assertEqual(cfg.validate(), [])


class TestPersonaContractIOContract(unittest.TestCase):
    """Testes de schema e serialização do io_contract no PersonaContract."""

    def test_persona_contract_with_io_contract_validates(self):
        """PersonaContract configurado com io_contract deve passar na validação."""
        contract = PersonaContract(
            persona_id="test-io",
            display_name="Test IO Persona",
            role="specialist",
            io_contract=IOContractConfig(
                required_input_fields=["param1"],
                output_schema_strict=True,
                required_output_fields=["output1"],
            ),
        )
        errors = contract.validate()
        self.assertEqual(errors, [])
        self.assertTrue(contract.io_contract.output_schema_strict)
        self.assertEqual(contract.io_contract.required_input_fields, ["param1"])
        self.assertEqual(contract.io_contract.required_output_fields, ["output1"])

    def test_to_dict_from_dict_roundtrip_with_io_contract(self):
        """to_dict() e from_dict() devem serializar e desserializar io_contract com fidelidade."""
        original = PersonaContract(
            persona_id="roundtrip-io",
            display_name="Roundtrip IO Persona",
            role="executor",
            io_contract=IOContractConfig(
                required_input_fields=["command", "timeout"],
                output_schema_strict=True,
                required_output_fields=["status", "stdout"],
            ),
        )
        d = original.to_dict()
        self.assertIn("io_contract", d)
        self.assertEqual(d["io_contract"]["required_input_fields"], ["command", "timeout"])
        self.assertTrue(d["io_contract"]["output_schema_strict"])
        self.assertEqual(d["io_contract"]["required_output_fields"], ["status", "stdout"])

        restored = PersonaContract.from_dict(d)
        self.assertEqual(restored.persona_id, "roundtrip-io")
        self.assertEqual(restored.io_contract.required_input_fields, ["command", "timeout"])
        self.assertTrue(restored.io_contract.output_schema_strict)
        self.assertEqual(restored.io_contract.required_output_fields, ["status", "stdout"])
        self.assertEqual(restored.validate(), [])

    def test_backward_compatibility_no_io_contract_in_dict(self):
        """Dicionários antigos sem a chave io_contract devem usar defaults seguros."""
        data = {
            "persona_id": "legacy-persona",
            "display_name": "Legacy Persona",
            "role": "specialist",
        }
        contract = PersonaContract.from_dict(data)
        self.assertIsInstance(contract.io_contract, IOContractConfig)
        self.assertEqual(contract.io_contract.required_input_fields, [])
        self.assertFalse(contract.io_contract.output_schema_strict)
        self.assertEqual(contract.io_contract.required_output_fields, [])
        self.assertEqual(contract.validate(), [])


class TestBuiltinIOContracts(unittest.TestCase):
    """Testa a presença e configuração correta de io_contract em todos os 5 BUILTIN_CONTRACTS."""

    def test_all_seven_builtin_contracts_have_io_contract(self):
        """Todos os 7 contratos built-in devem conter io_contract no dicionário e validar."""
        expected_personas = [
            "maia-orchestrator",
            "eva-supervisor",
            "persona-devops",
            "persona-finops",
            "cx-triage",
            "persona-researcher",
            "persona-writer",
        ]
        self.assertEqual(set(BUILTIN_CONTRACTS.keys()), set(expected_personas))

        for persona_id in expected_personas:
            raw = BUILTIN_CONTRACTS[persona_id]
            self.assertIn("io_contract", raw, f"io_contract ausente em {persona_id}")
            contract = get_builtin_contract(persona_id)
            self.assertIsNotNone(contract)
            self.assertIsInstance(contract.io_contract, IOContractConfig)
            self.assertEqual(contract.validate(), [], f"Erros de validação em {persona_id}")

    def test_builtin_contracts_io_definitions(self):
        """Verifica a especificação exata de cada persona built-in."""
        # 1. maia-orchestrator: required query, not strict, no required output
        maia = get_builtin_contract("maia-orchestrator")
        self.assertEqual(maia.io_contract.required_input_fields, ["query"])
        self.assertFalse(maia.io_contract.output_schema_strict)
        self.assertEqual(maia.io_contract.required_output_fields, [])

        # 2. eva-supervisor: no required input, strict, required verdict and confidence
        eva = get_builtin_contract("eva-supervisor")
        self.assertEqual(eva.io_contract.required_input_fields, [])
        self.assertTrue(eva.io_contract.output_schema_strict)
        self.assertEqual(eva.io_contract.required_output_fields, ["verdict", "confidence"])

        # 3. persona-devops: required command, not strict, required status
        devops = get_builtin_contract("persona-devops")
        self.assertEqual(devops.io_contract.required_input_fields, ["command"])
        self.assertFalse(devops.io_contract.output_schema_strict)
        self.assertEqual(devops.io_contract.required_output_fields, ["status"])

        # 4. persona-finops: required amount_brl, strict, required transaction_id and status
        finops = get_builtin_contract("persona-finops")
        self.assertEqual(finops.io_contract.required_input_fields, ["amount_brl"])
        self.assertTrue(finops.io_contract.output_schema_strict)
        self.assertEqual(finops.io_contract.required_output_fields, ["transaction_id", "status"])

        # 5. cx-triage: required customer_query, not strict, required response and sentiment
        cx = get_builtin_contract("cx-triage")
        self.assertEqual(cx.io_contract.required_input_fields, ["customer_query"])
        self.assertFalse(cx.io_contract.output_schema_strict)
        self.assertEqual(cx.io_contract.required_output_fields, ["response", "sentiment"])


class TestValidateInputContract(unittest.TestCase):
    """Testa a função validate_input_contract()."""

    def setUp(self):
        reset_all_singletons()

    def tearDown(self):
        reset_all_singletons()

    def test_validate_input_contract_blocks_on_missing_required_fields(self):
        """Deve bloquear quando campos obrigatórios estiverem ausentes."""
        # maia-orchestrator exige "query"
        res = validate_input_contract("maia-orchestrator", {})
        self.assertFalse(res.allowed)
        self.assertEqual(res.reason, "input_contract_violation")
        self.assertEqual(res.details.get("missing_fields"), ["query"])
        self.assertEqual(res.details.get("required"), ["query"])

        # persona-finops exige "amount_brl"
        res_fin = validate_input_contract("persona-finops", {"description": "licença"})
        self.assertFalse(res_fin.allowed)
        self.assertEqual(res_fin.reason, "input_contract_violation")
        self.assertEqual(res_fin.details.get("missing_fields"), ["amount_brl"])

        # cx-triage exige "customer_query"
        res_cx = validate_input_contract("cx-triage", {"query": "teste"})
        self.assertFalse(res_cx.allowed)
        self.assertEqual(res_cx.reason, "input_contract_violation")
        self.assertEqual(res_cx.details.get("missing_fields"), ["customer_query"])

    def test_validate_input_contract_passes_with_all_fields_present(self):
        """Deve aprovar quando todos os campos obrigatórios estiverem presentes."""
        res_maia = validate_input_contract("maia-orchestrator", {"query": "pesquisar logs"})
        self.assertTrue(res_maia.allowed)
        self.assertEqual(res_maia.reason, "input_contract_valid")

        res_devops = validate_input_contract("persona-devops", {"command": "kubectl get pods", "env": "prod"})
        self.assertTrue(res_devops.allowed)
        self.assertEqual(res_devops.reason, "input_contract_valid")

        res_cx = validate_input_contract("cx-triage", {"customer_query": "Troca de produto"})
        self.assertTrue(res_cx.allowed)
        self.assertEqual(res_cx.reason, "input_contract_valid")

    def test_validate_input_contract_passes_with_no_contract(self):
        """Deve aprovar se persona_id for None, desconhecido ou sem campos requeridos."""
        # Sem persona_id
        res_none = validate_input_contract(None, {"qualquer": "valor"})
        self.assertTrue(res_none.allowed)
        self.assertEqual(res_none.reason, "no_contract")

        # Persona desconhecida
        res_unknown = validate_input_contract("persona-inexistente", {"query": "teste"})
        self.assertTrue(res_unknown.allowed)
        self.assertEqual(res_unknown.reason, "no_input_contract")

        # eva-supervisor não possui required_input_fields
        res_eva = validate_input_contract("eva-supervisor", {})
        self.assertTrue(res_eva.allowed)
        self.assertEqual(res_eva.reason, "no_input_contract")


class TestValidateOutputContract(unittest.TestCase):
    """Testa a função validate_output_contract()."""

    def setUp(self):
        reset_all_singletons()

    def tearDown(self):
        reset_all_singletons()

    def test_validate_output_contract_detects_missing_output_fields(self):
        """Deve detectar campos de saída ausentes e sinalizar strict/valid."""
        # eva-supervisor requer "verdict" e "confidence", strict=True
        check_eva = validate_output_contract("eva-supervisor", {"verdict": "pass"})
        self.assertFalse(check_eva["valid"])
        self.assertEqual(check_eva["missing_fields"], ["confidence"])
        self.assertTrue(check_eva["strict"])

        # persona-finops requer "transaction_id" e "status", strict=True
        check_fin = validate_output_contract("persona-finops", {"transaction_id": "tx-123"})
        self.assertFalse(check_fin["valid"])
        self.assertEqual(check_fin["missing_fields"], ["status"])
        self.assertTrue(check_fin["strict"])

        # cx-triage requer "response" e "sentiment", strict=False
        check_cx = validate_output_contract("cx-triage", {"response": "Olá cliente!"})
        self.assertFalse(check_cx["valid"])
        self.assertEqual(check_cx["missing_fields"], ["sentiment"])
        self.assertFalse(check_cx["strict"])

    def test_validate_output_contract_passes_with_complete_output(self):
        """Deve validar com sucesso quando todos os campos requeridos estiverem presentes."""
        check_eva = validate_output_contract(
            "eva-supervisor",
            {"verdict": "pass", "confidence": 0.98, "comment": "aprovado"},
        )
        self.assertTrue(check_eva["valid"])
        self.assertEqual(check_eva["missing_fields"], [])
        self.assertTrue(check_eva["strict"])

        check_devops = validate_output_contract(
            "persona-devops",
            {"status": "ok", "exit_code": 0},
        )
        self.assertTrue(check_devops["valid"])
        self.assertEqual(check_devops["missing_fields"], [])
        self.assertFalse(check_devops["strict"])

    def test_validate_output_contract_with_no_contract_or_empty_output_fields(self):
        """Deve retornar valid=True quando não houver persona_id ou required_output_fields for vazio."""
        # Sem persona_id
        check_none = validate_output_contract(None, {"result": "ok"})
        self.assertTrue(check_none["valid"])
        self.assertEqual(check_none["missing_fields"], [])
        self.assertFalse(check_none["strict"])

        # maia-orchestrator não possui required_output_fields
        check_maia = validate_output_contract("maia-orchestrator", {})
        self.assertTrue(check_maia["valid"])
        self.assertEqual(check_maia["missing_fields"], [])
        self.assertFalse(check_maia["strict"])

        # Persona desconhecida
        check_unknown = validate_output_contract("persona-desconhecida", {"result": "ok"})
        self.assertTrue(check_unknown["valid"])
        self.assertEqual(check_unknown["missing_fields"], [])
        self.assertFalse(check_unknown["strict"])


class TestPostCallStrictWarning(unittest.TestCase):
    """Testa o comportamento de aviso em stderr no post_call_pipeline() para modo strict."""

    def setUp(self):
        reset_all_singletons()

    def tearDown(self):
        reset_all_singletons()

    def test_output_strict_mode_logs_warning_to_stderr(self):
        """Violação de contrato de saída em persona strict deve emitir warning no stderr."""
        captured_stderr = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            post_call_pipeline(
                tool_name="review_code",
                success=True,
                identity="agent:supervisor",
                trace_id="trace-strict-test-1",
                result={"verdict": "pass"},  # ausente: "confidence"
                persona_id="eva-supervisor",
            )
        finally:
            sys.stderr = old_stderr

        output = captured_stderr.getvalue()
        self.assertIn("output_contract: strict violation for eva-supervisor", output)
        self.assertIn("confidence", output)

    def test_output_non_strict_mode_does_not_log_warning(self):
        """Persona não-strict com campos faltando NÃO deve logar aviso de violação estrita."""
        captured_stderr = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            post_call_pipeline(
                tool_name="search_knowledge_base",
                success=True,
                identity="agent:cx",
                trace_id="trace-non-strict-test",
                result={"response": "ajuda realizada"},  # ausente: "sentiment", mas strict=False
                persona_id="cx-triage",
            )
        finally:
            sys.stderr = old_stderr

        output = captured_stderr.getvalue()
        self.assertNotIn("output_contract: strict violation", output)

    def test_output_strict_mode_complete_output_no_warning(self):
        """Persona strict com output completo NÃO deve emitir nenhum aviso no stderr."""
        captured_stderr = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured_stderr
        try:
            post_call_pipeline(
                tool_name="review_code",
                success=True,
                identity="agent:supervisor",
                trace_id="trace-strict-ok",
                result={"verdict": "pass", "confidence": 0.99},
                persona_id="eva-supervisor",
            )
        finally:
            sys.stderr = old_stderr

        output = captured_stderr.getvalue()
        self.assertNotIn("output_contract: strict violation", output)


class TestPreCallPipelineInputValidation(unittest.TestCase):
    """Testa a integração da validação de input contract dentro do pre_call_pipeline()."""

    def setUp(self):
        reset_all_singletons()

    def tearDown(self):
        reset_all_singletons()

    def test_pre_call_pipeline_blocks_on_missing_input(self):
        """pre_call_pipeline bloqueia chamada se campos obrigatórios de input faltarem."""
        # cx-triage possui autonomia auto_execute, passa em RBAC e forbidden_topics
        res = pre_call_pipeline(
            persona_id="cx-triage",
            tool_name="search_knowledge_base",
            args={},  # ausente: "customer_query"
            task_text="Como alterar minha senha de acesso?",
        )
        self.assertFalse(res.allowed)
        self.assertEqual(res.reason, "input_contract_violation")
        self.assertIn("customer_query", res.details.get("missing_fields", []))

    def test_pre_call_pipeline_passes_when_input_valid(self):
        """pre_call_pipeline aprova quando os campos do contrato de input estão presentes."""
        res = pre_call_pipeline(
            persona_id="cx-triage",
            tool_name="search_knowledge_base",
            args={"customer_query": "Como alterar minha senha de acesso?"},
            task_text="Como alterar minha senha de acesso?",
        )
        self.assertTrue(res.allowed)
        self.assertEqual(res.reason, "all_checks_passed")

    def test_pre_call_pipeline_without_persona_skips_input_validation(self):
        """pre_call_pipeline sem persona_id não executa validação de contrato de input."""
        res = pre_call_pipeline(
            persona_id=None,
            tool_name="search_knowledge_base",
            args={},
            task_text="Como alterar minha senha de acesso?",
        )
        self.assertTrue(res.allowed)
        self.assertEqual(res.reason, "all_checks_passed")


if __name__ == "__main__":
    unittest.main()

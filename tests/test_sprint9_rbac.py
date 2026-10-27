"""Testes da implementação de RBAC Explícito por Persona (Sprint 9 — R11).

Cobre:
- RBACConfig: instanciação, defaults e validação (overlap allowed/denied)
- PersonaContract: integração com RBACConfig, validação em cascata, to_dict/from_dict
- check_rbac: allowlist, denylist, herança (allowed vazio), persona nula/desconhecida
- pre_call_pipeline: bloqueio por RBAC antes de FT e autonomia
- BUILTIN_CONTRACTS: papéis e listas configuradas para todas as 5 personas
- Restrições específicas: CX Triage e FinOps
- Backward compatibility: contratos legados sem campo 'rbac'
"""

import unittest
from typing import Dict, Any

from core.schema.persona_contract import (
    PersonaContract,
    RBACConfig,
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
    check_rbac,
    pre_call_pipeline,
    reset_all_singletons,
    _persona_cache,
)


class TestRBACConfig(unittest.TestCase):
    """Testes unitários para o dataclass RBACConfig."""

    def test_rbac_config_defaults(self):
        """RBACConfig com valores padrão deve ser válido e vazio."""
        rbac = RBACConfig()
        self.assertEqual(rbac.rbac_role, "")
        self.assertEqual(rbac.allowed_tools, [])
        self.assertEqual(rbac.denied_tools, [])
        self.assertEqual(rbac.validate(), [])

    def test_rbac_config_validation_overlap(self):
        """Validação deve detectar colisão entre allowed_tools e denied_tools."""
        rbac = RBACConfig(
            rbac_role="role:agent:test",
            allowed_tools=["search_knowledge_base", "run_safe_command"],
            denied_tools=["run_safe_command", "read_vault_file"],
        )
        errors = rbac.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("tools em allowed e denied simultaneamente: run_safe_command", errors[0])

    def test_rbac_config_validation_multiple_overlaps_sorted(self):
        """Múltiplas colisões devem ser listadas em ordem alfabética."""
        rbac = RBACConfig(
            rbac_role="role:agent:test",
            allowed_tools=["tool_z", "tool_a", "tool_m"],
            denied_tools=["tool_m", "tool_z"],
        )
        errors = rbac.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("tool_m, tool_z", errors[0])

    def test_rbac_config_no_overlap_valid(self):
        """Listas disjuntas devem ser válidas."""
        rbac = RBACConfig(
            rbac_role="role:agent:operator",
            allowed_tools=["read_doc"],
            denied_tools=["delete_doc"],
        )
        self.assertEqual(rbac.validate(), [])


class TestPersonaContractRBAC(unittest.TestCase):
    """Testes de integração entre PersonaContract e RBACConfig."""

    def test_persona_contract_with_rbac_validates(self):
        """PersonaContract com RBAC válido passa na validação."""
        contract = PersonaContract(
            persona_id="test-agent",
            display_name="Test Agent",
            role="specialist",
            moe_routing=MoERoutingConfig(embedding_tags=["teste"]),
            rbac=RBACConfig(
                rbac_role="role:agent:test",
                allowed_tools=["search_knowledge_base"],
                denied_tools=["run_safe_command"],
            ),
        )
        self.assertEqual(contract.validate(), [])

    def test_persona_contract_catches_rbac_error(self):
        """PersonaContract.validate() propaga erros do RBACConfig."""
        contract = PersonaContract(
            persona_id="test-agent",
            display_name="Test Agent",
            role="specialist",
            moe_routing=MoERoutingConfig(embedding_tags=["teste"]),
            rbac=RBACConfig(
                rbac_role="role:agent:test",
                allowed_tools=["conflict_tool"],
                denied_tools=["conflict_tool"],
            ),
        )
        errors = contract.validate()
        self.assertTrue(any("tools em allowed e denied simultaneamente" in e for e in errors))

    def test_to_dict_from_dict_roundtrip_with_rbac(self):
        """Serialização to_dict/from_dict preserva a estrutura RBAC completa."""
        original = PersonaContract(
            persona_id="roundtrip-agent",
            display_name="Roundtrip Agent",
            role="orchestrator",
            moe_routing=MoERoutingConfig(embedding_tags=["orquestração"]),
            rbac=RBACConfig(
                rbac_role="role:agent:custom_role",
                allowed_tools=["tool_1", "tool_2"],
                denied_tools=["tool_3", "tool_4"],
            ),
        )
        data = original.to_dict()
        self.assertIn("rbac", data)
        self.assertEqual(data["rbac"]["rbac_role"], "role:agent:custom_role")
        self.assertEqual(data["rbac"]["allowed_tools"], ["tool_1", "tool_2"])
        self.assertEqual(data["rbac"]["denied_tools"], ["tool_3", "tool_4"])

        restored = PersonaContract.from_dict(data)
        self.assertEqual(restored.rbac.rbac_role, "role:agent:custom_role")
        self.assertEqual(restored.rbac.allowed_tools, ["tool_1", "tool_2"])
        self.assertEqual(restored.rbac.denied_tools, ["tool_3", "tool_4"])
        self.assertEqual(restored.validate(), [])

    def test_from_dict_backward_compatibility_missing_rbac(self):
        """from_dict sem chave 'rbac' atribui RBACConfig padrão."""
        minimal_data: Dict[str, Any] = {
            "schema_version": "aios.example/v1",
            "persona_id": "legacy-agent",
            "display_name": "Legacy Agent",
        }
        contract = PersonaContract.from_dict(minimal_data)
        self.assertIsInstance(contract.rbac, RBACConfig)
        self.assertEqual(contract.rbac.rbac_role, "")
        self.assertEqual(contract.rbac.allowed_tools, [])
        self.assertEqual(contract.rbac.denied_tools, [])
        self.assertEqual(contract.validate(), [])


class TestCheckRBAC(unittest.TestCase):
    """Testes da função check_rbac() e pre_call_pipeline() com RBAC."""

    def setUp(self):
        reset_all_singletons()

    def tearDown(self):
        reset_all_singletons()

    def test_check_rbac_allows_tool_in_allowed_tools(self):
        """Ferramenta presente em allowed_tools deve ser autorizada."""
        result = check_rbac("maia-orchestrator", "search_knowledge_base")
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "rbac_ok")

    def test_check_rbac_blocks_tool_in_denied_tools(self):
        """Ferramenta presente em denied_tools deve ser bloqueada com rbac_denied."""
        result = check_rbac("maia-orchestrator", "run_safe_command")
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "rbac_denied")
        self.assertEqual(result.details["tool"], "run_safe_command")
        self.assertEqual(result.details["rbac_role"], "role:agent:orchestrator")
        self.assertIn("está na denied_tools", result.details["reason"])

    def test_check_rbac_blocks_tool_not_in_allowed_tools(self):
        """Ferramenta ausente de allowed_tools (não-vazio) deve ser bloqueada com rbac_not_allowed."""
        result = check_rbac("maia-orchestrator", "unregistered_dangerous_tool")
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "rbac_not_allowed")
        self.assertEqual(result.details["tool"], "unregistered_dangerous_tool")
        self.assertEqual(result.details["rbac_role"], "role:agent:orchestrator")
        self.assertIn("allowed", result.details)

    def test_check_rbac_allows_when_allowed_tools_is_empty_inherit(self):
        """Quando allowed_tools estiver vazio, permite ferramentas não-denied (herança)."""
        contract = PersonaContract(
            persona_id="inherit-agent",
            display_name="Inherit Agent",
            role="specialist",
            moe_routing=MoERoutingConfig(embedding_tags=["teste"]),
            rbac=RBACConfig(
                rbac_role="role:agent:inherit",
                allowed_tools=[],
                denied_tools=["strictly_forbidden"],
            ),
        )
        _persona_cache["inherit-agent"] = contract

        # Ferramenta arbitrária permitida
        res_ok = check_rbac("inherit-agent", "some_regular_tool")
        self.assertTrue(res_ok.allowed)
        self.assertEqual(res_ok.reason, "rbac_ok")

        # Ferramenta negada continua bloqueada
        res_denied = check_rbac("inherit-agent", "strictly_forbidden")
        self.assertFalse(res_denied.allowed)
        self.assertEqual(res_denied.reason, "rbac_denied")

    def test_check_rbac_passes_with_no_persona_id(self):
        """Sem persona_id, check_rbac permite e retorna 'no_rbac_contract'."""
        result_none = check_rbac(None, "run_safe_command")
        self.assertTrue(result_none.allowed)
        self.assertEqual(result_none.reason, "no_rbac_contract")

        result_empty = check_rbac("", "run_safe_command")
        self.assertTrue(result_empty.allowed)
        self.assertEqual(result_empty.reason, "no_rbac_contract")

    def test_check_rbac_passes_with_unknown_persona(self):
        """Com persona desconhecida (sem contrato), permite e retorna 'no_contract'."""
        result = check_rbac("unknown-persona-xyz", "run_safe_command")
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "no_contract")

    def test_pre_call_pipeline_blocks_denied_tool(self):
        """pre_call_pipeline bloqueia ferramenta negada antes de FT e autonomia."""
        result = pre_call_pipeline("maia-orchestrator", "run_safe_command", {})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "rbac_denied")
        self.assertEqual(result.details["tool"], "run_safe_command")

    def test_pre_call_pipeline_blocks_not_allowed_tool(self):
        """pre_call_pipeline bloqueia ferramenta não listada em allowed_tools."""
        result = pre_call_pipeline("cx-triage", "list_rules", {})
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "rbac_not_allowed")


class TestBuiltinContractsRBAC(unittest.TestCase):
    """Testes dos contratos built-in e regras específicas de personas."""

    def setUp(self):
        reset_all_singletons()

    def test_all_5_builtins_have_rbac_configured(self):
        """Todos os 5 contratos pré-definidos possuem RBAC configurado e válido."""
        expected_personas = [
            "maia-orchestrator",
            "eva-supervisor",
            "persona-devops",
            "persona-finops",
            "cx-triage",
        ]
        for p_id in expected_personas:
            contract = get_builtin_contract(p_id)
            self.assertIsNotNone(contract, f"{p_id} não encontrado")
            self.assertIsInstance(contract.rbac, RBACConfig)
            self.assertTrue(contract.rbac.rbac_role.startswith("role:agent:"), f"role inválido para {p_id}")
            self.assertTrue(len(contract.rbac.allowed_tools) > 0, f"allowed_tools vazio para {p_id}")
            self.assertEqual(contract.validate(), [], f"erros de validação em {p_id}")

    def test_cx_triage_rbac_permissions(self):
        """CX Triage: estritamente somente-leitura. Bloqueia comandos seguros, arq e vault."""
        cx = get_builtin_contract("cx-triage")
        self.assertEqual(cx.rbac.rbac_role, "role:agent:cx_readonly")
        self.assertIn("run_safe_command", cx.rbac.denied_tools)
        self.assertIn("get_system_architecture", cx.rbac.denied_tools)
        self.assertIn("read_vault_file", cx.rbac.denied_tools)

        # Denied tools bloqueadas
        self.assertFalse(check_rbac("cx-triage", "run_safe_command").allowed)
        self.assertFalse(check_rbac("cx-triage", "get_system_architecture").allowed)
        self.assertFalse(check_rbac("cx-triage", "read_vault_file").allowed)

        # Allowed tools permitidas
        self.assertTrue(check_rbac("cx-triage", "search_knowledge_base").allowed)
        self.assertTrue(check_rbac("cx-triage", "get_brain_status").allowed)

        # Ferramentas não listadas em allowed bloqueadas
        self.assertFalse(check_rbac("cx-triage", "list_rules").allowed)

    def test_finops_rbac_permissions(self):
        """FinOps: bloqueia run_safe_command e get_system_architecture."""
        finops = get_builtin_contract("persona-finops")
        self.assertEqual(finops.rbac.rbac_role, "role:agent:finops_specialist")
        self.assertIn("run_safe_command", finops.rbac.denied_tools)
        self.assertIn("get_system_architecture", finops.rbac.denied_tools)

        # Denied tools bloqueadas
        self.assertFalse(check_rbac("persona-finops", "run_safe_command").allowed)
        self.assertFalse(check_rbac("persona-finops", "get_system_architecture").allowed)

        # Allowed tools permitidas
        self.assertTrue(check_rbac("persona-finops", "search_knowledge_base").allowed)
        self.assertTrue(check_rbac("persona-finops", "list_rules").allowed)
        self.assertTrue(check_rbac("persona-finops", "get_rule_evidence").allowed)

    def test_devops_rbac_permissions(self):
        """DevOps: tem permissão para run_safe_command e get_system_architecture."""
        devops = get_builtin_contract("persona-devops")
        self.assertEqual(devops.rbac.rbac_role, "role:agent:devops_executor")
        self.assertIn("run_safe_command", devops.rbac.allowed_tools)
        self.assertIn("get_system_architecture", devops.rbac.allowed_tools)

        self.assertTrue(check_rbac("persona-devops", "run_safe_command").allowed)
        self.assertTrue(check_rbac("persona-devops", "get_system_architecture").allowed)

    def test_eva_supervisor_rbac_permissions(self):
        """Eva Supervisor: ferramentas de revisão e qualidade permitidas."""
        eva = get_builtin_contract("eva-supervisor")
        self.assertEqual(eva.rbac.rbac_role, "role:agent:supervisor")
        self.assertIn("get_adr", eva.rbac.allowed_tools)

        self.assertTrue(check_rbac("eva-supervisor", "get_adr").allowed)
        self.assertFalse(check_rbac("eva-supervisor", "run_safe_command").allowed)


if __name__ == "__main__":
    unittest.main()

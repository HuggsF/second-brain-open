"""Testes do Sprint 2: Scoped Context View (G6) + MoE Router (G4)."""
import unittest

from core.memory.session_store import (
    SessionMemoryStore,
    ScopePolicy,
    PERSONA_SCOPE_POLICIES,
)
from core.routing.moe_router import (
    MoERouter,
    PersonaProfile,
    PERSONA_PROFILES,
    RoutingDecision,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Testes de Scoped Context View (Gap G6)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScopePolicy(unittest.TestCase):
    """Testes do enum ScopePolicy."""

    def test_all_policies_exist(self):
        self.assertEqual(len(ScopePolicy), 5)
        self.assertIn(ScopePolicy.FULL_ACCESS, ScopePolicy)
        self.assertIn(ScopePolicy.SCOPED_SUMMARY, ScopePolicy)
        self.assertIn(ScopePolicy.FINANCIAL_ISOLATED_VIEW, ScopePolicy)
        self.assertIn(ScopePolicy.TECHNICAL_METRICS_ONLY, ScopePolicy)
        self.assertIn(ScopePolicy.SECURITY_AUDIT_VIEW, ScopePolicy)

    def test_all_agent_roles_have_default_policy(self):
        for role in ("manager", "researcher", "coder", "writer", "reviewer"):
            self.assertIn(role, PERSONA_SCOPE_POLICIES)


class TestScopedContextView(unittest.TestCase):
    """Testes do get_scoped_view() no SessionMemoryStore."""

    def setUp(self):
        self.store = SessionMemoryStore()
        # Popula sessão com registros heterogêneos (simulando missão completa)
        self.store.append("mission-1", {
            "agent": "manager", "role": "manager", "event": "mission_start",
            "status": "running", "summary": "Missão iniciada",
            "payload": {"secret": "dados_sensiveis"}, "type": "lifecycle",
            "amount": 15000.00, "currency": "BRL",
            "duration_ms": 120, "cpu_percent": 45.2,
            "gate_results": {"dag": "PASS"}, "semaphore": "GREEN",
        })
        self.store.append("mission-1", {
            "agent": "coder", "role": "coder", "event": "deploy",
            "status": "ok", "summary": "Deploy executado",
            "payload": {"command": "kubectl apply -f deploy.yaml"},
            "type": "tool_call",
            "duration_ms": 3400, "cpu_percent": 78.1, "memory_mb": 512,
            "error_type": None, "service_name": "api-gateway",
            "nfe_key": "12345678901234567890123456789012345678901234",
        })

    def test_manager_full_access_sees_everything(self):
        """Manager (FULL_ACCESS) deve ver todos os campos."""
        view = self.store.get_scoped_view("mission-1", "manager")
        self.assertEqual(len(view), 2)
        # Deve conter campo 'payload' (campo sensível)
        self.assertIn("payload", view[0])
        self.assertIn("secret", view[0]["payload"])

    def test_researcher_scoped_summary_hides_payload(self):
        """Researcher (SCOPED_SUMMARY) não deve ver payload nem dados financeiros."""
        view = self.store.get_scoped_view("mission-1", "researcher")
        self.assertEqual(len(view), 2)
        for record in view:
            self.assertNotIn("payload", record)
            self.assertNotIn("amount", record)
            self.assertNotIn("cpu_percent", record)
            self.assertIn("_scope_policy", record)
            self.assertEqual(record["_scope_policy"], "SCOPED_SUMMARY")

    def test_coder_technical_metrics_only(self):
        """Coder (TECHNICAL_METRICS_ONLY) deve ver apenas métricas técnicas."""
        view = self.store.get_scoped_view("mission-1", "coder")
        self.assertEqual(len(view), 2)
        # Registro do deploy deve ter duration_ms, cpu_percent, memory_mb
        deploy = view[1]
        self.assertIn("duration_ms", deploy)
        self.assertIn("cpu_percent", deploy)
        # Não deve ter payload, amount, gate_results
        self.assertNotIn("payload", deploy)
        self.assertNotIn("amount", deploy)
        self.assertNotIn("gate_results", deploy)

    def test_reviewer_security_audit_view(self):
        """Reviewer (SECURITY_AUDIT_VIEW) deve ver gate_results e semáforos."""
        view = self.store.get_scoped_view("mission-1", "reviewer")
        first = view[0]
        self.assertIn("gate_results", first)
        self.assertIn("semaphore", first)
        # Não deve ter payload, amount, cpu_percent
        self.assertNotIn("payload", first)
        self.assertNotIn("amount", first)
        self.assertNotIn("cpu_percent", first)

    def test_explicit_policy_overrides_default(self):
        """Policy explícita deve sobrescrever o mapeamento padrão da persona."""
        view = self.store.get_scoped_view(
            "mission-1", "manager",
            scope_policy=ScopePolicy.SCOPED_SUMMARY,
        )
        for record in view:
            self.assertNotIn("payload", record)
            self.assertEqual(record["_scope_policy"], "SCOPED_SUMMARY")

    def test_unknown_persona_defaults_to_scoped_summary(self):
        """Persona desconhecida deve usar SCOPED_SUMMARY como fallback."""
        view = self.store.get_scoped_view("mission-1", "persona_desconhecida")
        for record in view:
            self.assertNotIn("payload", record)
            self.assertEqual(record["_scope_policy"], "SCOPED_SUMMARY")

    def test_empty_session_returns_empty(self):
        view = self.store.get_scoped_view("session-inexistente", "manager")
        self.assertEqual(view, [])

    def test_scoped_view_preserves_recorded_at(self):
        """recorded_at deve sempre estar presente (é campo permitido por todas as policies)."""
        view = self.store.get_scoped_view("mission-1", "researcher")
        for record in view:
            self.assertIn("recorded_at", record)

    def test_backward_compat_get_history_unchanged(self):
        """get_history() deve continuar retornando tudo sem filtro."""
        history = self.store.get_history("mission-1")
        self.assertEqual(len(history), 2)
        self.assertIn("payload", history[0])


# ═══════════════════════════════════════════════════════════════════════════════
# Testes do MoE Gating Network Router (Gap G4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersonaProfile(unittest.TestCase):
    """Testes do PersonaProfile."""

    def test_all_roles_have_profiles(self):
        for role in ("manager", "researcher", "coder", "writer", "reviewer"):
            self.assertIn(role, PERSONA_PROFILES)

    def test_matches_keywords_basic(self):
        profile = PERSONA_PROFILES["coder"]
        score, matched = profile.matches_keywords("Preciso fazer deploy no kubernetes")
        self.assertGreater(score, 0)
        self.assertIn("deploy", matched)
        self.assertIn("kubernetes", matched)

    def test_matches_keywords_no_match(self):
        profile = PERSONA_PROFILES["coder"]
        score, matched = profile.matches_keywords("Qual é o prazo de entrega do pedido?")
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])

    def test_fallback_chain_defined(self):
        # Manager não tem fallback (é o fallback global)
        self.assertIsNone(PERSONA_PROFILES["manager"].fallback_persona)
        # Outros devem ter fallback
        self.assertIsNotNone(PERSONA_PROFILES["researcher"].fallback_persona)
        self.assertIsNotNone(PERSONA_PROFILES["coder"].fallback_persona)


class TestMoERouter(unittest.TestCase):
    """Testes do MoE Router."""

    def setUp(self):
        self.router = MoERouter()

    def test_routes_deploy_to_coder(self):
        decision = self.router.route("Preciso fazer deploy no kubernetes com docker")
        self.assertEqual(decision.selected_persona, "coder")
        self.assertGreater(decision.confidence_score, 0)
        self.assertFalse(decision.is_fallback)
        self.assertEqual(decision.method, "keyword")

    def test_routes_security_to_reviewer(self):
        decision = self.router.route("Auditar compliance e validar regras de segurança")
        self.assertEqual(decision.selected_persona, "reviewer")
        self.assertFalse(decision.is_fallback)

    def test_routes_documentation_to_writer(self):
        decision = self.router.route("Criar documentação do playbook e guia de template")
        self.assertEqual(decision.selected_persona, "writer")

    def test_routes_analysis_to_researcher(self):
        decision = self.router.route("Fazer análise de dados e diagnóstico das métricas")
        self.assertEqual(decision.selected_persona, "researcher")

    def test_routes_cx_to_manager(self):
        decision = self.router.route("Triagem do atendimento ao customer e suporte")
        self.assertEqual(decision.selected_persona, "manager")

    def test_ambiguous_text_fallbacks_to_manager(self):
        """Texto genérico sem keywords deve cair no manager (fallback global)."""
        decision = self.router.route("Olá, como posso ajudar?")
        self.assertEqual(decision.selected_persona, "manager")
        self.assertTrue(decision.is_fallback)

    def test_empty_text_fallbacks_to_manager(self):
        decision = self.router.route("")
        self.assertEqual(decision.selected_persona, "manager")
        self.assertTrue(decision.is_fallback)

    def test_none_text_fallbacks_to_manager(self):
        decision = self.router.route(None)
        self.assertEqual(decision.selected_persona, "manager")
        self.assertTrue(decision.is_fallback)

    def test_fallback_chain_tracked(self):
        """Quando fallback é acionado, a chain deve estar registrada."""
        decision = self.router.route("algo totalmente irrelevante xyzabc123")
        self.assertTrue(decision.is_fallback)
        self.assertIn("manager", decision.fallback_chain)

    def test_routing_decision_to_dict(self):
        decision = self.router.route("deploy no kubernetes")
        d = decision.to_dict()
        self.assertIn("selected_persona", d)
        self.assertIn("confidence_score", d)
        self.assertIn("matched_tags", d)
        self.assertIn("passed_threshold", d)

    def test_route_with_scores_returns_all_personas(self):
        result = self.router.route_with_scores("deploy no kubernetes")
        self.assertIn("decision", result)
        self.assertIn("all_scores", result)
        for role in PERSONA_PROFILES:
            self.assertIn(role, result["all_scores"])
            self.assertIn("score", result["all_scores"][role])
            self.assertIn("threshold", result["all_scores"][role])

    def test_custom_profiles(self):
        """Router deve aceitar profiles customizados."""
        custom = {
            "finops": PersonaProfile(
                role="finops",
                label="FinOps & Billing",
                embedding_tags=["faturamento", "nota fiscal", "cobrança", "pagamento"],
                confidence_threshold=0.20,
                fallback_persona=None,
            ),
        }
        router = MoERouter(profiles=custom)
        decision = router.route("Problema no faturamento da nota fiscal e cobrança e pagamento")
        self.assertEqual(decision.selected_persona, "finops")

    def test_threshold_property(self):
        decision = RoutingDecision(
            selected_persona="coder",
            confidence_score=0.80,
            matched_tags=["deploy"],
        )
        self.assertTrue(decision.passed_threshold)

        low_decision = RoutingDecision(
            selected_persona="coder",
            confidence_score=0.05,
            matched_tags=[],
        )
        self.assertFalse(low_decision.passed_threshold)


if __name__ == "__main__":
    unittest.main()

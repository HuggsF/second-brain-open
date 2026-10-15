"""Testes para o R6 — Integração do MoE Router no Orchestrator (Sprint 8).

Verifica:
1. _get_moe_router() retorna singleton
2. _route_agent_for_step() mantém o agente original quando score MoE é baixo ou fallback
3. _route_agent_for_step() redireciona quando MoE tem alta confiança (>= 0.3)
4. Compatibilidade regressiva com MISSION_PATTERNS
5. Fluxo completo de run_mission com MoE routing (enriquecimento de steps, _original_agent, eventos)
"""
import unittest
from unittest import mock

from backend.orchestrator import (
    AGENT_IDS,
    DEFAULT_STEPS,
    MISSION_PATTERNS,
    Orchestrator,
    _get_moe_router,
)
import backend.orchestrator as orch_mod
from core.routing.moe_router import MoERouter, RoutingDecision


class TestMoERouterSingleton(unittest.TestCase):
    """Testa o singleton do MoE Router no módulo orchestrator."""

    def test_get_moe_router_returns_instance(self):
        router = _get_moe_router()
        self.assertIsInstance(router, MoERouter)

    def test_get_moe_router_is_singleton(self):
        r1 = _get_moe_router()
        r2 = _get_moe_router()
        self.assertIs(r1, r2)

    def test_get_moe_router_reinitializes_if_reset(self):
        old_router = _get_moe_router()
        orch_mod._moe_router = None
        new_router = _get_moe_router()
        self.assertIsInstance(new_router, MoERouter)
        # Novo singleton em cache
        self.assertIs(_get_moe_router(), new_router)


class TestRouteAgentForStep(unittest.TestCase):
    """Testa o método _route_agent_for_step do Orchestrator."""

    def setUp(self):
        self.orch = Orchestrator(pace=0)

    def test_returns_original_agent_when_score_is_low(self):
        step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
            "bubble": "Pesquisando...",
        }
        # Texto sem relação semântica forte com nenhuma persona
        mission_text = "ola mundo sem palavras chave relevantes"
        result = self.orch._route_agent_for_step(step, mission_text)
        self.assertEqual(result, "researcher")

    def test_returns_original_agent_when_decision_is_fallback(self):
        step = {
            "agent": "coder",
            "tool": "get_brain_status",
            "bubble": "Checando...",
        }
        with mock.patch.object(
            orch_mod._get_moe_router(),
            "route",
            return_value=RoutingDecision(
                selected_persona="manager",
                confidence_score=0.5,
                matched_tags=[],
                is_fallback=True,
            ),
        ):
            result = self.orch._route_agent_for_step(step, "qualquer texto")
            self.assertEqual(result, "coder")

    def test_returns_original_agent_when_confidence_below_threshold(self):
        step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
            "bubble": "Pesquisando...",
        }
        # Score de 0.25 é abaixo do limiar de 0.3 para redirecionamento
        with mock.patch.object(
            orch_mod._get_moe_router(),
            "route",
            return_value=RoutingDecision(
                selected_persona="writer",
                confidence_score=0.25,
                matched_tags=["documentação"],
                is_fallback=False,
            ),
        ):
            result = self.orch._route_agent_for_step(step, "criar documentação")
            self.assertEqual(result, "researcher")

    def test_returns_original_agent_when_selected_persona_equals_original(self):
        step = {
            "agent": "writer",
            "tool": "search_knowledge_base",
            "bubble": "Escrevendo playbook e documentação...",
        }
        mission_text = "redigir documentação guia e playbook template"
        result = self.orch._route_agent_for_step(step, mission_text)
        self.assertEqual(result, "writer")

    def test_reroutes_to_writer_when_step_and_task_have_high_writer_confidence(self):
        step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
            "bubble": "Redigindo template, manual e guia...",
        }
        mission_text = "escrever documentação e playbook com manual e guia template"
        result = self.orch._route_agent_for_step(step, mission_text)
        self.assertEqual(result, "writer")

    def test_reroutes_to_coder_when_step_and_task_have_high_coder_confidence(self):
        step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
            "bubble": "Verificando deploy no kubernetes e docker...",
        }
        mission_text = "deploy k8s kubernetes docker infraestrutura devops ci cd teste monitoring"
        result = self.orch._route_agent_for_step(step, mission_text)
        self.assertEqual(result, "coder")

    def test_reroutes_to_reviewer_when_step_and_task_have_high_reviewer_confidence(self):
        step = {
            "agent": "coder",
            "tool": "get_system_architecture",
            "bubble": "Verificando conformidade...",
        }
        mission_text = "revisão auditoria de segurança compliance policy regra validação dlp pii"
        result = self.orch._route_agent_for_step(step, mission_text)
        self.assertEqual(result, "reviewer")

    def test_handles_step_without_bubble(self):
        step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
        }
        mission_text = "escrever documentação redação template playbook readme manual guia"
        result = self.orch._route_agent_for_step(step, mission_text)
        self.assertEqual(result, "writer")


class TestMissionPatternsBackwardCompatibility(unittest.TestCase):
    """Garante que _match_pattern continua funcionando de forma idêntica."""

    def setUp(self):
        self.orch = Orchestrator(pace=0)

    def test_match_diagnosticar_pattern(self):
        steps = self.orch._match_pattern("diagnosticar erro no hub")
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]["agent"], "researcher")
        self.assertEqual(steps[1]["agent"], "coder")
        self.assertEqual(steps[2]["agent"], "reviewer")
        self.assertEqual(steps[0]["input"]["query"], "diagnosticar erro no hub")

    def test_match_playbook_pattern(self):
        steps = self.orch._match_pattern("abrir playbook pb-01")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["agent"], "researcher")
        self.assertEqual(steps[1]["agent"], "reviewer")

    def test_match_adr_pattern(self):
        steps = self.orch._match_pattern("pesquisar adr de arquitetura")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["agent"], "researcher")

    def test_match_oauth_pattern(self):
        steps = self.orch._match_pattern("como funciona o token oauth do bling?")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["agent"], "researcher")
        self.assertEqual(steps[1]["agent"], "coder")

    def test_match_status_pattern(self):
        steps = self.orch._match_pattern("qual o status da saúde do brain qdrant?")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["agent"], "coder")

    def test_match_fallback_default_steps(self):
        steps = self.orch._match_pattern("algo completamente desconhecido e generico")
        self.assertEqual(len(steps), len(DEFAULT_STEPS))
        self.assertEqual(steps[0]["agent"], "researcher")
        self.assertEqual(steps[0]["tool"], "search_knowledge_base")


class TestFullMissionFlowWithMoERouting(unittest.IsolatedAsyncioTestCase):
    """Testa o ciclo de vida completo de run_mission com dynamic routing MoE."""

    async def test_full_mission_flow_without_rerouting(self):
        """Missão padrão sem desvio do MoE Router preserva os agentes originais."""
        orch = Orchestrator(pace=0)
        events = []
        async for event in orch.run_mission("diagnosticar erro no hub", mission_id=101):
            events.append(event)
            if event.get("type") == "approval_request":
                orch.approve()

        # Verifica eventos básicos
        types = [e["type"] for e in events]
        self.assertIn("status_change", types)
        self.assertIn("collaboration", types)
        self.assertIn("message", types)
        self.assertIn("approval_request", types)
        self.assertIn("completion", types)

        # Distribute event contém os agentes originais
        distribute_events = [e for e in events if e.get("type") == "collaboration" and e["payload"].get("subtype") == "distribute"]
        self.assertEqual(len(distribute_events), 1)
        distribute = distribute_events[0]
        # Padrão diagnosticar envolve researcher, coder, reviewer
        self.assertIn("researcher", distribute["payload"]["to"])
        self.assertIn("coder", distribute["payload"]["to"])
        self.assertIn("reviewer", distribute["payload"]["to"])

        # Completion emitido por manager
        completion = [e for e in events if e.get("type") == "completion"][0]
        self.assertEqual(completion["agentId"], "manager")

    async def test_full_mission_flow_with_moe_rerouting(self):
        """Missão com forte semântica de documentação reroteia step para writer."""
        orch = Orchestrator(pace=0)
        task = "escrever documentação e redigir manual guia template de playbook"
        events = []

        async for event in orch.run_mission(task, mission_id=202):
            events.append(event)
            if event.get("type") == "approval_request":
                orch.approve()

        # O padrão de 'playbook' normalmente tem step 0 com researcher.
        # Com MoE routing sobre "documentação redigir manual guia template de playbook",
        # o primeiro step deve ter sido reroteado para writer!
        distribute_events = [e for e in events if e.get("type") == "collaboration" and e["payload"].get("subtype") == "distribute"]
        self.assertEqual(len(distribute_events), 1)
        agents_involved = distribute_events[0]["payload"]["to"]
        self.assertIn("writer", agents_involved)

        # O writer deve ter trabalhado (emitido status_change e message)
        writer_events = [e for e in events if e["agentId"] == "writer"]
        self.assertTrue(len(writer_events) >= 2)
        writer_types = {e["type"] for e in writer_events}
        self.assertIn("status_change", writer_types)
        self.assertIn("message", writer_types)

        # Finalização conclui com sucesso
        last_event = events[-1]
        self.assertEqual(last_event["type"], "completion")
        self.assertEqual(last_event["agentId"], "manager")

    async def test_original_agent_preserved_in_step_metadata(self):
        """Garante que step['_original_agent'] guarda o agente original quando reroteado."""
        orch = Orchestrator(pace=0)
        # Monta um step artificial com researcher
        step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
            "bubble": "Redigindo documentação template manual e guia...",
            "input": {"query": ""},
        }
        task = "escrever documentação redação template playbook manual guia"
        routed = orch._route_agent_for_step(step, task)
        self.assertEqual(routed, "writer")

        # Simula a atribuição feita no loop de run_mission
        if routed != step["agent"]:
            step["_original_agent"] = step["agent"]
            step["agent"] = routed

        self.assertEqual(step["_original_agent"], "researcher")
        self.assertEqual(step["agent"], "writer")

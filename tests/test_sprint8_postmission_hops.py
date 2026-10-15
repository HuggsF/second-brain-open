"""Testes do Sprint 8: R5 (Post-mission gates execution) e R9 (Max Hops + TTL).

Cobre:
- run_post_mission_gates com persona que tem post_mission gates (maia-orchestrator)
- run_post_mission_gates com persona sem post_mission gates (persona-devops)
- run_post_mission_gates sem persona_id ou persona desconhecida
- run_post_mission_gates com documento válido do Vault vs alucinado
- max_hops enforcement no Orchestrator (truncamento de passos para max_hops)
- TTL enforcement no Orchestrator (timeout de 30s)
- Backward compatibility (sem persona = sem truncamento)
- Soft enforcement de post-mission gates no Orchestrator (emite warning sem bloquear)
"""
import asyncio
import time
from unittest import mock
import pytest

from backend.orchestrator import (
    Orchestrator,
    AGENT_PERSONA_MAP,
    MISSION_TTL_SECONDS,
)
from core.integration import (
    run_post_mission_gates,
    get_persona_contract,
    reset_all_singletons,
)
from core.schema.persona_contract import PersonaContract, QualityGatesConfig


# ─── Utilitários de Teste ───

async def _collect_events(orchestrator: Orchestrator, task: str) -> list:
    """Coleta todos os eventos de run_mission com auto-aprovação de background."""
    events = []

    async def approver():
        while True:
            await asyncio.sleep(0.01)
            orchestrator.approve()

    approver_task = asyncio.create_task(approver())
    try:
        async for evt in orchestrator.run_mission(task):
            events.append(evt)
    finally:
        approver_task.cancel()
    return events


# ─── Testes de R5: run_post_mission_gates ───

class TestRunPostMissionGates:
    """Testes unitários para run_post_mission_gates()."""

    def setup_method(self):
        reset_all_singletons()

    def test_with_persona_having_post_mission_valid_doc(self):
        """Persona com post_mission gates e documento real no Vault deve passar."""
        mission_results = [
            {
                "tool": "search_knowledge_base",
                "sources": [
                    {
                        "document": "adrs/ADR-006-implementacao-flowlogger-observabilidade-semaforos.md",
                        "score": 0.95,
                    }
                ],
            }
        ]
        result = run_post_mission_gates("maia-orchestrator", mission_results)
        assert result["gates_run"] == ["grounding_sha256"]
        assert result["all_passed"] is True
        assert len(result["gate_results"]) == 1
        assert result["gate_results"][0]["passed"] is True
        assert result["gate_results"][0]["semaphore"] == "GREEN"

    def test_with_persona_having_post_mission_hallucinated_doc(self):
        """Persona com post_mission gates e documento inexistente deve falhar."""
        mission_results = [
            {
                "tool": "search_knowledge_base",
                "sources": [
                    {
                        "document": "adrs/ADR-999-documento-que-nao-existe.md",
                        "score": 0.5,
                    }
                ],
            }
        ]
        result = run_post_mission_gates("maia-orchestrator", mission_results)
        assert result["gates_run"] == ["grounding_sha256"]
        assert result["all_passed"] is False
        assert len(result["gate_results"]) == 1
        assert result["gate_results"][0]["passed"] is False
        assert result["gate_results"][0]["semaphore"] == "RED"

    def test_with_persona_without_post_mission_gates(self):
        """Persona sem post_mission gates (ex: persona-devops) retorna vazio e aprovado."""
        mission_results = [
            {
                "tool": "search_knowledge_base",
                "sources": [{"document": "adrs/ADR-006-implementacao-flowlogger-observabilidade-semaforos.md"}],
            }
        ]
        result = run_post_mission_gates("persona-devops", mission_results)
        assert result["gates_run"] == []
        assert result["all_passed"] is True
        assert result["gate_results"] == []

    def test_with_no_persona_id(self):
        """Sem persona_id (None ou string vazia) retorna vazio e aprovado."""
        mission_results = [{"sources": [{"document": "doc.md"}]}]
        res_none = run_post_mission_gates(None, mission_results)
        assert res_none == {"gates_run": [], "all_passed": True, "gate_results": []}

        res_empty = run_post_mission_gates("", mission_results)
        assert res_empty == {"gates_run": [], "all_passed": True, "gate_results": []}

    def test_with_unknown_persona_id(self):
        """Persona desconhecida retorna vazio e aprovado (backward compatible)."""
        mission_results = [{"sources": [{"document": "doc.md"}]}]
        result = run_post_mission_gates("persona-inexistente-123", mission_results)
        assert result == {"gates_run": [], "all_passed": True, "gate_results": []}

    def test_with_empty_mission_results(self):
        """Lista vazia de resultados passa com lista vazia de gate_results."""
        result = run_post_mission_gates("maia-orchestrator", [])
        assert result["gates_run"] == ["grounding_sha256"]
        assert result["all_passed"] is True
        assert result["gate_results"] == []


# ─── Testes de R9: Max Hops Enforcement ───

class TestMaxHopsEnforcement:
    """Testes de enforce max_hops no Orchestrator."""

    def setup_method(self):
        reset_all_singletons()

    def test_max_hops_truncation(self):
        """Quando o número de passos excede max_hops, trunca para max_hops e emite warning."""
        orch = Orchestrator(pace=0)

        five_steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "b1"},
            {"agent": "coder", "tool": "get_system_architecture", "input": {"system_name": "s1"}, "bubble": "b2"},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "b3"},
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q2"}, "bubble": "b4"},
            {"agent": "coder", "tool": "get_brain_status", "input": {}, "bubble": "b5"},
        ]

        # Criar contrato customizado para o manager com max_hops = 2
        custom_contract = PersonaContract(
            persona_id="maia-orchestrator",
            display_name="Maia",
            role="orchestrator",
            quality_gates=QualityGatesConfig(
                pre_mission=["dlp_input"],
                post_mission=[],
                max_hops=2,
            ),
        )

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        with mock.patch.object(orch, "_match_pattern", return_value=five_steps), \
             mock.patch("backend.orchestrator.get_persona_contract", return_value=custom_contract), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            events = asyncio.run(_collect_events(orch, "tarefa com 5 passos"))

        # Verifica se apenas 2 ferramentas foram executadas
        assert len(executed_tools) == 2
        assert executed_tools == ["search_knowledge_base", "get_system_architecture"]

        # Verifica se o evento de warning sobre truncamento foi emitido
        warning_events = [
            e for e in events
            if e["type"] == "message" and "truncada" in e["payload"].get("message", "").lower()
        ]
        assert len(warning_events) == 1
        assert "2 passos" in warning_events[0]["payload"]["message"]

    def test_max_hops_not_truncated_when_under_limit(self):
        """Quando o número de passos está dentro de max_hops, não há truncamento."""
        orch = Orchestrator(pace=0)

        two_steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "b1"},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "b2"},
        ]

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        with mock.patch.object(orch, "_match_pattern", return_value=two_steps), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            events = asyncio.run(_collect_events(orch, "tarefa de 2 passos"))

        assert len(executed_tools) == 2
        warning_events = [
            e for e in events
            if e["type"] == "message" and "truncada" in e["payload"].get("message", "").lower()
        ]
        assert len(warning_events) == 0

    def test_backward_compatibility_no_persona_no_truncation(self):
        """Sem persona associada ao manager, nenhum truncamento ocorre."""
        orch = Orchestrator(pace=0)

        five_steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": f"q{i}"}, "bubble": f"b{i}"}
            for i in range(5)
        ]

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        # Remove mapeamento da persona do manager
        with mock.patch.dict(AGENT_PERSONA_MAP, {"manager": None}, clear=False), \
             mock.patch.object(orch, "_match_pattern", return_value=five_steps), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            events = asyncio.run(_collect_events(orch, "tarefa sem persona"))

        assert len(executed_tools) == 5
        warning_events = [
            e for e in events
            if e["type"] == "message" and "truncada" in e["payload"].get("message", "").lower()
        ]
        assert len(warning_events) == 0


# ─── Testes de R9: TTL Enforcement ───

class TestTTLEnforcement:
    """Testes de enforcement de TTL no Orchestrator."""

    def setup_method(self):
        reset_all_singletons()

    def test_ttl_constant_defined(self):
        """MISSION_TTL_SECONDS deve ser 30."""
        assert MISSION_TTL_SECONDS == 30

    def test_ttl_exceeded_breaks_loop_and_emits_timeout_event(self):
        """Quando o tempo decorrido excede MISSION_TTL_SECONDS, interrompe o loop e emite timeout."""
        orch = Orchestrator(pace=0)

        three_steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "b1"},
            {"agent": "coder", "tool": "get_system_architecture", "input": {"system_name": "s1"}, "bubble": "b2"},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "b3"},
        ]

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        # Simular o relógio:
        # 1. mission_start = time.time() -> 1000.0
        # 2. _event timestamps -> 1000.0
        # 3. Step 0 check -> 1000.0 (elapsed = 0 <= 30) -> executa step 0
        # 4. Step 1 check -> 1035.0 (elapsed = 35 > 30) -> TIMEOUT!
        current_time = [1000.0]

        def fake_time():
            return current_time[0]

        with mock.patch.object(orch, "_match_pattern", return_value=three_steps), \
             mock.patch("backend.orchestrator.time.time", side_effect=fake_time), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            # Inicia o gerador
            gen = orch.run_mission("diagnosticar fila")

            async def run_with_advancing_clock():
                events = []
                async for evt in gen:
                    events.append(evt)
                    # Quando o primeiro step terminar (status done do researcher), avança o relógio além do TTL
                    if evt.get("type") == "status_change" and evt.get("agentId") == "researcher" and evt["payload"].get("status") == "done":
                        current_time[0] = 1000.0 + MISSION_TTL_SECONDS + 5  # 1035.0
                    # Auto-aprovação para Eva
                    if evt.get("type") == "approval_request":
                        orch.approve()
                return events

            events = asyncio.run(run_with_advancing_clock())

        # Apenas o primeiro passo foi executado; passos 2 e 3 foram cancelados pelo timeout
        assert len(executed_tools) == 1
        assert executed_tools == ["search_knowledge_base"]

        # Verifica evento de timeout
        timeout_events = [
            e for e in events
            if e["type"] == "message" and "timeout" in e["payload"].get("message", "").lower()
        ]
        assert len(timeout_events) >= 1
        assert any("TTL" in e["payload"]["message"] for e in timeout_events)


# ─── Testes de Soft Enforcement de Post-Mission Gates no Orchestrator ───

class TestOrchestratorPostMissionSoftEnforcement:
    """Testes da integração do Orchestrator com post-mission gates."""

    def setup_method(self):
        reset_all_singletons()

    def test_post_mission_gate_failure_emits_warning_without_blocking(self):
        """Falha nos post-mission gates emite evento de warning e NÃO bloqueia a missão."""
        orch = Orchestrator(pace=0)

        one_step = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "b1"},
        ]

        # Simula retorno com documento não existente (falha no grounding)
        async def fake_run_tool(tool, args, **kwargs):
            return {
                "tool": tool,
                "sources": [{"document": "adrs/ADR-999-inexistente.md", "score": 0.5}],
            }

        with mock.patch.object(orch, "_match_pattern", return_value=one_step), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            events = asyncio.run(_collect_events(orch, "tarefa com doc alucinado"))

        # Verifica se o evento de aviso de governança foi emitido
        gov_warning_events = [
            e for e in events
            if e["type"] == "message" and "aviso de governança" in e["payload"].get("message", "").lower()
        ]
        assert len(gov_warning_events) == 1
        assert "gate_1_grounding_citation" in gov_warning_events[0]["payload"]["message"]

        # Verifica que a missão NÃO foi bloqueada: chegou até o evento de completion
        completion_events = [e for e in events if e["type"] == "completion"]
        assert len(completion_events) == 1
        assert completion_events[0]["payload"].get("bubble") == "Missão concluída! 🎉"

    def test_post_mission_gate_pass_no_warning_emitted(self):
        """Post-mission gates aprovados não devem emitir warning."""
        orch = Orchestrator(pace=0)

        one_step = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "b1"},
        ]

        # Simula retorno com documento real do Vault
        async def fake_run_tool(tool, args, **kwargs):
            return {
                "tool": tool,
                "sources": [
                    {
                        "document": "adrs/ADR-006-implementacao-flowlogger-observabilidade-semaforos.md",
                        "score": 0.9,
                    }
                ],
            }

        with mock.patch.object(orch, "_match_pattern", return_value=one_step), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            events = asyncio.run(_collect_events(orch, "tarefa com doc real"))

        # Não deve haver aviso de governança
        gov_warning_events = [
            e for e in events
            if e["type"] == "message" and "aviso de governança" in e["payload"].get("message", "").lower()
        ]
        assert len(gov_warning_events) == 0

        # Conclusão bem-sucedida
        completion_events = [e for e in events if e["type"] == "completion"]
        assert len(completion_events) == 1

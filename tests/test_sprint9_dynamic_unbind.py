"""Testes do Sprint 9: R10 — Dynamic Tool Unbind when Circuit Breaker Opens.

Cobre:
- get_unbound_tools() retorna lista vazia quando nenhum CB está aberto
- get_unbound_tools() retorna nome da tool quando CB está OPEN
- get_unbound_tools() com múltiplos breakers em estados diferentes (CLOSED, OPEN)
- unbind_open_circuit_tools() sem circuitos abertos (passthrough)
- unbind_open_circuit_tools() remove steps com CB aberto
- unbind_open_circuit_tools() preserva steps com CB fechado
- Fallback step possui _original_tool, _unbound_reason, tool=None e bubble customizada
- unbind_open_circuit_tools() com lista vazia de steps
- Orchestrator lida com passos com tool=None de forma graciosa (pace=0)
- Fluxo completo de missão com tool desvinculada emite evento de aviso do manager
- Fluxo completo sem tools desvinculadas não emite aviso de unbind
- Backward compatibility quando nenhum CB existe no registry
"""
import asyncio
from unittest import mock
import pytest

from backend.orchestrator import Orchestrator, AGENT_PERSONA_MAP
from core.integration import (
    _get_cb_registry,
    get_unbound_tools,
    unbind_open_circuit_tools,
    reset_all_singletons,
)
from core.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitState


# ─── Utilitários de Teste ───

async def _collect_events(orchestrator: Orchestrator, task: str) -> list:
    """Coleta todos os eventos de run_mission com auto-aprovação em background."""
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


# ─── Testes de get_unbound_tools ───

class TestGetUnboundTools:
    """Testes unitários para get_unbound_tools()."""

    def setup_method(self):
        reset_all_singletons()

    def test_get_unbound_tools_empty_when_no_cb_exists(self):
        """Quando nenhum CB foi registrado, retorna lista vazia."""
        unbound = get_unbound_tools()
        assert unbound == []

    def test_get_unbound_tools_empty_when_all_circuits_closed(self):
        """Quando existem CBs mas todos estão CLOSED, retorna lista vazia."""
        registry = _get_cb_registry()
        cb = registry.get("search_knowledge_base")
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

        unbound = get_unbound_tools()
        assert unbound == []

    def test_get_unbound_tools_returns_tool_when_cb_open(self):
        """Quando um CB atinge o threshold de falhas e abre, retorna seu nome."""
        registry = _get_cb_registry()
        cb = registry.get("search_knowledge_base")
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        unbound = get_unbound_tools()
        assert unbound == ["search_knowledge_base"]

    def test_get_unbound_tools_multiple_breakers_mixed_states(self):
        """Retorna apenas as tools cujo CB está em OPEN."""
        registry = _get_cb_registry()
        cb1 = registry.get("tool_a")
        cb2 = registry.get("tool_b")
        cb3 = registry.get("tool_c")

        # tool_a abre (3 falhas)
        for _ in range(3):
            cb1.record_failure()

        # tool_b permanece fechada (sucessos e 1 falha < threshold)
        cb2.record_success()
        cb2.record_failure()

        # tool_c abre (3 falhas)
        for _ in range(3):
            cb3.record_failure()

        assert cb1.state == CircuitState.OPEN
        assert cb2.state == CircuitState.CLOSED
        assert cb3.state == CircuitState.OPEN

        unbound = get_unbound_tools()
        assert set(unbound) == {"tool_a", "tool_c"}


# ─── Testes de unbind_open_circuit_tools ───

class TestUnbindOpenCircuitTools:
    """Testes unitários para unbind_open_circuit_tools()."""

    def setup_method(self):
        reset_all_singletons()

    def test_passthrough_when_no_open_circuits(self):
        """Sem CBs abertos, steps são retornados inalterados e removed é vazio."""
        steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "b1"},
            {"agent": "coder", "tool": "get_system_architecture", "input": {}, "bubble": "b2"},
        ]
        filtered_steps, removed = unbind_open_circuit_tools(steps)
        assert filtered_steps == steps
        assert removed == []

    def test_passthrough_when_steps_empty(self):
        """Com lista vazia de steps, retorna ([], [])."""
        filtered_steps, removed = unbind_open_circuit_tools([])
        assert filtered_steps == []
        assert removed == []

    def test_removes_step_with_open_cb(self):
        """Step com tool em OPEN é desvinculado e seu nome incluído em removed."""
        registry = _get_cb_registry()
        cb = registry.get("search_knowledge_base")
        for _ in range(3):
            cb.record_failure()

        steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "Pesquisando..."},
        ]
        filtered_steps, removed = unbind_open_circuit_tools(steps)

        assert removed == ["search_knowledge_base"]
        assert len(filtered_steps) == 1
        assert filtered_steps[0]["tool"] is None

    def test_preserves_steps_with_closed_cb(self):
        """Steps com ferramentas sem circuito aberto são mantidos intactos."""
        registry = _get_cb_registry()
        cb = registry.get("search_knowledge_base")
        for _ in range(3):
            cb.record_failure()

        steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}, "bubble": "Pesquisando..."},
            {"agent": "coder", "tool": "get_system_architecture", "input": {}, "bubble": "Arquitetura..."},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "Regras..."},
        ]
        filtered_steps, removed = unbind_open_circuit_tools(steps)

        assert removed == ["search_knowledge_base"]
        assert len(filtered_steps) == 3

        # Step 0 foi desvinculado
        assert filtered_steps[0]["tool"] is None

        # Steps 1 e 2 preservados
        assert filtered_steps[1]["tool"] == "get_system_architecture"
        assert filtered_steps[1]["bubble"] == "Arquitetura..."
        assert filtered_steps[2]["tool"] == "list_rules"
        assert filtered_steps[2]["bubble"] == "Regras..."

    def test_fallback_step_metadata_and_attributes(self):
        """Verifica se o fallback step possui os metadados esperados."""
        registry = _get_cb_registry()
        cb = registry.get("search_knowledge_base")
        for _ in range(3):
            cb.record_failure()

        original_step = {
            "agent": "researcher",
            "tool": "search_knowledge_base",
            "input": {"query": "teste"},
            "bubble": "Pesquisando...",
        }
        filtered_steps, removed = unbind_open_circuit_tools([original_step])

        assert len(filtered_steps) == 1
        step = filtered_steps[0]

        assert step["tool"] is None
        assert step["_original_tool"] == "search_knowledge_base"
        assert step["_unbound_reason"] == "circuit_breaker_open"
        assert step["bubble"] == "⚡ search_knowledge_base indisponível (circuit breaker aberto)"
        assert step["agent"] == "researcher"
        assert step["input"] == {"query": "teste"}

    def test_backward_compatibility_no_cbs_exist(self):
        """Garante compatibilidade quando o registry nunca foi inicializado."""
        reset_all_singletons()
        steps = [
            {"agent": "coder", "tool": "custom_tool", "input": {}},
        ]
        filtered_steps, removed = unbind_open_circuit_tools(steps)
        assert filtered_steps == steps
        assert removed == []

    def test_multiple_occurrences_of_unbound_tool(self):
        """Se a mesma tool com CB aberto aparecer em múltiplos passos, todos são desvinculados."""
        registry = _get_cb_registry()
        cb = registry.get("search_knowledge_base")
        for _ in range(3):
            cb.record_failure()

        steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "q1"}},
            {"agent": "reviewer", "tool": "search_knowledge_base", "input": {"query": "q2"}},
        ]
        filtered_steps, removed = unbind_open_circuit_tools(steps)
        assert removed == ["search_knowledge_base", "search_knowledge_base"]
        assert all(s["tool"] is None for s in filtered_steps)
        assert all(s["_original_tool"] == "search_knowledge_base" for s in filtered_steps)


# ─── Testes do Orchestrator com Dynamic Unbind ───

class TestOrchestratorDynamicUnbind:
    """Testes de integração do Orchestrator com Dynamic Unbind."""

    def setup_method(self):
        reset_all_singletons()

    def test_orchestrator_handles_none_tool_steps_gracefully(self):
        """Orchestrator executa step com tool=None emitindo fallback sem chamar run_tool."""
        orch = Orchestrator(pace=0)

        unbound_step = {
            "agent": "researcher",
            "tool": None,
            "_original_tool": "search_knowledge_base",
            "_unbound_reason": "circuit_breaker_open",
            "bubble": "⚡ search_knowledge_base indisponível (circuit breaker aberto)",
            "input": {},
        }
        normal_step = {
            "agent": "reviewer",
            "tool": "list_rules",
            "bubble": "Verificando regras...",
            "input": {},
        }

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        with mock.patch("backend.orchestrator.check_mission", return_value={"action": "proceed", "semaphore": "GREEN"}), \
             mock.patch.object(orch, "_match_pattern", return_value=[unbound_step, normal_step]), \
             mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):

            events = asyncio.run(_collect_events(orch, "tarefa com step unbound"))

        # run_tool só deve ter sido chamado para a tool válida
        assert executed_tools == ["list_rules"]
        assert "search_knowledge_base" not in executed_tools

        # researcher deve ter emitido mensagem de fallback
        researcher_messages = [
            e for e in events
            if e["type"] == "message" and e.get("agentId") == "researcher"
        ]
        assert len(researcher_messages) == 1
        assert "⚡ search_knowledge_base indisponível" in researcher_messages[0]["payload"]["message"]

        # researcher deve ter transicionado para done
        researcher_done = [
            e for e in events
            if e["type"] == "status_change" and e.get("agentId") == "researcher" and e["payload"].get("status") == "done"
        ]
        assert len(researcher_done) >= 1

    def test_full_mission_flow_with_one_tool_unbound_emits_warning_event(self):
        """Fluxo completo de missão: com CB aberto, manager emite aviso de dynamic unbind."""
        # Abre o CB para search_knowledge_base
        cb = _get_cb_registry().get("search_knowledge_base")
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        orch = Orchestrator(pace=0)

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        with mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):
            # 'diagnosticar' mapeia para 3 passos: search_knowledge_base, get_system_architecture, list_rules
            events = asyncio.run(_collect_events(orch, "diagnosticar erro no hub"))

        # Verifica se o evento de unbind foi emitido pelo manager
        unbind_events = [
            e for e in events
            if e["type"] == "message"
            and e.get("agentId") == "manager"
            and "Dynamic unbind" in e["payload"].get("message", "")
        ]
        assert len(unbind_events) == 1
        msg = unbind_events[0]["payload"]["message"]
        bubble = unbind_events[0]["payload"]["bubble"]
        assert "search_knowledge_base" in msg
        assert "circuit breaker aberto" in msg
        assert "1 tool(s) desvinculada(s)" in bubble

        # search_knowledge_base NÃO deve ter sido executada via run_tool
        assert "search_knowledge_base" not in executed_tools
        assert "get_system_architecture" in executed_tools
        assert "list_rules" in executed_tools

    def test_full_mission_flow_all_circuits_closed_no_warning_event(self):
        """Quando nenhum CB está aberto, a missão roda normalmente sem avisos de unbind."""
        orch = Orchestrator(pace=0)

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        with mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):
            events = asyncio.run(_collect_events(orch, "diagnosticar erro no hub"))

        # Nenhum evento de dynamic unbind
        unbind_events = [
            e for e in events
            if e["type"] == "message"
            and e.get("agentId") == "manager"
            and "Dynamic unbind" in e["payload"].get("message", "")
        ]
        assert len(unbind_events) == 0

        # Todas as ferramentas foram executadas
        assert "search_knowledge_base" in executed_tools
        assert "get_system_architecture" in executed_tools
        assert "list_rules" in executed_tools

    def test_backward_compatibility_when_no_cbs_exist(self):
        """Missão roda perfeitamente sem breakers no registry."""
        reset_all_singletons()
        orch = Orchestrator(pace=0)

        executed_tools = []

        async def fake_run_tool(tool, args, **kwargs):
            executed_tools.append(tool)
            return {"tool": tool, "success": True}

        with mock.patch("backend.orchestrator.run_tool", side_effect=fake_run_tool):
            events = asyncio.run(_collect_events(orch, "playbook de deploy"))

        # Evento de completion completado com sucesso
        completion_events = [
            e for e in events
            if e["type"] == "completion" and e.get("agentId") == "manager"
        ]
        assert len(completion_events) == 1
        assert len(executed_tools) > 0

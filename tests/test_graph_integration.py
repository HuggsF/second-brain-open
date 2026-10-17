"""Integration tests for core.graph/ — full graph traversal with mocked infra.

Run:  C:\\Python314\\python.exe -m pytest tests/test_graph_integration.py -v

These tests use the REAL ``build_graph()`` factory and ``run_graph()`` runner
but mock all external dependencies (broker, mission_guard, MoE router,
integration module) so they run offline without Qdrant, MCP servers, etc.

Coverage:
  - Happy path: plan → gate(GREEN) → route → execute → validate → post_gate → END
  - Gate blocked: plan → gate(RED) → END(failed)
  - HITL suspend + resume: plan → gate(YELLOW) → suspend → resume → route → ...
  - Correction loop: validate fail → correct → retry → validate → pass
  - Circuit breaker: correction loop exhausts attempts → END(circuit_broken)
  - Multi-step: 3 steps executed sequentially
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.graph import END, Graph, GraphEdge, GraphNode
from core.graph.edges import build_graph
from core.graph.runner import run_graph
from core.state import GraphState, create_initial_state


# ═══════════════════════════════════════════════════════════════════════
# Mock infrastructure
# ═══════════════════════════════════════════════════════════════════════


# -- Mock for backend.orchestrator module (lazy import in plan_node) --
MOCK_PATTERNS = [
    {
        "keywords": ["test", "deploy"],
        "steps": [
            {"tool": "search_knowledge_base", "agent": "researcher", "input": {}},
        ],
    },
]
MOCK_DEFAULT_STEPS = [
    {"tool": "search_knowledge_base", "agent": "researcher", "input": {"query": ""}},
]
MOCK_AGENT_MAP = {"manager": "test-manager"}

_mock_orchestrator = MagicMock(
    MISSION_PATTERNS=MOCK_PATTERNS,
    DEFAULT_STEPS=MOCK_DEFAULT_STEPS,
    AGENT_PERSONA_MAP=MOCK_AGENT_MAP,
)


# -- Mock for RoutingDecision (returned by MoERouter.route) --
@dataclass
class _MockRoutingDecision:
    selected_persona: str = "researcher"
    confidence_score: float = 0.1  # below threshold → no rerouting
    matched_tags: list = field(default_factory=list)
    is_fallback: bool = True
    method: str = "mock"


class _MockMoERouter:
    """Mock MoE router that returns low-confidence fallback decisions."""

    def __init__(self, **kwargs):
        pass

    def route(self, mission_text: str) -> _MockRoutingDecision:
        return _MockRoutingDecision()


# -- Helpers --

def _make_state(**overrides: Any) -> GraphState:
    """Create a minimal GraphState with task metadata."""
    s = create_initial_state(trace_id="b" * 32, max_attempts=3)
    s["metadata"] = {
        "task_text": "test deploy application",
        "mission_id": 42,
        **(overrides.pop("metadata", {})),
    }
    s.update(overrides)
    return s


def _gate_green(*args, **kwargs):
    """check_mission mock → GREEN semaphore."""
    return {"action": "proceed", "semaphore": "GREEN", "gate_results": []}


def _gate_red(*args, **kwargs):
    """check_mission mock → RED semaphore (blocked)."""
    return {"action": "block", "semaphore": "RED", "gate_results": [{"gate": "dag", "passed": False}]}


def _gate_yellow(*args, **kwargs):
    """check_mission mock → YELLOW semaphore (approval required)."""
    return {"action": "approval", "semaphore": "YELLOW", "gate_results": []}


def _unbind_passthrough(steps, persona_id=None):
    """unbind_open_circuit_tools mock → no changes."""
    return steps, []


def _post_gates_ok(persona_id, mission_results):
    """run_post_mission_gates mock → all passed."""
    return {"gates_run": ["grounding_sha256"], "all_passed": True, "gate_results": []}


def _post_gates_warn(persona_id, mission_results):
    """run_post_mission_gates mock → some failed (but doesn't block)."""
    return {"gates_run": ["grounding_sha256"], "all_passed": False, "gate_results": [{"passed": False}]}


async def _broker_success(identity, tool, args, task_id=None, **kwargs):
    """broker.call mock → successful execution."""
    return {"data": "mock_result", "status": "ok"}


async def _broker_refused(identity, tool, args, task_id=None, **kwargs):
    """broker.call mock → policy denial."""
    return {"refused": True, "error": "policy denied", "approval_required": False}


async def _broker_error_once():
    """Factory that returns a broker mock that fails once then succeeds."""
    call_count = 0

    async def _call(identity, tool, args, task_id=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"error": True, "reason": "transient failure", "agent": "a", "tool": tool}
        return {"data": "recovered", "status": "ok"}

    return _call


# ═══════════════════════════════════════════════════════════════════════
# Context managers for patching all lazy imports
# ═══════════════════════════════════════════════════════════════════════


import contextlib
import sys
from unittest.mock import patch as _patch


@contextlib.contextmanager
def _patch_graph_infra(
    *,
    check_mission=_gate_green,
    broker_call=_broker_success,
    make_identity=lambda role, **kw: f"identity:{role}",
    unbind_tools=_unbind_passthrough,
    post_gates=_post_gates_ok,
    get_persona_contract=lambda pid: None,
    router_class=_MockMoERouter,
    orchestrator_module=None,
):
    """Patch all external dependencies used by graph nodes via lazy imports.

    Strategy: inject mock modules into ``sys.modules`` so that ``from X import Y``
    inside node function bodies resolves to our mocks WITHOUT triggering the real
    module's import chain (which would pull in qdrant, numpy, etc.).

    We preserve any pre-existing modules and restore them on exit.
    """
    # -- Build mock modules --

    # core.broker: execute_node does `from core.broker import call`
    mock_broker = MagicMock()
    mock_broker.call = AsyncMock(side_effect=broker_call)

    # core.policy: execute_node does `from core.policy import make_identity`
    mock_policy = MagicMock()
    mock_policy.make_identity = make_identity
    # Prevent `from core.policy.autonomy import ...` from failing
    mock_policy_autonomy = MagicMock()

    # core.mission_guard: gate_node does `from core.mission_guard import check_mission`
    mock_mission_guard = MagicMock()
    mock_mission_guard.check_mission = check_mission

    # core.integration: plan_node, route_node, post_gate_node use lazy imports
    mock_integration = MagicMock()
    mock_integration.get_persona_contract = get_persona_contract
    mock_integration.unbind_open_circuit_tools = unbind_tools
    mock_integration.run_post_mission_gates = post_gates

    # core.routing.moe_router: route_node does `from core.routing.moe_router import MoERouter`
    mock_moe_module = MagicMock()
    mock_moe_module.MoERouter = router_class

    # backend.orchestrator: plan_node does `from backend.orchestrator import ...`
    orch = orchestrator_module if orchestrator_module is not None else _mock_orchestrator

    # -- Collect modules to inject --
    injected = {
        "backend.orchestrator": orch,
        "core.broker": mock_broker,
        "core.policy": mock_policy,
        "core.policy.autonomy": mock_policy_autonomy,
        "core.mission_guard": mock_mission_guard,
        "core.integration": mock_integration,
        "core.routing.moe_router": mock_moe_module,
    }

    # Save originals so we can restore them
    saved = {k: sys.modules.get(k) for k in injected}

    try:
        sys.modules.update(injected)
        yield
    finally:
        for key, original in saved.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original


# ═══════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """Full happy path: plan → gate(GREEN) → route → execute → validate → post_gate → END."""

    @pytest.mark.asyncio
    async def test_single_step_completes(self):
        """Single step mission completes successfully."""
        graph = build_graph()
        state = _make_state()

        with _patch_graph_infra():
            result = await run_graph(graph, state)

        assert result["status"] == "completed"
        assert len(result["node_history"]) >= 5  # plan, gate, route, execute, validate, post_gate
        assert "plan_node" in result["node_history"]
        assert "post_gate_node" in result["node_history"]
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_metadata_populated(self):
        """After happy path, metadata has steps, step_results, gate_result, post_gate_result."""
        graph = build_graph()
        state = _make_state()

        with _patch_graph_infra():
            result = await run_graph(graph, state)

        meta = result["metadata"]
        assert "steps" in meta
        assert "step_results" in meta
        assert len(meta["step_results"]) == len(meta["steps"])
        assert "gate_result" in meta
        assert meta["gate_result"]["action"] == "proceed"
        assert "post_gate_result" in meta
        assert meta["post_gate_result"]["all_passed"] is True

    @pytest.mark.asyncio
    async def test_node_history_order(self):
        """Nodes are visited in the correct order."""
        graph = build_graph()
        state = _make_state()

        with _patch_graph_infra():
            result = await run_graph(graph, state)

        history = result["node_history"]
        # plan → gate → route → execute → validate → post_gate
        assert history[0] == "plan_node"
        assert history[1] == "gate_node"
        assert history[2] == "route_node"
        assert history[3] == "execute_node"
        assert history[4] == "validate_node"
        assert history[-1] == "post_gate_node"

    @pytest.mark.asyncio
    async def test_event_callback_receives_events(self):
        """on_event callback receives lifecycle events during full run."""
        graph = build_graph()
        events: list[dict] = []

        async def _collect(event):
            events.append(event)

        with _patch_graph_infra():
            result = await run_graph(graph, _make_state(), on_event=_collect)

        assert result["status"] == "completed"
        event_types = [e["type"] for e in events]
        assert "node_start" in event_types
        assert "node_end" in event_types
        assert "edge_taken" in event_types
        assert "graph_end" in event_types


class TestGateBlocked:
    """Gate blocked: plan → gate(RED) → END(failed)."""

    @pytest.mark.asyncio
    async def test_red_semaphore_blocks(self):
        """RED semaphore results in status=failed, stops at gate_node."""
        graph = build_graph()
        state = _make_state()

        with _patch_graph_infra(check_mission=_gate_red):
            result = await run_graph(graph, state)

        assert result["status"] == "failed"
        assert "gate_node" in result["node_history"]
        # Should NOT have reached execute_node or post_gate_node
        assert "execute_node" not in result["node_history"]
        assert "post_gate_node" not in result["node_history"]

    @pytest.mark.asyncio
    async def test_gate_result_stored(self):
        """Gate result is stored in metadata even when blocked."""
        graph = build_graph()

        with _patch_graph_infra(check_mission=_gate_red):
            result = await run_graph(graph, _make_state())

        meta = result["metadata"]
        assert meta["gate_result"]["action"] == "block"
        assert meta["gate_result"]["semaphore"] == "RED"


class TestHITL:
    """HITL: gate(YELLOW) → suspend → resume → route → ... → END."""

    @pytest.mark.asyncio
    async def test_yellow_semaphore_suspends(self):
        """YELLOW semaphore suspends execution for human approval."""
        graph = build_graph()

        with _patch_graph_infra(check_mission=_gate_yellow):
            result = await run_graph(graph, _make_state())

        assert result["status"] == "awaiting_approval"
        assert result["metadata"]["_suspended_at"] == "gate_node"
        assert result["metadata"]["needs_approval"] is True

    @pytest.mark.asyncio
    async def test_resume_after_approval_completes(self):
        """After approval, resume from gate_node continues to completion."""
        graph = build_graph()

        # Phase 1: Suspend
        with _patch_graph_infra(check_mission=_gate_yellow):
            suspended = await run_graph(graph, _make_state())

        assert suspended["status"] == "awaiting_approval"

        # Phase 2: Resume — gate_node edges are re-evaluated.
        # After approval, needs_approval should be cleared.
        # The resumed state still has needs_approval=True from gate_node,
        # but the runner skips re-execution and evaluates edges.
        # Since status is NOT "failed", _gate_blocked returns False,
        # so the edge goes to route_node.
        resumed_state = {
            **suspended,
            "status": "running",  # caller resets status
            "metadata": {
                **suspended["metadata"],
                "needs_approval": False,  # caller clears after approval
            },
        }

        graph2 = build_graph()  # fresh graph (nodes haven't been executed)
        with _patch_graph_infra():
            result = await run_graph(
                graph2, resumed_state,
                resume_from="gate_node",
            )

        assert result["status"] == "completed"
        assert "post_gate_node" in result["node_history"]


class TestCorrectionLoop:
    """Correction loop: validate fail → correct → retry → validate pass."""

    @pytest.mark.asyncio
    async def test_transient_failure_retried_and_recovers(self):
        """First broker call fails, correct_node retries, second call succeeds."""
        graph = build_graph()
        broker_fn = await _broker_error_once()

        with _patch_graph_infra(broker_call=broker_fn):
            result = await run_graph(graph, _make_state())

        assert result["status"] == "completed"
        # Should have visited correct_node (retry loop)
        assert "correct_node" in result["node_history"]
        # Attempt should have been incremented
        assert result["current_attempt"] >= 2


class TestCircuitBreaker:
    """Circuit breaker: correction loop exhausts attempts → END(circuit_broken)."""

    @pytest.mark.asyncio
    async def test_persistent_failure_trips_cb(self):
        """Broker always refuses → correction loop exhausts attempts → circuit_broken."""
        graph = build_graph()
        state = _make_state(max_attempts=2)  # low threshold for fast test

        with _patch_graph_infra(broker_call=_broker_refused):
            result = await run_graph(graph, state)

        assert result["status"] == "circuit_broken"
        assert "correct_node" in result["node_history"]
        # current_attempt should exceed max_attempts
        assert result["current_attempt"] > result["max_attempts"]

    @pytest.mark.asyncio
    async def test_cb_preserves_errors(self):
        """Errors from each attempt are preserved in the final state."""
        graph = build_graph()
        state = _make_state(max_attempts=2)

        with _patch_graph_infra(broker_call=_broker_refused):
            result = await run_graph(graph, state)

        assert len(result["errors"]) >= 1
        error_types = [e.error_type for e in result["errors"]]
        assert "PolicyDenial" in error_types


class TestMultiStep:
    """Multi-step mission: 3 steps executed sequentially."""

    @pytest.mark.asyncio
    async def test_three_steps_all_execute(self):
        """Mission with 3 steps executes all of them."""
        multi_step_patterns = [
            {
                "keywords": ["test", "deploy"],
                "steps": [
                    {"tool": "tool_1", "agent": "agent_1", "input": {}},
                    {"tool": "tool_2", "agent": "agent_2", "input": {}},
                    {"tool": "tool_3", "agent": "agent_3", "input": {}},
                ],
            },
        ]
        mock_orch = MagicMock(
            MISSION_PATTERNS=multi_step_patterns,
            DEFAULT_STEPS=MOCK_DEFAULT_STEPS,
            AGENT_PERSONA_MAP=MOCK_AGENT_MAP,
        )

        graph = build_graph()

        with _patch_graph_infra(orchestrator_module=mock_orch):
            result = await run_graph(graph, _make_state())

        assert result["status"] == "completed"
        meta = result["metadata"]
        assert len(meta["step_results"]) == 3
        assert meta["current_step_index"] == 3

        # execute_node should appear 3 times in history
        exec_visits = [n for n in result["node_history"] if n == "execute_node"]
        assert len(exec_visits) == 3

        # validate_node should also appear 3 times
        val_visits = [n for n in result["node_history"] if n == "validate_node"]
        assert len(val_visits) == 3


class TestPostGateWarning:
    """Post-mission gate warnings don't block completion."""

    @pytest.mark.asyncio
    async def test_failed_post_gate_still_completes(self):
        """Failed post-mission gates produce warnings but status=completed."""
        graph = build_graph()

        with _patch_graph_infra(post_gates=_post_gates_warn):
            result = await run_graph(graph, _make_state())

        assert result["status"] == "completed"
        meta = result["metadata"]
        assert meta["post_gate_result"]["all_passed"] is False
        # A warning message should be added
        assert any("gates warning" in m.content.lower() for m in result["messages"])


class TestInstrumentedIntegration:
    """Integration with telemetry wrapper."""

    @pytest.mark.asyncio
    async def test_instrumented_run_graph_happy_path(self):
        """instrumented_run_graph produces trace records during full run."""
        from core.graph.telemetry import instrumented_run_graph

        class _FakeTraceWriter:
            def __init__(self):
                self.records = []

            def write(self, record, path=None):
                self.records.append(record)

        class _FakeContainer:
            def __init__(self):
                self.trace_writer = _FakeTraceWriter()

        graph = build_graph()
        container = _FakeContainer()

        with _patch_graph_infra():
            result = await instrumented_run_graph(
                graph, _make_state(),
                container=container,
            )

        assert result["status"] == "completed"
        # Should have trace records for each node (start + end)
        assert len(container.trace_writer.records) >= 10  # 5+ nodes × 2 + summary
        # Verify trace record structure
        events = [r["event"] for r in container.trace_writer.records]
        assert any("plan_node" in e for e in events)
        assert any("post_gate_node" in e for e in events)

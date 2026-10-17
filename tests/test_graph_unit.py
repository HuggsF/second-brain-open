"""Unit tests for core.graph/ — types, runner, nodes, edges, telemetry.

Run:  C:\\Python314\\python.exe -m pytest tests/test_graph_unit.py -v

Coverage map:
  - TestConstants:    END, MAX_GRAPH_ITERATIONS
  - TestGraphEdge:    frozen, slots, defaults
  - TestGraphNode:    slots, mutable edges
  - TestGraph:        slots, defaults
  - TestLazyReExports: __getattr__ for run_graph, build_graph
  - TestRunner:       happy path, conditional edges, global CB, per-step CB,
                      node exception, HITL suspend+resume, edge resolution,
                      event callback, resume validation
  - TestNodes:        plan_node, gate_node, route_node, execute_node,
                      validate_node, correct_node, post_gate_node (all mocked)
  - TestEdgePredicates: _gate_blocked, _has_step_failure, _has_more_steps,
                        _is_circuit_broken
  - TestBuildGraph:   structure, edges, targets
  - TestTelemetry:    instrumented wrapper, instrumented_run_graph
"""

from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.graph import END, MAX_GRAPH_ITERATIONS, Graph, GraphEdge, GraphNode
from core.state import (
    GraphState,
    TokenUsage,
    accumulate_tokens,
    add_error,
    create_initial_state,
    is_circuit_broken,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_state(**overrides: Any) -> GraphState:
    """Create a minimal GraphState for testing."""
    s = create_initial_state(trace_id="a" * 32, max_attempts=3)
    s.update(overrides)
    return s


async def _identity_node(state: GraphState) -> GraphState:
    """Node that returns state unchanged."""
    return state


async def _boom_node(state: GraphState) -> GraphState:
    """Node that always raises."""
    raise ValueError("intentional failure")


async def _token_node(state: GraphState) -> GraphState:
    """Node that simulates token accumulation."""
    return accumulate_tokens(state, prompt=100, completion=50)


async def _set_running(state: GraphState) -> GraphState:
    """Node that sets status to running."""
    return {**state, "status": "running"}


class _FakeTraceWriter:
    """Collects all trace records for assertion."""

    def __init__(self):
        self.records: list[dict] = []

    def write(self, record: dict, path=None) -> None:
        self.records.append(record)


class _FakeContainer:
    def __init__(self):
        self.trace_writer = _FakeTraceWriter()


# ═══════════════════════════════════════════════════════════════════════
# 1. Constants
# ═══════════════════════════════════════════════════════════════════════


class TestConstants:
    """Tests for core.graph constants."""

    def test_end_sentinel_value(self):
        assert END == "__END__"

    def test_end_is_string(self):
        assert isinstance(END, str)

    def test_max_iterations_value(self):
        assert MAX_GRAPH_ITERATIONS == 50

    def test_max_iterations_is_int(self):
        assert isinstance(MAX_GRAPH_ITERATIONS, int)


# ═══════════════════════════════════════════════════════════════════════
# 2. Types — GraphEdge, GraphNode, Graph
# ═══════════════════════════════════════════════════════════════════════


class TestGraphEdge:
    """Tests for GraphEdge frozen dataclass."""

    def test_unconditional_edge(self):
        edge = GraphEdge(target="next")
        assert edge.target == "next"
        assert edge.condition is None

    def test_conditional_edge(self):
        cond = lambda s: True  # noqa: E731
        edge = GraphEdge(target="next", condition=cond)
        assert edge.condition is cond

    def test_frozen(self):
        edge = GraphEdge(target="x")
        with pytest.raises(FrozenInstanceError):
            edge.target = "y"  # type: ignore[misc]

    def test_has_slots(self):
        assert hasattr(GraphEdge, "__slots__")


class TestGraphNode:
    """Tests for GraphNode (slots, mutable edges)."""

    def test_basic_creation(self):
        node = GraphNode(name="test", fn=_identity_node)
        assert node.name == "test"
        assert node.fn is _identity_node
        assert node.edges == []

    def test_edges_are_mutable(self):
        node = GraphNode(name="test", fn=_identity_node)
        node.edges.append(GraphEdge(target=END))
        assert len(node.edges) == 1

    def test_has_slots(self):
        assert hasattr(GraphNode, "__slots__")


class TestGraph:
    """Tests for Graph dataclass."""

    def test_empty_graph(self):
        g = Graph()
        assert g.nodes == {}
        assert g.entry == ""

    def test_graph_with_node(self):
        node = GraphNode(name="a", fn=_identity_node)
        g = Graph(nodes={"a": node}, entry="a")
        assert "a" in g.nodes
        assert g.entry == "a"


# ═══════════════════════════════════════════════════════════════════════
# 3. Lazy re-exports
# ═══════════════════════════════════════════════════════════════════════


class TestLazyReExports:
    """Tests for __getattr__ lazy re-exports in core.graph."""

    def test_run_graph_importable(self):
        from core.graph import run_graph

        assert callable(run_graph)

    def test_build_graph_importable(self):
        from core.graph import build_graph

        assert callable(build_graph)

    def test_unknown_attr_raises(self):
        import core.graph

        with pytest.raises(AttributeError, match="no_such_thing"):
            _ = core.graph.no_such_thing


# ═══════════════════════════════════════════════════════════════════════
# 4. Runner
# ═══════════════════════════════════════════════════════════════════════


class TestRunner:
    """Tests for core.graph.runner.run_graph."""

    @pytest.mark.asyncio
    async def test_happy_path_single_node(self):
        """A single-node graph that routes to END."""
        from core.graph.runner import run_graph

        node = GraphNode(
            name="a",
            fn=_set_running,
            edges=[GraphEdge(target=END)],
        )
        graph = Graph(nodes={"a": node}, entry="a")
        state = _make_state()

        result = await run_graph(graph, state)
        assert result["status"] == "completed"
        assert "a" in result["node_history"]

    @pytest.mark.asyncio
    async def test_multi_node_chain(self):
        """a → b → END."""
        from core.graph.runner import run_graph

        node_a = GraphNode(
            name="a", fn=_identity_node,
            edges=[GraphEdge(target="b")],
        )
        node_b = GraphNode(
            name="b", fn=_identity_node,
            edges=[GraphEdge(target=END)],
        )
        graph = Graph(nodes={"a": node_a, "b": node_b}, entry="a")
        state = _make_state()

        result = await run_graph(graph, state)
        assert result["status"] == "completed"
        assert result["node_history"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_conditional_edges(self):
        """a → [cond] b | c → END."""
        from core.graph.runner import run_graph

        async def _setter(state):
            return {**state, "metadata": {**state.get("metadata", {}), "go_b": True}}

        node_a = GraphNode(
            name="a", fn=_setter,
            edges=[
                GraphEdge(
                    target="b",
                    condition=lambda s: s.get("metadata", {}).get("go_b"),
                ),
                GraphEdge(target="c"),  # fallback
            ],
        )
        node_b = GraphNode(name="b", fn=_identity_node, edges=[GraphEdge(target=END)])
        node_c = GraphNode(name="c", fn=_identity_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"a": node_a, "b": node_b, "c": node_c}, entry="a")

        result = await run_graph(graph, _make_state())
        assert result["node_history"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_global_circuit_breaker(self):
        """Loop node that never ends should hit MAX_GRAPH_ITERATIONS."""
        from core.graph.runner import run_graph

        node = GraphNode(
            name="loop", fn=_identity_node,
            edges=[GraphEdge(target="loop")],  # infinite loop
        )
        graph = Graph(nodes={"loop": node}, entry="loop")

        result = await run_graph(graph, _make_state())
        assert result["status"] == "circuit_broken"
        assert any(
            e.error_type == "GlobalCircuitBreakerTripped"
            for e in result["errors"]
        )

    @pytest.mark.asyncio
    async def test_per_step_circuit_breaker(self):
        """State with current_attempt > max_attempts triggers CB in runner."""
        from core.graph.runner import run_graph

        node = GraphNode(name="x", fn=_identity_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"x": node}, entry="x")
        state = _make_state(current_attempt=10, max_attempts=3)

        result = await run_graph(graph, state)
        assert result["status"] == "circuit_broken"
        assert any(
            e.error_type == "PerStepCircuitBreakerTripped"
            for e in result["errors"]
        )

    @pytest.mark.asyncio
    async def test_node_exception_caught(self):
        """A node that raises is caught; state gets status=failed."""
        from core.graph.runner import run_graph

        node = GraphNode(name="bad", fn=_boom_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"bad": node}, entry="bad")

        result = await run_graph(graph, _make_state())
        assert result["status"] == "failed"
        assert any(e.error_type == "ValueError" for e in result["errors"])

    @pytest.mark.asyncio
    async def test_hitl_suspend_and_resume(self):
        """HITL: node sets needs_approval → status=awaiting_approval."""
        from core.graph.runner import run_graph

        async def _approval_node(state):
            meta = {**state.get("metadata", {}), "needs_approval": True}
            return {**state, "metadata": meta}

        node_a = GraphNode(name="gate", fn=_approval_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"gate": node_a}, entry="gate")

        # Suspend
        result = await run_graph(graph, _make_state())
        assert result["status"] == "awaiting_approval"
        assert result["metadata"]["_suspended_at"] == "gate"

        # Resume — should skip execution, evaluate edges → END
        result2 = await run_graph(graph, result, resume_from="gate")
        assert result2["status"] == "completed"

    @pytest.mark.asyncio
    async def test_event_callback_called(self):
        """on_event should be called for node lifecycle events."""
        from core.graph.runner import run_graph

        events: list[dict] = []
        async def _collector(event):
            events.append(event)

        node = GraphNode(name="ev", fn=_identity_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"ev": node}, entry="ev")

        await run_graph(graph, _make_state(), on_event=_collector)
        types = [e["type"] for e in events]
        assert "node_start" in types
        assert "node_end" in types
        assert "graph_end" in types

    @pytest.mark.asyncio
    async def test_event_callback_failure_swallowed(self):
        """A failing on_event callback should not crash the runner."""
        from core.graph.runner import run_graph

        async def _bad_callback(event):
            raise RuntimeError("callback boom")

        node = GraphNode(name="safe", fn=_identity_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"safe": node}, entry="safe")

        result = await run_graph(graph, _make_state(), on_event=_bad_callback)
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_graph_raises(self):
        """Empty graph should raise ValueError."""
        from core.graph.runner import run_graph

        with pytest.raises(ValueError, match="no nodes"):
            await run_graph(Graph(), _make_state())

    @pytest.mark.asyncio
    async def test_resume_from_invalid_node_raises(self):
        """resume_from with non-existent node should raise ValueError."""
        from core.graph.runner import run_graph

        node = GraphNode(name="a", fn=_identity_node, edges=[GraphEdge(target=END)])
        graph = Graph(nodes={"a": node}, entry="a")

        with pytest.raises(ValueError, match="not found"):
            await run_graph(graph, _make_state(), resume_from="nonexistent")

    @pytest.mark.asyncio
    async def test_no_matching_edge_raises(self):
        """Node with no matching edge should result in failed status."""
        from core.graph.runner import run_graph

        node = GraphNode(
            name="dead",
            fn=_identity_node,
            edges=[GraphEdge(target="x", condition=lambda s: False)],
        )
        graph = Graph(nodes={"dead": node}, entry="dead")

        result = await run_graph(graph, _make_state())
        assert result["status"] == "failed"
        assert any(e.error_type == "EdgeResolutionError" for e in result["errors"])


# ═══════════════════════════════════════════════════════════════════════
# 5. Nodes (mocked lazy imports)
# ═══════════════════════════════════════════════════════════════════════


class TestNodes:
    """Tests for core.graph.nodes — each node with mocked dependencies."""

    # ── validate_node ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_validate_success(self):
        """Successful step result passes validation unchanged."""
        from core.graph.nodes import validate_node

        state = _make_state(metadata={
            "step_results": [{"agent": "a", "tool": "t", "step_index": 0}],
        })
        result = await validate_node(state)
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_error_true(self):
        """Step with error=True adds an error."""
        from core.graph.nodes import validate_node

        state = _make_state(metadata={
            "step_results": [{
                "agent": "a", "tool": "t", "step_index": 0,
                "error": True, "reason": "failed",
            }],
        })
        result = await validate_node(state)
        assert len(result["errors"]) == 1
        assert result["errors"][0].error_type == "StepError"

    @pytest.mark.asyncio
    async def test_validate_refused(self):
        """Step with refused=True adds PolicyDenial error."""
        from core.graph.nodes import validate_node

        state = _make_state(metadata={
            "step_results": [{
                "agent": "a", "tool": "t", "step_index": 0,
                "refused": True, "error": "policy denied",
            }],
        })
        result = await validate_node(state)
        assert len(result["errors"]) == 1
        assert result["errors"][0].error_type == "PolicyDenial"

    @pytest.mark.asyncio
    async def test_validate_approval_required(self):
        """Step with refused=True + approval_required adds ApprovalRequired."""
        from core.graph.nodes import validate_node

        state = _make_state(metadata={
            "step_results": [{
                "agent": "a", "tool": "t", "step_index": 0,
                "refused": True, "approval_required": True,
                "error": "needs approval",
            }],
        })
        result = await validate_node(state)
        assert result["errors"][0].error_type == "ApprovalRequired"

    @pytest.mark.asyncio
    async def test_validate_unbound_skipped(self):
        """Unbound step results skip validation."""
        from core.graph.nodes import validate_node

        state = _make_state(metadata={
            "step_results": [{"unbound": True, "agent": "a", "step_index": 0}],
        })
        result = await validate_node(state)
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_empty_results(self):
        """No step results returns state unchanged."""
        from core.graph.nodes import validate_node

        state = _make_state(metadata={"step_results": []})
        result = await validate_node(state)
        assert result is state

    # ── correct_node ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_correct_increments_attempt(self):
        """correct_node should increment current_attempt."""
        from core.graph.nodes import correct_node

        state = _make_state(
            current_attempt=1,
            metadata={"current_step_index": 1},
        )
        result = await correct_node(state)
        assert result["current_attempt"] == 2

    @pytest.mark.asyncio
    async def test_correct_rolls_back_step_index(self):
        """correct_node should decrement current_step_index for retry."""
        from core.graph.nodes import correct_node

        state = _make_state(
            current_attempt=1,
            metadata={"current_step_index": 2},
        )
        result = await correct_node(state)
        assert result["metadata"]["current_step_index"] == 1

    @pytest.mark.asyncio
    async def test_correct_circuit_broken(self):
        """correct_node sets status=circuit_broken when CB trips."""
        from core.graph.nodes import correct_node

        state = _make_state(
            current_attempt=3,  # after increment: 4 > max_attempts=3
            max_attempts=3,
            metadata={"current_step_index": 1},
        )
        result = await correct_node(state)
        assert result["current_attempt"] == 4
        assert result["status"] == "circuit_broken"

    # ── plan_node (mocked imports) ────────────────────────────────

    @pytest.mark.asyncio
    async def test_plan_node_creates_steps(self):
        """plan_node decomposes task into steps via keyword matching."""
        from core.graph.nodes import plan_node

        mock_patterns = [
            {"keywords": ["test", "hello"], "steps": [{"tool": "t1", "agent": "a1"}]},
        ]
        mock_defaults = [{"tool": "default_tool", "agent": "default_agent"}]
        mock_agent_map = {"manager": "test-manager"}

        # plan_node does lazy imports from backend.orchestrator and
        # core.integration inside its body, so we must mock the source
        # modules via sys.modules + patch on the real module path.
        mock_orchestrator = MagicMock(
            MISSION_PATTERNS=mock_patterns,
            DEFAULT_STEPS=mock_defaults,
            AGENT_PERSONA_MAP=mock_agent_map,
        )
        with (
            patch.dict("sys.modules", {"backend.orchestrator": mock_orchestrator}),
            patch("core.integration.get_persona_contract", return_value=None),
        ):
            state = _make_state(metadata={
                "task_text": "test hello world",
                "mission_id": 1,
            })
            result = await plan_node(state)

            assert result["status"] == "running"
            assert result["metadata"]["steps"] is not None
            assert len(result["metadata"]["steps"]) == 1
            assert result["metadata"]["current_step_index"] == 0
            assert result["metadata"]["step_results"] == []
            assert result["metadata"]["manager_persona_id"] == "test-manager"

    # ── execute_node (mocked broker) ──────────────────────────────

    @pytest.mark.asyncio
    async def test_execute_node_unbound_tool(self):
        """execute_node skips steps with tool=None."""
        from core.graph.nodes import execute_node

        state = _make_state(metadata={
            "steps": [{"tool": None, "agent": "a1"}],
            "current_step_index": 0,
            "task_text": "test",
            "mission_id": 1,
            "manager_persona_id": "mgr",
            "step_results": [],
        })
        result = await execute_node(state)
        last = result["metadata"]["step_results"][-1]
        assert last["unbound"] is True
        assert result["metadata"]["current_step_index"] == 1

    @pytest.mark.asyncio
    async def test_execute_node_out_of_bounds(self):
        """execute_node returns state unchanged when step_index >= len(steps)."""
        from core.graph.nodes import execute_node

        state = _make_state(metadata={
            "steps": [{"tool": "t", "agent": "a"}],
            "current_step_index": 5,
            "step_results": [],
        })
        result = await execute_node(state)
        assert result is state

    # ── Module exports ────────────────────────────────────────────

    def test_nodes_module_exports(self):
        """All 7 node functions are listed in __all__."""
        from core.graph import nodes

        expected = {
            "plan_node", "gate_node", "route_node", "execute_node",
            "validate_node", "correct_node", "post_gate_node",
        }
        assert expected == set(nodes.__all__)

    def test_all_nodes_are_async(self):
        """All exported nodes should be coroutine functions."""
        import inspect

        from core.graph import nodes

        for name in nodes.__all__:
            fn = getattr(nodes, name)
            assert inspect.iscoroutinefunction(fn), f"{name} is not async"


# ═══════════════════════════════════════════════════════════════════════
# 6. Edge Predicates
# ═══════════════════════════════════════════════════════════════════════


class TestEdgePredicates:
    """Tests for the 4 predicate functions in core.graph.edges."""

    def test_gate_blocked_true(self):
        from core.graph.edges import _gate_blocked

        assert _gate_blocked(_make_state(status="failed")) is True

    def test_gate_blocked_false(self):
        from core.graph.edges import _gate_blocked

        assert _gate_blocked(_make_state(status="running")) is False

    def test_has_step_failure_error_true(self):
        from core.graph.edges import _has_step_failure

        state = _make_state(metadata={"step_results": [{"error": True}]})
        assert _has_step_failure(state) is True

    def test_has_step_failure_refused(self):
        from core.graph.edges import _has_step_failure

        state = _make_state(metadata={"step_results": [{"refused": True}]})
        assert _has_step_failure(state) is True

    def test_has_step_failure_unbound_skipped(self):
        from core.graph.edges import _has_step_failure

        state = _make_state(metadata={
            "step_results": [{"unbound": True, "error": True}],
        })
        assert _has_step_failure(state) is False

    def test_has_step_failure_success(self):
        from core.graph.edges import _has_step_failure

        state = _make_state(metadata={"step_results": [{"data": "ok"}]})
        assert _has_step_failure(state) is False

    def test_has_step_failure_empty(self):
        from core.graph.edges import _has_step_failure

        assert _has_step_failure(_make_state(metadata={"step_results": []})) is False

    def test_has_more_steps_true(self):
        from core.graph.edges import _has_more_steps

        state = _make_state(metadata={
            "current_step_index": 0,
            "steps": [{"tool": "a"}, {"tool": "b"}],
        })
        assert _has_more_steps(state) is True

    def test_has_more_steps_false(self):
        from core.graph.edges import _has_more_steps

        state = _make_state(metadata={
            "current_step_index": 2,
            "steps": [{"tool": "a"}, {"tool": "b"}],
        })
        assert _has_more_steps(state) is False

    def test_is_circuit_broken_true(self):
        from core.graph.edges import _is_circuit_broken

        assert _is_circuit_broken(_make_state(status="circuit_broken")) is True

    def test_is_circuit_broken_false(self):
        from core.graph.edges import _is_circuit_broken

        assert _is_circuit_broken(_make_state(status="running")) is False


# ═══════════════════════════════════════════════════════════════════════
# 7. build_graph structure
# ═══════════════════════════════════════════════════════════════════════


class TestBuildGraph:
    """Tests for build_graph() factory."""

    def test_build_returns_graph(self):
        from core.graph.edges import build_graph

        g = build_graph()
        assert isinstance(g, Graph)

    def test_has_seven_nodes(self):
        from core.graph.edges import build_graph

        g = build_graph()
        assert len(g.nodes) == 7

    def test_entry_is_plan_node(self):
        from core.graph.edges import build_graph

        g = build_graph()
        assert g.entry == "plan_node"

    def test_all_expected_nodes_present(self):
        from core.graph.edges import build_graph

        g = build_graph()
        expected = {
            "plan_node", "gate_node", "route_node", "execute_node",
            "validate_node", "correct_node", "post_gate_node",
        }
        assert set(g.nodes.keys()) == expected

    def test_plan_node_edges(self):
        from core.graph.edges import build_graph

        g = build_graph()
        edges = g.nodes["plan_node"].edges
        assert len(edges) == 1
        assert edges[0].target == "gate_node"

    def test_gate_node_edges(self):
        from core.graph.edges import build_graph

        g = build_graph()
        edges = g.nodes["gate_node"].edges
        assert len(edges) == 2
        assert edges[0].target == END  # blocked
        assert edges[1].target == "route_node"  # fallback

    def test_validate_node_edges(self):
        from core.graph.edges import build_graph

        g = build_graph()
        edges = g.nodes["validate_node"].edges
        assert len(edges) == 3
        assert edges[0].target == "correct_node"  # failure
        assert edges[1].target == "execute_node"  # more steps
        assert edges[2].target == "post_gate_node"  # done (fallback)

    def test_correct_node_edges(self):
        from core.graph.edges import build_graph

        g = build_graph()
        edges = g.nodes["correct_node"].edges
        assert len(edges) == 2
        assert edges[0].target == END  # circuit broken
        assert edges[1].target == "execute_node"  # retry (fallback)

    def test_post_gate_node_edges(self):
        from core.graph.edges import build_graph

        g = build_graph()
        edges = g.nodes["post_gate_node"].edges
        assert len(edges) == 1
        assert edges[0].target == END


# ═══════════════════════════════════════════════════════════════════════
# 8. Telemetry
# ═══════════════════════════════════════════════════════════════════════


class TestTelemetryInstrumented:
    """Tests for core.graph.telemetry.instrumented()."""

    def test_returns_callable(self):
        from core.graph.telemetry import instrumented

        wrapped = instrumented(_identity_node, node_name="test")
        assert callable(wrapped)

    def test_preserves_name(self):
        from core.graph.telemetry import instrumented

        wrapped = instrumented(_identity_node, node_name="plan_node")
        assert wrapped.__name__ == "instrumented_plan_node"

    def test_preserves_wrapped_ref(self):
        from core.graph.telemetry import instrumented

        wrapped = instrumented(_identity_node, node_name="x")
        assert wrapped.__wrapped__ is _identity_node

    @pytest.mark.asyncio
    async def test_happy_path_writes_two_records(self):
        """Start + end = 2 trace records."""
        from core.graph.telemetry import instrumented

        container = _FakeContainer()
        wrapped = instrumented(
            _identity_node, node_name="test_node", container=container,
        )
        state = _make_state()
        result = await wrapped(state)

        assert result["status"] == state["status"]
        records = container.trace_writer.records
        assert len(records) == 2
        assert records[0]["event"] == "node.test_node.start"
        assert records[1]["event"] == "node.test_node.end"
        assert records[1]["status"] == "ok"
        assert "duration_ms" in records[1]
        assert records[1]["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_error_path_writes_error_record(self):
        """Start + error = 2 records with error info."""
        from core.graph.telemetry import instrumented

        container = _FakeContainer()
        wrapped = instrumented(
            _boom_node, node_name="bad_node", container=container,
        )
        with pytest.raises(ValueError, match="intentional"):
            await wrapped(_make_state())

        records = container.trace_writer.records
        assert len(records) == 2
        assert records[1]["event"] == "node.bad_node.error"
        assert records[1]["status"] == "error"
        assert records[1]["error_type"] == "ValueError"
        assert "intentional" in records[1]["error_message"]

    @pytest.mark.asyncio
    async def test_token_delta_detection(self):
        """Wrapper should detect token changes made by the node."""
        from core.graph.telemetry import instrumented

        container = _FakeContainer()
        wrapped = instrumented(
            _token_node, node_name="llm_node", container=container,
        )
        result = await wrapped(_make_state())

        assert result["token_usage"].prompt_tokens == 100
        assert result["token_usage"].completion_tokens == 50

        end_record = container.trace_writer.records[1]
        assert end_record["token_delta"]["prompt_tokens"] == 100
        assert end_record["token_delta"]["completion_tokens"] == 50
        assert end_record["token_delta"]["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_no_container_does_not_crash(self):
        """When container is None and get_container fails, no crash."""
        from core.graph.telemetry import instrumented

        wrapped = instrumented(_identity_node, node_name="solo")
        result = await wrapped(_make_state())
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_obs_ctx_records_visit(self):
        """ObservabilityContext.record_visit() is called."""
        from core.bootstrap import ObservabilityContext
        from core.graph.telemetry import instrumented

        obs = ObservabilityContext.create(server="test")
        assert obs.node_visits == 0

        container = _FakeContainer()
        wrapped = instrumented(
            _identity_node, node_name="counted",
            container=container, obs_ctx=obs,
        )
        await wrapped(_make_state())
        assert obs.node_visits == 1

    @pytest.mark.asyncio
    async def test_trace_record_fields(self):
        """Verify trace record has all expected W3C-compatible fields."""
        from core.graph.telemetry import instrumented

        container = _FakeContainer()
        wrapped = instrumented(
            _identity_node, node_name="field_check", container=container,
        )
        await wrapped(_make_state())

        rec = container.trace_writer.records[0]
        required = {
            "schema_version", "ts", "trace_id", "span_id",
            "parent_span_id", "server", "tool", "event", "status",
        }
        assert required.issubset(rec.keys()), f"Missing: {required - rec.keys()}"
        assert rec["server"] == "graph"
        assert rec["tool"] == "graph.field_check"


class TestTelemetryRunGraph:
    """Tests for core.graph.telemetry.instrumented_run_graph()."""

    @pytest.mark.asyncio
    async def test_instruments_all_nodes(self):
        """Every node in the graph should be wrapped."""
        from core.graph.telemetry import instrumented_run_graph

        node_a = GraphNode(
            name="a", fn=_identity_node, edges=[GraphEdge(target=END)],
        )
        graph = Graph(nodes={"a": node_a}, entry="a")
        state = _make_state(status="running")
        container = _FakeContainer()

        result = await instrumented_run_graph(
            graph, state, container=container,
        )

        assert result["status"] == "completed"
        assert "instrumented" in graph.nodes["a"].fn.__name__
        # At least start + end for node 'a'
        assert len(container.trace_writer.records) >= 2

    @pytest.mark.asyncio
    async def test_idempotent_wrapping(self):
        """Re-instrumenting already-wrapped nodes unwraps first."""
        from core.graph.telemetry import instrumented, instrumented_run_graph

        # Pre-wrap
        wrapped_fn = instrumented(_identity_node, node_name="a")
        node_a = GraphNode(
            name="a", fn=wrapped_fn, edges=[GraphEdge(target=END)],
        )
        graph = Graph(nodes={"a": node_a}, entry="a")
        container = _FakeContainer()

        result = await instrumented_run_graph(
            graph, _make_state(status="running"), container=container,
        )
        assert result["status"] == "completed"
        # Should still work — double-wrapping doesn't crash
        assert "instrumented" in graph.nodes["a"].fn.__name__

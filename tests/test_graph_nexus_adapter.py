"""Tests for core.graph.nexus_adapter — NexusEventAdapter.

Run:  C:\\Python314\\python.exe -m pytest tests/test_graph_nexus_adapter.py -v --tb=short

These tests verify the streaming adapter that translates graph runner
lifecycle events into the Nexus event-protocol.js wire format expected
by the React frontend.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.graph.nexus_adapter import (
    DEFAULT_NODE_AGENT_MAP,
    STEP_AGENT_SENTINEL,
    NexusEventAdapter,
)
from core.state import create_initial_state


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_adapter(
    mission_id: int = 42,
    sent: list | None = None,
    **kwargs,
) -> NexusEventAdapter:
    """Create an adapter with a collecting send callback."""
    collected = sent if sent is not None else []

    async def _send(event: dict) -> None:
        collected.append(event)

    adapter = NexusEventAdapter(mission_id, _send, **kwargs)
    return adapter


def _make_state_with_steps(
    steps: list[dict[str, Any]] | None = None,
    current_step_index: int = 1,
    **extra_meta,
) -> dict[str, Any]:
    """Create a GraphState-like dict with step metadata."""
    state = create_initial_state()
    if steps is None:
        steps = [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {}, "bubble": "Pesquisando..."},
            {"agent": "coder", "tool": "get_brain_status", "input": {}, "bubble": "Verificando..."},
        ]
    state = {
        **state,
        "metadata": {
            **state["metadata"],
            "task_text": "test task",
            "mission_id": 42,
            "steps": steps,
            "current_step_index": current_step_index,
            "agents_involved": sorted({s["agent"] for s in steps}),
            **extra_meta,
        },
    }
    return state


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestNodeStartTranslation:
    """node_start events produce Nexus status_change or collaboration."""

    @pytest.mark.asyncio
    async def test_plan_node_produces_thinking_status(self):
        """plan_node start → status_change with status='thinking'."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        assert len(events) == 1
        assert events[0]["type"] == "status_change"
        assert events[0]["agentId"] == "manager"
        assert events[0]["payload"]["status"] == "thinking"

    @pytest.mark.asyncio
    async def test_gate_node_produces_working_status(self):
        """gate_node start → status_change with status='working'."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "gate_node", "trace_id": "t", "iteration": 1})

        assert len(events) == 1
        assert events[0]["type"] == "status_change"
        assert events[0]["agentId"] == "manager"
        assert events[0]["payload"]["status"] == "working"

    @pytest.mark.asyncio
    async def test_route_node_produces_collaboration(self):
        """route_node start → collaboration event with distribute subtype."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps()
        adapter.set_state(state)

        await adapter.on_event({"type": "node_start", "node": "route_node", "trace_id": "t", "iteration": 2})

        assert len(events) == 1
        assert events[0]["type"] == "collaboration"
        assert events[0]["payload"]["subtype"] == "distribute"
        assert events[0]["agentId"] == "manager"

    @pytest.mark.asyncio
    async def test_execute_node_resolves_step_agent(self):
        """execute_node start → status_change with agent from current step."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        # Step index = 1 means step[0] was just executed
        state = _make_state_with_steps(current_step_index=1)
        adapter.set_state(state)

        await adapter.on_event({"type": "node_start", "node": "execute_node", "trace_id": "t", "iteration": 3})

        assert len(events) == 1
        assert events[0]["type"] == "status_change"
        assert events[0]["agentId"] == "researcher"
        assert events[0]["payload"]["bubble"] == "Pesquisando..."

    @pytest.mark.asyncio
    async def test_execute_node_second_step_resolves_coder(self):
        """Second step resolves to 'coder' agent."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps(current_step_index=2)
        adapter.set_state(state)

        await adapter.on_event({"type": "node_start", "node": "execute_node", "trace_id": "t", "iteration": 5})

        assert events[0]["agentId"] == "coder"
        assert events[0]["payload"]["bubble"] == "Verificando..."


class TestNodeEndTranslation:
    """node_end events produce status_change(done) for relevant nodes."""

    @pytest.mark.asyncio
    async def test_execute_node_end_produces_done(self):
        """execute_node end → status_change(done) for the step agent."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps(current_step_index=1)
        adapter.set_state(state)

        await adapter.on_event({"type": "node_end", "node": "execute_node", "trace_id": "t", "iteration": 4, "status": "running"})

        assert len(events) == 1
        assert events[0]["type"] == "status_change"
        assert events[0]["payload"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_plan_node_end_produces_no_events(self):
        """plan_node end → no Nexus events (internal node)."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_end", "node": "plan_node", "trace_id": "t", "iteration": 0, "status": "running"})

        assert len(events) == 0


class TestGraphEndTranslation:
    """graph_end events produce completion, message, or circuit_broken."""

    @pytest.mark.asyncio
    async def test_completed_produces_completion(self):
        """graph_end with status=completed → completion event."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "graph_end", "trace_id": "t", "iteration": 10, "status": "completed", "reason": "reached_end"})

        assert len(events) == 1
        assert events[0]["type"] == "completion"
        assert events[0]["agentId"] == "manager"
        assert "🎉" in events[0]["payload"]["bubble"]

    @pytest.mark.asyncio
    async def test_failed_produces_message(self):
        """graph_end with status=failed → message event."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "graph_end", "trace_id": "t", "iteration": 2, "status": "failed", "reason": "node_exception"})

        assert len(events) == 1
        assert events[0]["type"] == "message"
        assert "bloqueada" in events[0]["payload"]["message"].lower()

    @pytest.mark.asyncio
    async def test_circuit_broken_produces_message(self):
        """graph_end with status=circuit_broken → message about CB."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "graph_end", "trace_id": "t", "iteration": 6, "status": "circuit_broken", "reason": "per_step_circuit_breaker"})

        assert len(events) == 1
        assert events[0]["type"] == "message"
        assert "circuit breaker" in events[0]["payload"]["message"].lower()


class TestGraphSuspended:
    """graph_suspended → approval_request."""

    @pytest.mark.asyncio
    async def test_suspended_produces_approval_request(self):
        """graph_suspended → approval_request event for manager."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "graph_suspended", "node": "gate_node", "trace_id": "t", "iteration": 1, "reason": "awaiting_approval"})

        assert len(events) == 1
        assert events[0]["type"] == "approval_request"
        assert events[0]["agentId"] == "manager"


class TestNodeError:
    """node_error → error message."""

    @pytest.mark.asyncio
    async def test_node_error_produces_error_message(self):
        """node_error → message with error details."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({
            "type": "node_error", "node": "execute_node",
            "trace_id": "t", "iteration": 3,
            "error_type": "ValueError", "error_message": "something broke",
        })

        assert len(events) == 1
        assert events[0]["type"] == "message"
        assert "something broke" in events[0]["payload"]["message"]


class TestProtocolCompliance:
    """Nexus event-protocol.js compliance."""

    @pytest.mark.asyncio
    async def test_schema_version_is_1(self):
        """All events have schemaVersion=1."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        assert events[0]["schemaVersion"] == 1

    @pytest.mark.asyncio
    async def test_mission_id_propagated(self):
        """All events carry the correct missionId."""
        events: list[dict] = []
        adapter = _make_adapter(mission_id=99, sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        assert events[0]["missionId"] == 99

    @pytest.mark.asyncio
    async def test_sequence_monotonic(self):
        """Sequence numbers are strictly increasing."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})
        await adapter.on_event({"type": "node_start", "node": "gate_node", "trace_id": "t", "iteration": 1})
        await adapter.on_event({"type": "graph_end", "trace_id": "t", "iteration": 5, "status": "completed", "reason": "reached_end"})

        sequences = [e["sequence"] for e in events]
        assert sequences == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_has_required_fields(self):
        """Every event has all required event-protocol.js fields."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        required = {"schemaVersion", "id", "missionId", "sequence", "agentId", "type", "timestamp", "payload"}
        assert required.issubset(events[0].keys())

    @pytest.mark.asyncio
    async def test_event_id_format(self):
        """Event IDs follow the evt:<missionId>:<hex> format."""
        events: list[dict] = []
        adapter = _make_adapter(mission_id=42, sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        assert events[0]["id"].startswith("evt:42:")

    @pytest.mark.asyncio
    async def test_timestamp_is_ms_epoch(self):
        """Timestamp is a float representing ms since epoch (JS-compatible)."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        # Should be in the ballpark of current time in ms
        ts = events[0]["timestamp"]
        assert isinstance(ts, float)
        assert ts > 1_000_000_000_000  # After ~2001 in ms


class TestEdgeCases:
    """Edge cases and resilience."""

    @pytest.mark.asyncio
    async def test_unknown_node_defaults_to_manager(self):
        """Unknown node names fall back to 'manager' agent."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "node_start", "node": "future_node_xyz", "trace_id": "t", "iteration": 0})

        assert events[0]["agentId"] == "manager"

    @pytest.mark.asyncio
    async def test_edge_taken_produces_no_events(self):
        """edge_taken has no Nexus equivalent → no events."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)

        await adapter.on_event({"type": "edge_taken", "from_node": "plan_node", "to_node": "gate_node", "trace_id": "t", "iteration": 0})

        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_send_failure_does_not_crash_adapter(self):
        """If the send callback raises, the adapter logs but doesn't crash."""
        async def _exploding_send(event: dict) -> None:
            raise ConnectionError("websocket closed")

        adapter = NexusEventAdapter(42, _exploding_send)

        # Should NOT raise
        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

    @pytest.mark.asyncio
    async def test_custom_node_agent_map(self):
        """Custom node_agent_map overrides the default."""
        events: list[dict] = []
        custom_map = {"plan_node": "researcher"}
        adapter = _make_adapter(sent=events, node_agent_map=custom_map)

        await adapter.on_event({"type": "node_start", "node": "plan_node", "trace_id": "t", "iteration": 0})

        assert events[0]["agentId"] == "researcher"

    @pytest.mark.asyncio
    async def test_no_state_execute_node_fallback(self):
        """execute_node without state set falls back to manager."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        # Don't call set_state

        await adapter.on_event({"type": "node_start", "node": "execute_node", "trace_id": "t", "iteration": 0})

        assert events[0]["agentId"] == "manager"

    @pytest.mark.asyncio
    async def test_step_index_out_of_bounds_fallback(self):
        """Step index beyond steps list falls back to manager."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps(current_step_index=99)
        adapter.set_state(state)

        await adapter.on_event({"type": "node_start", "node": "execute_node", "trace_id": "t", "iteration": 0})

        assert events[0]["agentId"] == "manager"


class TestDefaultNodeAgentMap:
    """Verify the default map structure."""

    def test_all_graph_nodes_mapped(self):
        """All 7 graph nodes are present in the default map."""
        expected = {"plan_node", "gate_node", "route_node", "execute_node", "validate_node", "correct_node", "post_gate_node"}
        assert expected == set(DEFAULT_NODE_AGENT_MAP.keys())

    def test_execute_node_uses_sentinel(self):
        """execute_node uses the STEP_AGENT_SENTINEL."""
        assert DEFAULT_NODE_AGENT_MAP["execute_node"] == STEP_AGENT_SENTINEL

    def test_sentinel_value(self):
        """STEP_AGENT_SENTINEL is the expected string."""
        assert STEP_AGENT_SENTINEL == "__step__"


class TestAutoStateSync:
    """Verify adapter auto-syncs state from _state field in events."""

    @pytest.mark.asyncio
    async def test_state_auto_synced_from_event(self):
        """Adapter picks up _state from event and resolves step agent."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps(current_step_index=1)

        # Don't call set_state() — let auto-sync do the work
        await adapter.on_event({
            "type": "node_start", "node": "execute_node",
            "trace_id": "t", "iteration": 3,
            "_state": state,
        })

        assert events[0]["agentId"] == "researcher"
        assert events[0]["payload"]["bubble"] == "Pesquisando..."

    @pytest.mark.asyncio
    async def test_state_auto_synced_on_node_end(self):
        """Adapter picks up _state from node_end and resolves agent."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps(current_step_index=2)

        await adapter.on_event({
            "type": "node_end", "node": "execute_node",
            "trace_id": "t", "iteration": 4, "status": "running",
            "_state": state,
        })

        assert len(events) == 1
        assert events[0]["agentId"] == "coder"

    @pytest.mark.asyncio
    async def test_no_state_field_keeps_previous_state(self):
        """Events without _state don't overwrite manually set state."""
        events: list[dict] = []
        adapter = _make_adapter(sent=events)
        state = _make_state_with_steps(current_step_index=1)
        adapter.set_state(state)

        # Event without _state
        await adapter.on_event({
            "type": "node_start", "node": "execute_node",
            "trace_id": "t", "iteration": 3,
        })

        # Should still use the manually set state
        assert events[0]["agentId"] == "researcher"

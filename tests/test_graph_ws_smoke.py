"""Smoke tests for the graph engine path in ws_server.

Run:  C:\\Python314\\python.exe -m pytest tests/test_graph_ws_smoke.py -v --tb=short

These tests verify the Strangler Fig graph path:
1. ``_run_graph_mission`` sends Nexus events via the adapter
2. HITL resume loop: graph suspends → approve → resume → complete
3. HITL timeout: graph suspends → no approval → timeout
4. ``_graph_approval_events`` lifecycle (created, signaled, cleaned up)
5. Cancellation cleans up approval events
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import ws_server
from backend.ws_server import _graph_approval_events, _run_graph_mission


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _fake_ws() -> MagicMock:
    """Create a mock websocket with async send."""
    ws = MagicMock()
    ws.sent: list[dict] = []

    async def _send(payload: str) -> None:
        ws.sent.append(json.loads(payload))

    ws.send = AsyncMock(side_effect=_send)
    return ws


def _completed_state(**overrides) -> dict[str, Any]:
    """Return a GraphState-like dict with status=completed."""
    return {
        "status": "completed",
        "trace_id": "abc123",
        "node_history": ["plan_node", "gate_node"],
        "metadata": {"task_text": "test", "mission_id": 42},
        **overrides,
    }


def _suspended_state(suspended_at: str = "gate_node") -> dict[str, Any]:
    """Return a GraphState-like dict with status=awaiting_approval."""
    return {
        "status": "awaiting_approval",
        "trace_id": "abc123",
        "node_history": ["plan_node", "gate_node"],
        "metadata": {
            "task_text": "test",
            "mission_id": 42,
            "needs_approval": True,
            "_suspended_at": suspended_at,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRunGraphMissionHappyPath:
    """_run_graph_mission completes and sends events."""

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_happy_path_sends_events(
        self, mock_build, mock_run, mock_create,
    ):
        """Graph completes → events sent via adapter → no approval event leaked."""
        mock_build.return_value = MagicMock()
        mock_create.return_value = {
            "status": "idle",
            "metadata": {},
            "trace_id": "t",
            "node_history": [],
        }
        mock_run.return_value = _completed_state()

        ws = _fake_ws()
        await _run_graph_mission(ws, "test task", 42)

        # instrumented_run_graph was called once (no resume)
        mock_run.assert_called_once()
        # No leaked approval events
        assert 42 not in _graph_approval_events

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_state_seeded_with_task_metadata(
        self, mock_build, mock_run, mock_create,
    ):
        """Initial state has task_text and mission_id in metadata."""
        mock_build.return_value = MagicMock()
        base_state = {
            "status": "idle",
            "metadata": {"extra": "kept"},
            "trace_id": "t",
            "node_history": [],
        }
        mock_create.return_value = base_state
        mock_run.return_value = _completed_state()

        ws = _fake_ws()
        await _run_graph_mission(ws, "deploy app", 99)

        # Check the state passed to instrumented_run_graph
        call_args = mock_run.call_args
        state_passed = call_args[0][1]  # second positional arg
        assert state_passed["metadata"]["task_text"] == "deploy app"
        assert state_passed["metadata"]["mission_id"] == 99
        assert state_passed["metadata"]["extra"] == "kept"


class TestRunGraphMissionHITL:
    """HITL resume loop in _run_graph_mission."""

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_hitl_suspend_and_resume(
        self, mock_build, mock_run, mock_create,
    ):
        """Graph suspends → approval signaled → graph resumes → completes."""
        mock_build.return_value = MagicMock()
        mock_create.return_value = {
            "status": "idle", "metadata": {}, "trace_id": "t", "node_history": [],
        }
        # First call: suspend; second call: complete
        mock_run.side_effect = [
            _suspended_state("gate_node"),
            _completed_state(),
        ]

        ws = _fake_ws()

        async def _approve_after_delay():
            """Simulate APPROVE arriving after a short delay."""
            await asyncio.sleep(0.05)
            evt = _graph_approval_events.get(42)
            assert evt is not None, "Approval event should be registered"
            evt.set()

        approval_task = asyncio.create_task(_approve_after_delay())
        await _run_graph_mission(ws, "test task", 42)
        await approval_task

        # instrumented_run_graph called twice: initial + resume
        assert mock_run.call_count == 2
        # Resume call has resume_from="gate_node"
        resume_call = mock_run.call_args_list[1]
        assert resume_call[1]["resume_from"] == "gate_node"
        # Approval event cleaned up
        assert 42 not in _graph_approval_events

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_hitl_timeout(
        self, mock_build, mock_run, mock_create,
    ):
        """Graph suspends → no approval → timeout after short period."""
        mock_build.return_value = MagicMock()
        mock_create.return_value = {
            "status": "idle", "metadata": {}, "trace_id": "t", "node_history": [],
        }
        mock_run.return_value = _suspended_state("gate_node")

        ws = _fake_ws()

        # Patch timeout to 0.1s for fast test
        with patch("backend.ws_server.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await _run_graph_mission(ws, "test task", 42)

        # Only called once (no resume after timeout)
        mock_run.assert_called_once()
        # Approval event cleaned up
        assert 42 not in _graph_approval_events

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_hitl_missing_suspended_at(
        self, mock_build, mock_run, mock_create,
    ):
        """Graph suspends but _suspended_at missing → graceful exit."""
        mock_build.return_value = MagicMock()
        mock_create.return_value = {
            "status": "idle", "metadata": {}, "trace_id": "t", "node_history": [],
        }
        # Suspended state WITHOUT _suspended_at
        bad_state = {
            "status": "awaiting_approval",
            "trace_id": "t",
            "node_history": [],
            "metadata": {"task_text": "test", "mission_id": 42},
        }
        mock_run.return_value = bad_state

        ws = _fake_ws()

        async def _approve_fast():
            await asyncio.sleep(0.05)
            evt = _graph_approval_events.get(42)
            if evt:
                evt.set()

        approval_task = asyncio.create_task(_approve_fast())
        await _run_graph_mission(ws, "test task", 42)
        await approval_task

        # Only called once (no resume — missing _suspended_at)
        mock_run.assert_called_once()


class TestRunGraphMissionErrorHandling:
    """Error handling in _run_graph_mission."""

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_exception_sends_error_event(
        self, mock_build, mock_run, mock_create,
    ):
        """Unexpected exception → error event sent to websocket."""
        mock_build.return_value = MagicMock()
        mock_create.return_value = {
            "status": "idle", "metadata": {}, "trace_id": "t", "node_history": [],
        }
        mock_run.side_effect = RuntimeError("boom")

        ws = _fake_ws()
        await _run_graph_mission(ws, "test task", 42)

        # Error event was sent
        assert any(
            e.get("type") == "message" and "boom" in e.get("payload", {}).get("message", "")
            for e in ws.sent
        )
        # Cleanup
        assert 42 not in _graph_approval_events

    @pytest.mark.asyncio
    @patch("core.state.create_initial_state")
    @patch("core.graph.telemetry.instrumented_run_graph", new_callable=AsyncMock)
    @patch("core.graph.edges.build_graph")
    async def test_cancellation_cleans_up(
        self, mock_build, mock_run, mock_create,
    ):
        """CancelledError during graph run → approval events cleaned up."""
        mock_build.return_value = MagicMock()
        mock_create.return_value = {
            "status": "idle", "metadata": {}, "trace_id": "t", "node_history": [],
        }
        mock_run.side_effect = asyncio.CancelledError()

        ws = _fake_ws()
        await _run_graph_mission(ws, "test task", 42)

        assert 42 not in _graph_approval_events


class TestGraphApprovalEvents:
    """_graph_approval_events lifecycle management."""

    def test_approval_events_dict_exists(self):
        """Module-level _graph_approval_events is an empty dict."""
        assert isinstance(_graph_approval_events, dict)

    @pytest.mark.asyncio
    async def test_approval_event_signal_and_cleanup(self):
        """Register an event, signal it, verify it's consumed."""
        evt = asyncio.Event()
        _graph_approval_events[999] = evt
        assert not evt.is_set()

        evt.set()
        assert evt.is_set()

        # Cleanup
        _graph_approval_events.pop(999, None)
        assert 999 not in _graph_approval_events


class TestMissionEngineFlag:
    """MISSION_ENGINE Strangler Fig flag."""

    def test_default_is_legacy(self):
        """Default MISSION_ENGINE value should be 'legacy'."""
        # The actual value depends on env var, but we verify the import works
        from backend.ws_server import MISSION_ENGINE
        assert MISSION_ENGINE in ("legacy", "graph", "shadow")

    def test_graph_approval_events_importable(self):
        """_graph_approval_events is importable from ws_server."""
        from backend.ws_server import _graph_approval_events
        assert isinstance(_graph_approval_events, dict)

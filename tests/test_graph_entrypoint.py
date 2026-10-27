"""Tests for core.graph.entrypoint — run_mission_graph() entry-point.

Run:  C:\\Python314\\python.exe -m pytest tests/test_graph_entrypoint.py -v --tb=short

These tests exercise the public ``run_mission_graph()`` entry-point that
wires together ``build_graph``, ``create_initial_state``, and
``instrumented_run_graph``.  All external dependencies are mocked via the
``_patch_graph_infra`` context manager from the integration test module.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Import the fixture context manager from integration tests ──────────
from tests.test_graph_integration import (
    _broker_refused,
    _broker_success,
    _gate_green,
    _gate_red,
    _patch_graph_infra,
)

from core.graph.entrypoint import run_mission_graph
from core.state import GraphState


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


class _FakeTraceWriter:
    """Minimal trace writer that captures records for assertions."""

    def __init__(self):
        self.records: list[dict[str, Any]] = []

    def write(self, record, path=None):
        self.records.append(record)


class _FakeContainer:
    """Minimal DI container with a fake trace writer."""

    def __init__(self):
        self.trace_writer = _FakeTraceWriter()


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """Happy-path tests for run_mission_graph()."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_completed(self):
        """Green-gate mission completes with status='completed'."""
        with _patch_graph_infra():
            result = await run_mission_graph(
                task="test deploy application",
                mission_id=42,
            )

        assert result["status"] == "completed"
        assert "plan_node" in result["node_history"]
        assert "post_gate_node" in result["node_history"]

    @pytest.mark.asyncio
    async def test_metadata_has_task_and_mission(self):
        """Metadata contains the task_text and mission_id seeded by the entry-point."""
        with _patch_graph_infra():
            result = await run_mission_graph(
                task="analyse quarterly reports",
                mission_id=99,
            )

        assert result["metadata"]["task_text"] == "analyse quarterly reports"
        assert result["metadata"]["mission_id"] == 99


class TestGateBlocked:
    """Gate-blocked scenario."""

    @pytest.mark.asyncio
    async def test_gate_blocked_returns_failed(self):
        """RED semaphore → status='failed', no execute/post_gate nodes visited."""
        with _patch_graph_infra(check_mission=_gate_red):
            result = await run_mission_graph(
                task="blocked task",
                mission_id=7,
            )

        assert result["status"] == "failed"
        assert "gate_node" in result["node_history"]
        assert "execute_node" not in result["node_history"]
        assert "post_gate_node" not in result["node_history"]


class TestCustomMaxAttempts:
    """Verify max_attempts is forwarded correctly."""

    @pytest.mark.asyncio
    async def test_custom_max_attempts(self):
        """max_attempts=5 is reflected in the result state."""
        with _patch_graph_infra():
            result = await run_mission_graph(
                task="deploy",
                mission_id=1,
                max_attempts=5,
            )

        assert result["max_attempts"] == 5


class TestOnEventCallback:
    """on_event callback integration."""

    @pytest.mark.asyncio
    async def test_on_event_callback_receives_events(self):
        """on_event callback is invoked at least once during graph execution."""
        events: list[dict[str, Any]] = []

        async def _collect(event: dict[str, Any]) -> None:
            events.append(event)

        with _patch_graph_infra():
            result = await run_mission_graph(
                task="event test",
                mission_id=10,
                on_event=_collect,
            )

        assert result["status"] == "completed"
        assert len(events) >= 1
        # Should contain node lifecycle events
        event_types = [e.get("type") for e in events]
        assert "node_start" in event_types


class TestContainerForwarding:
    """Container is forwarded to instrumented_run_graph for trace writing."""

    @pytest.mark.asyncio
    async def test_container_forwarded_to_instrumented(self):
        """Fake container receives trace records during execution."""
        container = _FakeContainer()

        with _patch_graph_infra():
            result = await run_mission_graph(
                task="trace test",
                mission_id=20,
                container=container,
            )

        assert result["status"] == "completed"
        # The container's trace_writer should have captured records
        assert len(container.trace_writer.records) >= 1
        # At least one record should reference a graph node
        events = [r.get("event", "") for r in container.trace_writer.records]
        assert any("plan_node" in e for e in events)


class TestModuleReExport:
    """Verify lazy re-export through core.graph.__init__."""

    def test_module_re_export(self):
        """from core.graph import run_mission_graph works via lazy __getattr__."""
        from core.graph import run_mission_graph as imported_fn

        # It should be the exact same function object
        assert imported_fn is run_mission_graph


class TestExceptionLogging:
    """Unexpected exceptions are logged and re-raised."""

    @pytest.mark.asyncio
    async def test_exception_logging_and_reraise(self, caplog):
        """An exception from the graph runner is logged and propagated."""
        # Patch build_graph to raise an unexpected error
        from unittest.mock import patch

        with patch(
            "core.graph.entrypoint.build_graph",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                with caplog.at_level(logging.ERROR, logger="core.graph.entrypoint"):
                    await run_mission_graph(
                        task="will fail",
                        mission_id=0,
                    )

        # The exception should have been logged
        assert any(
            "unexpected error" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_exception_from_runner_propagates(self):
        """An exception from instrumented_run_graph propagates unmodified."""
        from unittest.mock import patch

        async def _exploding_runner(*args, **kwargs):
            raise ValueError("runner exploded")

        with patch(
            "core.graph.entrypoint.instrumented_run_graph",
            side_effect=_exploding_runner,
        ):
            with pytest.raises(ValueError, match="runner exploded"):
                await run_mission_graph(
                    task="kaboom",
                    mission_id=999,
                )


class TestLogging:
    """Entry and exit log lines are emitted."""

    @pytest.mark.asyncio
    async def test_entry_and_exit_logs(self, caplog):
        """Starting and finished log lines are emitted on happy path."""
        with caplog.at_level(logging.INFO, logger="core.graph.entrypoint"):
            with _patch_graph_infra():
                await run_mission_graph(
                    task="log test mission",
                    mission_id=55,
                )

        messages = [r.message for r in caplog.records]
        assert any("starting" in m for m in messages)
        assert any("finished" in m for m in messages)

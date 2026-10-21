"""Public entry-point for the Node Loop Graph.

Provides :func:`run_mission_graph` — the single async function that callers
use to execute a full mission.  It wires together the three lower-level
building blocks:

1. :func:`~core.graph.edges.build_graph`          — graph factory
2. :func:`~core.state.create_initial_state`        — state factory
3. :func:`~core.graph.telemetry.instrumented_run_graph` — instrumented runner

Design notes
------------
* **Zero mutation** — the initial ``GraphState`` is populated via the
  immutable ``{**state, 'field': value}`` pattern.
* **Logging only** — entry/exit and unexpected-exception log lines are
  emitted but never swallowed; exceptions always re-raise.
* **No external dependencies** — no qdrant, numpy, MCP servers or
  ``Orchestrator`` references.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from core.graph.edges import build_graph
from core.graph.telemetry import instrumented_run_graph
from core.state import GraphState, create_initial_state

logger = logging.getLogger(__name__)

__all__: list[str] = ["run_mission_graph"]


async def run_mission_graph(
    task: str,
    mission_id: int,
    *,
    max_attempts: int = 3,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    container: Any = None,
) -> GraphState:
    """Execute a full mission through the Node Loop Graph.

    This is the **recommended** public API for running a mission.  It
    builds the graph, creates a fresh initial state, seeds mission
    metadata, and delegates to ``instrumented_run_graph`` for
    execution with per-node telemetry.

    Parameters
    ----------
    task : str
        Human-readable description of the mission to execute.
    mission_id : int
        Unique numeric identifier for the mission (e.g. database PK).
    max_attempts : int, optional
        Per-step circuit-breaker threshold (default ``3``).
    on_event : Callable[[dict[str, Any]], Awaitable[None]] | None, optional
        Async callback invoked with lifecycle events (``node_start``,
        ``node_end``, ``edge_taken``, ``graph_end``, etc.).
    container : Any, optional
        DI container for trace writing.  Resolved lazily when ``None``.

    Returns
    -------
    GraphState
        The final state after graph execution.  Inspect ``status`` for
        the outcome (``"completed"``, ``"failed"``, ``"circuit_broken"``,
        ``"awaiting_approval"``).

    Raises
    ------
    Exception
        Any exception raised by the graph runner is logged and re-raised.
    """
    logger.info(
        "run_mission_graph: starting — task=%r, mission_id=%s",
        task[:100],
        mission_id,
    )

    t0 = time.perf_counter()

    try:
        # 1. Build the graph
        graph = build_graph()

        # 2. Create initial state with circuit-breaker threshold
        state = create_initial_state(max_attempts=max_attempts)

        # 3. Seed mission metadata (immutable pattern)
        state = {
            **state,
            "metadata": {
                **state["metadata"],
                "task_text": task,
                "mission_id": mission_id,
            },
        }

        # 4. Run with full telemetry instrumentation
        result = await instrumented_run_graph(
            graph,
            state,
            container=container,
            on_event=on_event,
        )

    except Exception:
        duration_ms = (time.perf_counter() - t0) * 1_000
        logger.exception(
            "run_mission_graph: unexpected error after %.1fms — "
            "task=%r, mission_id=%s",
            duration_ms,
            task[:100],
            mission_id,
        )
        raise

    duration_ms = (time.perf_counter() - t0) * 1_000
    node_count = len(result.get("node_history", []))

    logger.info(
        "run_mission_graph: finished — status=%s, duration=%.1fms, "
        "nodes=%d, mission_id=%s",
        result.get("status", "unknown"),
        duration_ms,
        node_count,
        mission_id,
    )

    return result

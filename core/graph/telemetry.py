"""Per-node telemetry instrumentation for the Node Loop Graph.

This module provides two public helpers:

1. :func:`instrumented` — wrap a single node function with observability:
   span creation, wall-clock timing, token-usage deltas, trace-record
   writing, and :class:`~core.bootstrap.ObservabilityContext` bookkeeping.

2. :func:`instrumented_run_graph` — convenience wrapper around
   :func:`~core.graph.runner.run_graph` that instruments **every** node in
   the graph before execution.

Design decisions
----------------
* **No global state** — the ``Container`` (and its ``trace_writer``) is
  passed explicitly or resolved lazily via ``get_container()``.  This makes
  the module unit-testable with a simple mock container.
* **Never raises** — all trace-writing is wrapped in ``try/except`` so that
  observability failures never kill a graph run.
* **Token delta detection** — the wrapper snapshots ``token_usage`` before
  the node runs and diffs after.  This works regardless of whether the node
  calls ``accumulate_tokens`` internally.
* **Immutable state contract preserved** — the wrapper never mutates the
  state dict; it only reads counters for diffing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

__all__: list[str] = ["instrumented", "instrumented_run_graph"]

# Type alias for readability
NodeFn = Callable[["GraphState"], Awaitable["GraphState"]]


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────


def _safe_get_container():
    """Resolve the DI container, returning ``None`` on failure.

    This defers the import of ``core.bootstrap`` to avoid circular imports
    and swallows ``RuntimeError`` when the container hasn't been initialised
    (e.g. during unit tests).
    """
    try:
        from core.bootstrap import get_container  # noqa: WPS433

        return get_container()
    except (ImportError, RuntimeError):
        return None


def _token_delta(before: "TokenUsage", after: "TokenUsage") -> dict[str, float]:
    """Compute the difference between two ``TokenUsage`` snapshots.

    Returns a flat dict suitable for embedding in a trace record.
    """
    return {
        "prompt_tokens": after.prompt_tokens - before.prompt_tokens,
        "completion_tokens": after.completion_tokens - before.completion_tokens,
        "total_tokens": after.total_tokens - before.total_tokens,
        "cost_usd": after.cost_usd - before.cost_usd,
    }


def _write_trace_record(
    container,
    *,
    node_name: str,
    trace_id: str,
    span_id: str,
    parent_span_id: str,
    event: str,
    status: str,
    duration_ms: float | None = None,
    token_delta: dict[str, float] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """Write a single trace record via the container's trace_writer.

    Never raises — all errors are logged and swallowed.
    """
    try:
        from core.tracing import now_iso  # noqa: WPS433
    except ImportError:
        return

    record: dict[str, Any] = {
        "schema_version": 1,
        "ts": now_iso(),
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "server": "graph",
        "tool": f"graph.{node_name}",
        "event": event,
        "status": status,
    }

    if duration_ms is not None:
        record["duration_ms"] = round(duration_ms, 2)
    if token_delta is not None:
        record["token_delta"] = token_delta
    if error_type is not None:
        record["error_type"] = error_type
    if error_message is not None:
        record["error_message"] = error_message[:500]  # bounded

    try:
        if container is not None and hasattr(container, "trace_writer"):
            container.trace_writer.write(record)
        else:
            # Fallback: write directly via tracing module
            from core.tracing import write_record  # noqa: WPS433

            write_record(record)
    except Exception:  # noqa: BLE001
        logger.warning(
            "telemetry: failed to write trace record for node '%s'",
            node_name,
            exc_info=True,
        )


# ──────────────────────────────────────────────────────────────────────
# Public API: per-node instrumentation
# ──────────────────────────────────────────────────────────────────────


def instrumented(
    fn: NodeFn,
    *,
    node_name: str | None = None,
    container=None,
    obs_ctx: "ObservabilityContext | None" = None,
) -> NodeFn:
    """Wrap a node function with observability instrumentation.

    The returned coroutine has the same signature as the original
    ``async def node(state: GraphState) -> GraphState``.

    Parameters
    ----------
    fn:
        The original node function to instrument.
    node_name:
        Human-readable name for trace records.  Falls back to
        ``fn.__name__`` when not specified.
    container:
        Optional DI :class:`~core.bootstrap.Container`.  Resolved lazily
        via ``get_container()`` when ``None``.
    obs_ctx:
        Optional :class:`~core.bootstrap.ObservabilityContext` for the
        current graph run.  When provided, the wrapper creates child
        spans and updates token/visit counters.

    Returns
    -------
    NodeFn
        Instrumented async callable with identical I/O contract.
    """
    name = node_name or getattr(fn, "__name__", "unknown_node")

    async def _wrapper(state: "GraphState") -> "GraphState":
        # -- Resolve container lazily if not injected --
        resolved_container = container or _safe_get_container()

        # -- Create a child span for this node --
        span_ctx = None
        if obs_ctx is not None:
            try:
                span_ctx = obs_ctx.new_span()
                obs_ctx.record_visit()
            except Exception:  # noqa: BLE001
                logger.debug("telemetry: could not create span for '%s'", name)

        # -- Snapshot token usage before node execution --
        token_before = state.get("token_usage")

        # -- Determine span IDs for the trace record --
        span_id = span_ctx.span_id if span_ctx else state.get("span_id", "")
        parent_span_id = state.get("span_id", "")
        trace_id = state.get("trace_id", "")

        # -- Emit start record --
        _write_trace_record(
            resolved_container,
            node_name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            event=f"node.{name}.start",
            status="running",
        )

        # -- Execute the node --
        t0 = time.perf_counter()
        error_occurred = False
        error_type_str = None
        error_msg_str = None

        try:
            result_state = await fn(state)
        except Exception as exc:
            error_occurred = True
            error_type_str = type(exc).__name__
            error_msg_str = str(exc)
            raise  # Re-raise — the runner handles node exceptions
        finally:
            duration_ms = (time.perf_counter() - t0) * 1_000

            # -- Compute token delta --
            td = None
            if token_before is not None:
                try:
                    token_after = (
                        result_state.get("token_usage")  # type: ignore[union-attr]
                        if not error_occurred
                        else token_before
                    )
                    if token_after is not None:
                        td = _token_delta(token_before, token_after)
                        # Update obs_ctx counters
                        if obs_ctx is not None and td["total_tokens"] > 0:
                            try:
                                obs_ctx.record_tokens(int(td["total_tokens"]))
                            except Exception:  # noqa: BLE001
                                pass
                except Exception:  # noqa: BLE001
                    pass

            # -- Emit end/error record --
            _write_trace_record(
                resolved_container,
                node_name=name,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                event=f"node.{name}.{'error' if error_occurred else 'end'}",
                status="error" if error_occurred else "ok",
                duration_ms=duration_ms,
                token_delta=td,
                error_type=error_type_str,
                error_message=error_msg_str,
            )

        return result_state

    # Preserve metadata for introspection
    _wrapper.__name__ = f"instrumented_{name}"
    _wrapper.__qualname__ = f"instrumented_{name}"
    _wrapper.__doc__ = f"Instrumented wrapper for {name}."
    _wrapper.__wrapped__ = fn  # type: ignore[attr-defined]

    return _wrapper


# ──────────────────────────────────────────────────────────────────────
# Public API: full-graph instrumentation wrapper
# ──────────────────────────────────────────────────────────────────────


def instrumented_run_graph(
    graph: "Graph",
    state: "GraphState",
    *,
    container=None,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_from: str | None = None,
) -> Awaitable["GraphState"]:
    """Instrument all nodes in *graph* and then run it.

    This is a convenience wrapper that:

    1. Creates an :class:`~core.bootstrap.ObservabilityContext` for the run.
    2. Wraps every node's ``fn`` with :func:`instrumented`.
    3. Delegates to :func:`~core.graph.runner.run_graph`.
    4. Logs a summary (total duration, nodes visited, tokens consumed).

    Parameters
    ----------
    graph:
        The compiled ``Graph`` with nodes and entry point.
    state:
        Initial ``GraphState``.
    container:
        Optional DI container.  Resolved lazily when ``None``.
    on_event:
        Optional async event callback (forwarded to ``run_graph``).
    resume_from:
        Node name for HITL resume (forwarded to ``run_graph``).

    Returns
    -------
    Awaitable[GraphState]
        Coroutine that yields the final state.  Await it::

            result = await instrumented_run_graph(graph, state)
    """
    return _instrumented_run_graph_impl(
        graph, state,
        container=container,
        on_event=on_event,
        resume_from=resume_from,
    )


async def _instrumented_run_graph_impl(
    graph: "Graph",
    state: "GraphState",
    *,
    container=None,
    on_event=None,
    resume_from=None,
) -> "GraphState":
    """Internal async implementation for instrumented_run_graph."""
    from core.graph.runner import run_graph  # noqa: WPS433

    resolved_container = container or _safe_get_container()

    # -- Create ObservabilityContext for this run --
    obs_ctx = None
    try:
        from core.bootstrap import ObservabilityContext  # noqa: WPS433

        obs_ctx = ObservabilityContext.create(server="graph")
    except (ImportError, Exception):  # noqa: BLE001
        logger.debug("telemetry: could not create ObservabilityContext")

    # -- Instrument every node --
    for node in graph.nodes.values():
        original_fn = getattr(node.fn, "__wrapped__", node.fn)
        node.fn = instrumented(
            original_fn,
            node_name=node.name,
            container=resolved_container,
            obs_ctx=obs_ctx,
        )

    # -- Run --
    t0 = time.perf_counter()
    result = await run_graph(
        graph, state,
        on_event=on_event,
        resume_from=resume_from,
    )
    total_ms = (time.perf_counter() - t0) * 1_000

    # -- Summary log --
    nodes_visited = len(result.get("node_history", []))
    final_status = result.get("status", "unknown")
    token_info = result.get("token_usage")
    total_tokens = getattr(token_info, "total_tokens", 0) if token_info else 0

    logger.info(
        "Graph run complete: status=%s, duration=%.1fms, nodes=%d, tokens=%s, trace=%s",
        final_status,
        total_ms,
        nodes_visited,
        total_tokens,
        result.get("trace_id", "?"),
    )

    # -- Write summary trace record --
    if resolved_container is not None:
        _write_trace_record(
            resolved_container,
            node_name="graph_run",
            trace_id=result.get("trace_id", ""),
            span_id=obs_ctx.span_id if obs_ctx else result.get("span_id", ""),
            parent_span_id="",
            event="graph.run.complete",
            status=final_status,
            duration_ms=total_ms,
            token_delta={
                "total_tokens": total_tokens,
            },
        )

    return result

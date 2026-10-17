"""Motor de execução do Node Loop Graph com dual circuit breaker e HITL.

O ``run_graph`` executa nós async em sequência, avaliando arestas condicionais
após cada nó para determinar o próximo passo.  Dois circuit breakers garantem
terminação:

1. **Per-step** — ``is_circuit_broken(state)`` de ``core.state``
   (``current_attempt > max_attempts``).  Verificado como safety-net no runner;
   a lógica primária vive nas arestas condicionais de ``correct_node``.
2. **Global** — ``MAX_GRAPH_ITERATIONS`` (hard limit de 50 iterações).
   Impede loops infinitos independentemente do estado dos nós.

HITL (Human-in-the-Loop)
-------------------------
Quando um nó seta ``metadata["needs_approval"] = True``, o runner suspende
a execução e retorna o state com ``status="awaiting_approval"`` e
``metadata["_suspended_at"]`` apontando para o nó que solicitou aprovação.

O caller gerencia a aprovação (ex: ``asyncio.Event``) e retoma chamando
``run_graph`` novamente com ``resume_from=state["metadata"]["_suspended_at"]``
— o runner pula a re-execução do nó e avalia diretamente suas arestas para
continuar o fluxo.

Event Callbacks
---------------
O parâmetro ``on_event`` recebe um async callable que é invocado em pontos
chave da execução::

    node_start → node_end → edge_taken → ... → graph_end
                 node_error ↘ graph_end
                 graph_suspended (HITL)

Cada evento é um ``dict`` com pelo menos ``{"type", "trace_id", "iteration"}``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.graph import END, MAX_GRAPH_ITERATIONS, Graph, GraphNode
from core.state import (
    GraphState,
    add_error,
    is_circuit_broken,
    record_node_visit,
)

logger = logging.getLogger(__name__)

__all__: list[str] = ["run_graph"]


# ──────────────────────────────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────────────────────────────


async def _emit(
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None,
    event: dict[str, Any],
) -> None:
    """Fire an event callback if one is registered.  Never raises."""
    if on_event is None:
        return
    try:
        await on_event(event)
    except Exception:  # noqa: BLE001
        logger.warning(
            "on_event callback failed for event type '%s'",
            event.get("type"),
            exc_info=True,
        )


def _resolve_next(node: GraphNode, state: GraphState) -> str:
    """Evaluate edges in order — first match wins.

    Returns the target node name (or ``END``).
    Raises ``RuntimeError`` if no edge matches.
    """
    for edge in node.edges:
        if edge.condition is None or edge.condition(state):
            return edge.target
    raise RuntimeError(
        f"Node '{node.name}' has no matching edge for current state. "
        f"Add a fallback edge with condition=None as the last edge."
    )


def _make_event(
    event_type: str,
    state: GraphState,
    iteration: int,
    **extra: Any,
) -> dict[str, Any]:
    """Build a consistently-shaped event dict."""
    return {
        "type": event_type,
        "trace_id": state.get("trace_id", ""),
        "iteration": iteration,
        **extra,
    }


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


async def run_graph(
    graph: Graph,
    state: GraphState,
    *,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    resume_from: str | None = None,
) -> GraphState:
    """Execute the graph, returning the final ``GraphState``.

    Parameters
    ----------
    graph:
        The compiled ``Graph`` with nodes and entry point.
    state:
        Initial ``GraphState``.  Mutação proibida — cada nó retorna
        um novo dict.
    on_event:
        Optional async callback for SSE/WebSocket event streaming.
        Called with dicts like ``{"type": "node_start", "node": "plan_node"}``.
        Must be an async callable; failures are logged and swallowed.
    resume_from:
        Node name to resume from after HITL approval.  The runner skips
        re-execution of this node and evaluates its edges to continue.
        Typically set to ``state["metadata"]["_suspended_at"]``.

    Returns
    -------
    GraphState
        Final state with ``status`` in
        ``{"completed", "failed", "circuit_broken", "awaiting_approval"}``.

    Raises
    ------
    ValueError
        If the graph is empty, the entry node is missing, or
        ``resume_from`` references a non-existent node.
    RuntimeError
        If a node has no matching edge (missing fallback).
    """
    # ── Validate graph ────────────────────────────────────────────
    if not graph.nodes:
        raise ValueError("Graph has no nodes")

    if resume_from is not None:
        if resume_from not in graph.nodes:
            raise ValueError(
                f"resume_from node '{resume_from}' not found in graph. "
                f"Available: {list(graph.nodes.keys())}"
            )
        current_name = resume_from
        resuming = True
        logger.info(
            "Resuming graph from '%s' (trace=%s)",
            resume_from,
            state.get("trace_id", "?"),
        )
    else:
        if not graph.entry or graph.entry not in graph.nodes:
            raise ValueError(
                f"Graph entry '{graph.entry}' not found in graph nodes. "
                f"Available: {list(graph.nodes.keys())}"
            )
        current_name = graph.entry
        resuming = False
        logger.info(
            "Starting graph at '%s' (trace=%s)",
            graph.entry,
            state.get("trace_id", "?"),
        )

    iteration = 0

    # ── Main loop ─────────────────────────────────────────────────
    while current_name != END:

        # ── Global circuit breaker ────────────────────────────────
        if iteration >= MAX_GRAPH_ITERATIONS:
            logger.error(
                "GLOBAL CIRCUIT BREAKER: %d iterations reached (trace=%s)",
                iteration,
                state.get("trace_id", "?"),
            )
            state = add_error(
                state,
                node_name="runner",
                error_type="GlobalCircuitBreakerTripped",
                message=(
                    f"Global iteration limit ({MAX_GRAPH_ITERATIONS}) exceeded. "
                    f"Last node: '{current_name}'."
                ),
            )
            state = {**state, "status": "circuit_broken"}
            await _emit(
                on_event,
                _make_event(
                    "graph_end", state, iteration,
                    status="circuit_broken",
                    reason="max_iterations",
                    last_node=current_name,
                ),
            )
            return state

        # ── Per-step circuit breaker (safety-net) ─────────────────
        if is_circuit_broken(state):
            logger.warning(
                "PER-STEP CIRCUIT BREAKER: attempt %d > max %d (trace=%s)",
                state["current_attempt"],
                state["max_attempts"],
                state.get("trace_id", "?"),
            )
            state = add_error(
                state,
                node_name="runner",
                error_type="PerStepCircuitBreakerTripped",
                message=(
                    f"Retry budget exhausted: attempt {state['current_attempt']} "
                    f"> max {state['max_attempts']}. "
                    f"Next node would have been '{current_name}'."
                ),
            )
            state = {**state, "status": "circuit_broken"}
            await _emit(
                on_event,
                _make_event(
                    "graph_end", state, iteration,
                    status="circuit_broken",
                    reason="per_step_circuit_breaker",
                    current_attempt=state["current_attempt"],
                    max_attempts=state["max_attempts"],
                ),
            )
            return state

        node = graph.nodes.get(current_name)
        if node is None:
            raise RuntimeError(
                f"Node '{current_name}' referenced but not found in graph. "
                f"Available: {list(graph.nodes.keys())}"
            )

        # ── Resume: skip execution, evaluate edges ────────────────
        if resuming:
            await _emit(
                on_event,
                _make_event("node_resumed", state, iteration, node=current_name),
            )
            resuming = False
            # Fall through to edge evaluation below

        else:
            # ── Execute node ──────────────────────────────────────
            await _emit(
                on_event,
                _make_event("node_start", state, iteration, node=current_name, _state=state),
            )

            try:
                state = await node.fn(state)
            except Exception as exc:
                logger.exception(
                    "Node '%s' raised %s: %s",
                    current_name,
                    type(exc).__name__,
                    exc,
                )
                state = add_error(
                    state,
                    node_name=current_name,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                state = {**state, "status": "failed"}
                await _emit(
                    on_event,
                    _make_event(
                        "node_error", state, iteration,
                        node=current_name,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )
                await _emit(
                    on_event,
                    _make_event(
                        "graph_end", state, iteration,
                        status="failed",
                        reason="node_exception",
                        node=current_name,
                    ),
                )
                return state

            # ── Record visit ──────────────────────────────────────
            state = record_node_visit(state, current_name)

            await _emit(
                on_event,
                _make_event(
                    "node_end", state, iteration,
                    node=current_name,
                    status=state.get("status", ""),
                    _state=state,
                ),
            )

            # ── HITL check ────────────────────────────────────────
            metadata = state.get("metadata", {})
            if metadata.get("needs_approval"):
                logger.info(
                    "HITL: node '%s' requests approval (trace=%s)",
                    current_name,
                    state.get("trace_id", "?"),
                )
                # Store resume point for the caller
                updated_metadata = {**metadata, "_suspended_at": current_name}
                state = {
                    **state,
                    "status": "awaiting_approval",
                    "metadata": updated_metadata,
                }
                await _emit(
                    on_event,
                    _make_event(
                        "graph_suspended", state, iteration,
                        node=current_name,
                        reason="awaiting_approval",
                    ),
                )
                return state

        # ── Evaluate edges → next node ────────────────────────────
        try:
            next_name = _resolve_next(node, state)
        except RuntimeError as exc:
            logger.exception("Edge resolution failed at '%s'", current_name)
            state = add_error(
                state,
                node_name=current_name,
                error_type="EdgeResolutionError",
                message=str(exc),
            )
            state = {**state, "status": "failed"}
            await _emit(
                on_event,
                _make_event(
                    "graph_end", state, iteration,
                    status="failed",
                    reason="no_matching_edge",
                    node=current_name,
                ),
            )
            return state

        logger.debug(
            "Edge: '%s' -> '%s' (iteration=%d)",
            current_name,
            next_name,
            iteration,
        )
        await _emit(
            on_event,
            _make_event(
                "edge_taken", state, iteration,
                from_node=current_name,
                to_node=next_name,
            ),
        )

        current_name = next_name
        iteration += 1

    # ── Graph reached END ─────────────────────────────────────────
    terminal_statuses = ("completed", "failed", "circuit_broken")
    if state.get("status") not in terminal_statuses:
        state = {**state, "status": "completed"}

    await _emit(
        on_event,
        _make_event(
            "graph_end", state, iteration,
            status=state["status"],
            reason="reached_end",
        ),
    )

    logger.info(
        "Graph finished: status=%s, iterations=%d, nodes_visited=%d, trace=%s",
        state["status"],
        iteration,
        len(state.get("node_history", [])),
        state.get("trace_id", "?"),
    )

    return state

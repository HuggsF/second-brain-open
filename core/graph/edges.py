"""3 roteadores condicionais e ``build_graph()`` factory.

Roteadores
----------
Cada roteador é um conjunto de funções-predicado puras sobre o ``GraphState``
que determinam qual aresta seguir.  As arestas de cada nó são avaliadas em
ordem — a **primeira match ganha**.  A última aresta é sempre incondicional
(fallback).

1. **gate_router**     — pós ``gate_node``: block → END, default → ``route_node``
2. **validate_router** — pós ``validate_node``: fail → ``correct_node``,
   more_steps → ``execute_node``, done → ``post_gate_node``
3. **correct_router**  — pós ``correct_node``: circuit_broken → END,
   retry → ``execute_node``

Grafo
-----
::

    START → plan_node → gate_node →[block]→ END(failed)
                                  →[proceed]→ route_node → execute_node → validate_node
                                               →[pass + more steps]→ execute_node
                                               →[pass + done]→ post_gate_node → END(completed)
                                               →[fail]→ correct_node →[circuit_broken]→ END
                                                                      →[retry]→ execute_node

``build_graph()``
-----------------
Factory que monta e retorna o ``Graph`` com todos os nós e arestas
configurados, pronto para ser executado via ``run_graph()``.
"""

from __future__ import annotations

import logging
from typing import Any

from core.graph import END, Graph, GraphEdge, GraphNode
from core.graph.nodes import (
    correct_node,
    execute_node,
    gate_node,
    plan_node,
    post_gate_node,
    route_node,
    validate_node,
)
from core.state import GraphState, is_circuit_broken

logger = logging.getLogger(__name__)

__all__: list[str] = ["build_graph"]


# ──────────────────────────────────────────────────────────────────────
# 1. Gate Router — post gate_node
# ──────────────────────────────────────────────────────────────────────


def _gate_blocked(state: GraphState) -> bool:
    """True when mission guard gates blocked the mission (RED semaphore).

    ``gate_node`` sets ``status="failed"`` when ``check_mission`` returns
    ``action="block"``.
    """
    return state.get("status") == "failed"


# ──────────────────────────────────────────────────────────────────────
# 2. Validate Router — post validate_node
# ──────────────────────────────────────────────────────────────────────


def _has_step_failure(state: GraphState) -> bool:
    """True when the last step result indicates a failure needing correction.

    Checks the last entry in ``metadata["step_results"]`` for:
    - ``error is True`` — explicit error from ``execute_node``
      (e.g. ``InvalidAgent``)
    - ``refused`` — policy denial from ``broker.call``
    """
    results: list[dict[str, Any]] = (
        state.get("metadata", {}).get("step_results", [])
    )
    if not results:
        return False
    last = results[-1]
    # Skip unbound steps — they're not failures
    if last.get("unbound"):
        return False
    return last.get("error") is True or bool(last.get("refused"))


def _has_more_steps(state: GraphState) -> bool:
    """True when there are remaining steps to execute.

    Compares ``metadata["current_step_index"]`` against ``len(steps)``.
    """
    metadata = state.get("metadata", {})
    step_index: int = metadata.get("current_step_index", 0)
    steps: list[dict[str, Any]] = metadata.get("steps", [])
    return step_index < len(steps)


# ──────────────────────────────────────────────────────────────────────
# 3. Correct Router — post correct_node
# ──────────────────────────────────────────────────────────────────────


def _is_circuit_broken(state: GraphState) -> bool:
    """True when the per-step circuit breaker has tripped.

    ``correct_node`` increments ``current_attempt`` and sets
    ``status="circuit_broken"`` when the threshold is exceeded.
    This edge condition confirms the state for routing to END.
    """
    return state.get("status") == "circuit_broken"


# ──────────────────────────────────────────────────────────────────────
# build_graph() Factory
# ──────────────────────────────────────────────────────────────────────


def build_graph() -> Graph:
    """Build and return the complete mission execution graph.

    Returns a ``Graph`` with 7 nodes and all edges wired according to
    the Node Loop Graph architecture.  The graph is ready to be executed
    via ``run_graph(graph, state)``.

    Node wiring::

        plan_node
          └─→ gate_node
                ├─[blocked]→ END
                └─→ route_node
                      └─→ execute_node
                            └─→ validate_node
                                  ├─[fail]→ correct_node
                                  │           ├─[circuit_broken]→ END
                                  │           └─[retry]→ execute_node
                                  ├─[more_steps]→ execute_node
                                  └─[done]→ post_gate_node
                                              └─→ END

    Returns
    -------
    Graph
        Compiled graph with ``entry="plan_node"``.
    """
    graph = Graph(
        nodes={
            # ── plan_node → gate_node (unconditional) ─────────────
            "plan_node": GraphNode(
                name="plan_node",
                fn=plan_node,
                edges=[
                    GraphEdge(target="gate_node"),  # always
                ],
            ),
            # ── gate_node → [blocked] END | [proceed] route_node ──
            "gate_node": GraphNode(
                name="gate_node",
                fn=gate_node,
                edges=[
                    GraphEdge(target=END, condition=_gate_blocked),
                    GraphEdge(target="route_node"),  # default: proceed
                ],
            ),
            # ── route_node → execute_node (unconditional) ─────────
            "route_node": GraphNode(
                name="route_node",
                fn=route_node,
                edges=[
                    GraphEdge(target="execute_node"),  # always
                ],
            ),
            # ── execute_node → validate_node (unconditional) ──────
            "execute_node": GraphNode(
                name="execute_node",
                fn=execute_node,
                edges=[
                    GraphEdge(target="validate_node"),  # always
                ],
            ),
            # ── validate_node → [fail] correct | [more] exec | [done] post
            "validate_node": GraphNode(
                name="validate_node",
                fn=validate_node,
                edges=[
                    GraphEdge(
                        target="correct_node",
                        condition=_has_step_failure,
                    ),
                    GraphEdge(
                        target="execute_node",
                        condition=_has_more_steps,
                    ),
                    GraphEdge(target="post_gate_node"),  # default: done
                ],
            ),
            # ── correct_node → [CB tripped] END | [retry] execute ─
            "correct_node": GraphNode(
                name="correct_node",
                fn=correct_node,
                edges=[
                    GraphEdge(
                        target=END,
                        condition=_is_circuit_broken,
                    ),
                    GraphEdge(target="execute_node"),  # default: retry
                ],
            ),
            # ── post_gate_node → END (unconditional) ─────────────
            "post_gate_node": GraphNode(
                name="post_gate_node",
                fn=post_gate_node,
                edges=[
                    GraphEdge(target=END),  # always
                ],
            ),
        },
        entry="plan_node",
    )

    logger.info(
        "build_graph: %d nodes, entry='%s'",
        len(graph.nodes),
        graph.entry,
    )

    return graph

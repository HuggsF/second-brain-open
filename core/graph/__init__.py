"""API pública do Node Loop Graph — tipos, constantes e re-exports.

O pacote ``core.graph`` implementa uma arquitetura de grafo de nós com loops
de auto-correção, **sem dependência de LangGraph**.  O motor de execução é
100 % stdlib + asyncio.

Exporta
-------
- **Tipos:**  ``GraphEdge``, ``GraphNode``, ``Graph``
- **Constantes:** ``END``, ``MAX_GRAPH_ITERATIONS``
- **Motor:**  ``run_graph``   (re-export de ``core.graph.runner``)
- **Factory:** ``build_graph`` (re-export de ``core.graph.edges``)

Dual Circuit Breaker
--------------------
1. *Per-step* — ``is_circuit_broken(state)`` de ``core.state``
   (``current_attempt > max_attempts``).
2. *Global* — ``MAX_GRAPH_ITERATIONS`` no runner — hard limit absoluto
   que impede loops infinitos independentemente do estado.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.state import GraphState

# ──────────────────────────────────────────────────────────────────────
# Sentinelas e Constantes
# ──────────────────────────────────────────────────────────────────────

END: str = "__END__"
"""Sentinela de término — quando uma aresta roteia para ``END``, o grafo para."""

MAX_GRAPH_ITERATIONS: int = 50
"""Hard limit global de iterações do runner.

Qualquer grafo que atingir esse número de passos é encerrado com
``status='circuit_broken'`` independentemente do estado dos nós.
"""

# ──────────────────────────────────────────────────────────────────────
# Tipos do Grafo
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Aresta condicional ou incondicional entre dois nós.

    As arestas de um nó são avaliadas **em ordem** — a primeira cuja
    ``condition`` retorne ``True`` (ou cuja ``condition`` seja ``None``)
    determina o próximo nó.

    Parameters
    ----------
    target:
        Nome do nó destino, ou ``END`` para encerrar o grafo.
    condition:
        Predicado puro sobre o ``GraphState``.  ``None`` significa
        aresta incondicional (default / fallback).
    """

    target: str
    condition: Callable[[GraphState], bool] | None = None


@dataclass(slots=True)
class GraphNode:
    """Nó do grafo com função async e lista de arestas de saída.

    A função ``fn`` recebe o ``GraphState`` atual e retorna um **novo**
    ``GraphState`` — nunca muta o state original
    (padrão ``{**state, 'field': new_value}``).

    As ``edges`` são avaliadas em ordem após a execução do nó;
    a primeira match ganha.

    Parameters
    ----------
    name:
        Identificador único do nó (ex: ``"plan_node"``).
    fn:
        Coroutine ``async def(state: GraphState) -> GraphState``.
    edges:
        Lista ordenada de ``GraphEdge``.  A última aresta tipicamente
        tem ``condition=None`` como fallback incondicional.
    """

    name: str
    fn: Callable[[GraphState], Awaitable[GraphState]]
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass(slots=True)
class Graph:
    """Grafo de execução com nós e ponto de entrada.

    Construído via ``build_graph()`` e executado via ``run_graph()``.

    Parameters
    ----------
    nodes:
        Mapa ``{nome: GraphNode}`` de todos os nós registrados.
    entry:
        Nome do nó de entrada (primeiro a ser executado).
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    entry: str = ""


# ──────────────────────────────────────────────────────────────────────
# API Pública
# ──────────────────────────────────────────────────────────────────────

__all__: list[str] = [
    # Constantes
    "END",
    "MAX_GRAPH_ITERATIONS",
    # Tipos
    "Graph",
    "GraphEdge",
    "GraphNode",
    # Motor + Factory + Entry-point (lazy re-exports)
    "build_graph",
    "run_graph",
    "run_mission_graph",
]


def __getattr__(name: str):
    """Lazy re-exports — carregados sob demanda para evitar imports circulares.

    ``run_graph``          ← ``core.graph.runner``
    ``build_graph``        ← ``core.graph.edges``
    ``run_mission_graph``  ← ``core.graph.entrypoint``
    """
    if name == "run_graph":
        from core.graph.runner import run_graph  # noqa: WPS433

        return run_graph
    if name == "build_graph":
        from core.graph.edges import build_graph  # noqa: WPS433

        return build_graph
    if name == "run_mission_graph":
        from core.graph.entrypoint import run_mission_graph  # noqa: WPS433

        return run_mission_graph
    raise AttributeError(f"module 'core.graph' has no attribute {name!r}")

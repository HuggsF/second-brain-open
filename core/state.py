"""Typed, immutable State structure that travels between nodes in the graph architecture.

The ``GraphState`` TypedDict is the single source of truth for every graph
execution.  Each node receives the current state, performs work, and returns a
*new* state dict — no mutation allowed.  Helper functions in this module
enforce that contract via the ``{**state, 'field': new_value}`` pattern.

State-machine semantics
-----------------------

* ``status`` progresses through ``VALID_STATUSES``:
  ``pending → running → completed | failed | circuit_broken``.
* ``current_attempt`` starts at 1 and is bumped by ``increment_attempt``.
  When ``current_attempt > max_attempts`` the circuit breaker trips and
  ``is_circuit_broken`` returns ``True``.
* ``errors`` accumulate across attempts so the caller can inspect the full
  history after the run finishes.
* ``node_history`` records the ordered list of node names visited, which is
  useful for debugging and for conditional routing.
* ``token_usage`` is an additive accumulator — call ``accumulate_tokens``
  after every LLM invocation to keep a running total.
* ``trace_id`` / ``span_id`` follow W3C Trace Context shapes (32 / 16 hex
  chars) so they can plug directly into OpenTelemetry exporters later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypedDict

from core.tracing import new_span_id, new_trace_id

__all__: list[str] = [
    # Dataclasses
    "Message",
    "NodeError",
    "TokenUsage",
    # TypedDict
    "GraphState",
    # Constants
    "VALID_STATUSES",
    # Factory
    "create_initial_state",
    # Helpers
    "add_error",
    "add_message",
    "increment_attempt",
    "is_circuit_broken",
    "record_node_visit",
    "accumulate_tokens",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "completed",
    "failed",
    "circuit_broken",
)

# ---------------------------------------------------------------------------
# Frozen dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Message:
    """A single message in the conversation history.

    Attributes:
        role: The sender role (e.g. ``"user"``, ``"assistant"``, ``"system"``).
        content: The textual content of the message.
        timestamp: ISO-8601 timestamp of when the message was created.
    """

    role: str
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    )


@dataclass(frozen=True, slots=True)
class NodeError:
    """An error captured during node execution.

    Attributes:
        node_name: The graph-node that raised the error.
        error_type: A short classification (e.g. ``"ValueError"``, ``"TimeoutError"``).
        message: Human-readable error description.
        timestamp: ISO-8601 timestamp of when the error occurred.
        attempt: The ``current_attempt`` value at the time of the error.
    """

    node_name: str
    error_type: str
    message: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    )
    attempt: int = 1


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Cumulative token-usage counters for the entire graph run.

    All fields default to ``0.0`` so the struct is always safe to read even
    before the first LLM call.

    Attributes:
        prompt_tokens: Total prompt / input tokens consumed.
        completion_tokens: Total completion / output tokens generated.
        total_tokens: Sum of prompt and completion tokens.
        cost_usd: Estimated cost in US dollars.
    """

    prompt_tokens: float = 0.0
    completion_tokens: float = 0.0
    total_tokens: float = 0.0
    cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# GraphState — the canonical LangGraph-compatible typed dict
# ---------------------------------------------------------------------------


class GraphState(TypedDict):
    """The immutable state bag that flows through every node in the graph.

    This ``TypedDict`` is fully compatible with LangGraph's ``StateGraph``
    annotation-based state.  Nodes receive it, may inspect any field, and
    return a partial dict with only the fields they wish to update.

    See the module docstring for state-machine semantics.
    """

    messages: list[Message]
    current_attempt: int
    max_attempts: int
    errors: list[NodeError]
    metadata: dict[str, Any]
    trace_id: str
    span_id: str
    node_history: list[str]
    token_usage: TokenUsage
    status: str


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_initial_state(
    trace_id: str | None = None,
    max_attempts: int = 3,
) -> GraphState:
    """Return a fresh ``GraphState`` populated with sensible defaults.

    Args:
        trace_id: Optional W3C trace id (32 hex chars).  A new one is
            generated when ``None``.
        max_attempts: Circuit-breaker threshold.  After this many attempts
            ``is_circuit_broken`` will return ``True``.

    Returns:
        A new ``GraphState`` dict ready to be fed into the first node.
    """
    return GraphState(
        messages=[],
        current_attempt=1,
        max_attempts=max_attempts,
        errors=[],
        metadata={},
        trace_id=trace_id or new_trace_id(),
        span_id=new_span_id(),
        node_history=[],
        token_usage=TokenUsage(),
        status="pending",
    )


# ---------------------------------------------------------------------------
# Immutable helper functions
# ---------------------------------------------------------------------------


def add_error(
    state: GraphState,
    node_name: str,
    error_type: str,
    message: str,
) -> GraphState:
    """Return a **new** state with a ``NodeError`` appended to ``errors``.

    The original ``state`` is never mutated.

    Args:
        state: Current graph state.
        node_name: The node where the error originated.
        error_type: Short error classification.
        message: Human-readable description.

    Returns:
        Updated ``GraphState`` with the new error appended.
    """
    error = NodeError(
        node_name=node_name,
        error_type=error_type,
        message=message,
        attempt=state["current_attempt"],
    )
    return {**state, "errors": [*state["errors"], error]}  # type: ignore[return-value]


def add_message(
    state: GraphState,
    role: str,
    content: str,
) -> GraphState:
    """Return a **new** state with a ``Message`` appended to ``messages``.

    Args:
        state: Current graph state.
        role: Sender role (``"user"``, ``"assistant"``, ``"system"``).
        content: Textual content.

    Returns:
        Updated ``GraphState``.
    """
    msg = Message(role=role, content=content)
    return {**state, "messages": [*state["messages"], msg]}  # type: ignore[return-value]


def increment_attempt(state: GraphState) -> GraphState:
    """Return a **new** state with ``current_attempt`` incremented by one.

    Args:
        state: Current graph state.

    Returns:
        Updated ``GraphState``.
    """
    return {**state, "current_attempt": state["current_attempt"] + 1}  # type: ignore[return-value]


def is_circuit_broken(state: GraphState) -> bool:
    """Return ``True`` when the retry budget is exhausted.

    The circuit is considered broken when ``current_attempt`` exceeds
    ``max_attempts``.

    Args:
        state: Current graph state.

    Returns:
        Whether the circuit breaker has tripped.
    """
    return state["current_attempt"] > state["max_attempts"]


def record_node_visit(state: GraphState, node_name: str) -> GraphState:
    """Return a **new** state with *node_name* appended to ``node_history``.

    Args:
        state: Current graph state.
        node_name: The node that was just executed.

    Returns:
        Updated ``GraphState``.
    """
    return {**state, "node_history": [*state["node_history"], node_name]}  # type: ignore[return-value]


def accumulate_tokens(
    state: GraphState,
    prompt: int,
    completion: int,
    cost: float = 0.0,
) -> GraphState:
    """Return a **new** state with token counts added to the running totals.

    Args:
        state: Current graph state.
        prompt: Number of prompt tokens used in the latest call.
        completion: Number of completion tokens used in the latest call.
        cost: Estimated cost in USD for the latest call.

    Returns:
        Updated ``GraphState`` with accumulated ``token_usage``.
    """
    prev = state["token_usage"]
    new_usage = TokenUsage(
        prompt_tokens=prev.prompt_tokens + prompt,
        completion_tokens=prev.completion_tokens + completion,
        total_tokens=prev.total_tokens + prompt + completion,
        cost_usd=prev.cost_usd + cost,
    )
    return {**state, "token_usage": new_usage}  # type: ignore[return-value]

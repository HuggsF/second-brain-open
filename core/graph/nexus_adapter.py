"""Streaming adapter: graph runner events → Nexus event-protocol.js.

Translates internal graph lifecycle events (``node_start``, ``node_end``,
``edge_taken``, ``graph_end``, ``graph_suspended``) into the wire format
expected by the Nexus React frontend (``event-protocol.js``).

Design decisions
----------------
* **Data-driven mapping** — node-to-agent translation lives in a plain
  ``dict`` (``DEFAULT_NODE_AGENT_MAP``), not in code.  Extending the graph
  with new nodes only requires adding a row.
* **State accessor** — for ``execute_node`` the adapter resolves the agent
  dynamically from ``state["metadata"]`` via the ``__step__`` sentinel.
* **Streaming** — each translated event is sent immediately via the
  injected ``send`` callback (typically ``websocket.send``).  No buffering.
* **Never raises** — translation/send errors are logged and swallowed so
  that observability failures never kill a graph run.

Wire format (event-protocol.js)::

    {
        "schemaVersion": 1,
        "id":            "evt:<missionId>:<hex8>",
        "missionId":     <int>,
        "sequence":      <int>,          # monotonically increasing
        "agentId":       "<role>",       # one of ALLOWED_ROLES
        "type":          "<event_type>", # status_change | message | ...
        "timestamp":     <float>,        # ms since epoch
        "payload":       { ... }
    }
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

__all__: list[str] = [
    "NexusEventAdapter",
    "DEFAULT_NODE_AGENT_MAP",
    "STEP_AGENT_SENTINEL",
]

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

STEP_AGENT_SENTINEL: str = "__step__"
"""Sentinel value in the node-agent map indicating the agent should be
resolved dynamically from the current step's metadata."""

DEFAULT_NODE_AGENT_MAP: dict[str, str] = {
    "plan_node": "manager",
    "gate_node": "manager",
    "route_node": "manager",
    "execute_node": STEP_AGENT_SENTINEL,
    "validate_node": "reviewer",
    "correct_node": "manager",
    "post_gate_node": "reviewer",
}
"""Default mapping from graph node names to Nexus agent roles.

Use ``STEP_AGENT_SENTINEL`` for nodes where the agent must be resolved
from the current step's ``"agent"`` field in state metadata.
"""

# Bubble text defaults per node (used only if no better context)
_DEFAULT_BUBBLES: dict[str, str] = {
    "plan_node": "Nova missão recebida! Analisando...",
    "gate_node": "Verificando portões de segurança...",
    "route_node": "Distribuindo responsabilidades...",
    "execute_node": "Trabalhando...",
    "validate_node": "Validando resultado...",
    "correct_node": "Corrigindo e retentando...",
    "post_gate_node": "Revisando entregas finais...",
}

# Max UTF-16 limits from event-protocol.js (backend/orchestrator.py L96–97)
_MAX_BUBBLE_CHARS: int = 240


# ──────────────────────────────────────────────────────────────────────
# Adapter
# ──────────────────────────────────────────────────────────────────────


class NexusEventAdapter:
    """Streaming adapter that translates graph events to Nexus protocol.

    Parameters
    ----------
    mission_id : int
        The mission ID echoed in every Nexus event.
    send : Callable[[dict[str, Any]], Awaitable[None]]
        Async callable that delivers a single Nexus event dict to the
        transport layer (e.g. ``websocket.send(json.dumps(event))``).
    node_agent_map : dict[str, str] | None
        Custom node→agent mapping.  Defaults to ``DEFAULT_NODE_AGENT_MAP``.
    """

    def __init__(
        self,
        mission_id: int,
        send: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        node_agent_map: dict[str, str] | None = None,
    ) -> None:
        self.mission_id = mission_id
        self._send = send
        self._seq = 0
        self._node_agent_map = node_agent_map or dict(DEFAULT_NODE_AGENT_MAP)
        self._state: dict[str, Any] | None = None

    # ── State accessor ────────────────────────────────────────────

    def set_state(self, state: dict[str, Any]) -> None:
        """Update the adapter's state snapshot.

        Called by the entrypoint wrapper after each node execution so
        the adapter can resolve step-level metadata (agent, bubble, etc.).
        """
        self._state = state

    # ── Public callback ───────────────────────────────────────────

    async def on_event(self, event: dict[str, Any]) -> None:
        """Callback for ``run_mission_graph(on_event=adapter.on_event)``.

        Translates a single graph runner event into zero or more Nexus
        events and sends each one immediately.  Never raises.
        """
        try:
            # Auto-sync state from runner events (piggybacked in _state)
            if "_state" in event:
                self._state = event["_state"]

            nexus_events = self._translate(event)
            for ne in nexus_events:
                await self._send(ne)
        except Exception:  # noqa: BLE001
            logger.warning(
                "nexus_adapter: failed to translate/send event type=%s",
                event.get("type"),
                exc_info=True,
            )

    # ── Internal helpers ──────────────────────────────────────────

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _next_event_id(self) -> str:
        return f"evt:{self.mission_id}:{uuid.uuid4().hex[:8]}"

    def _resolve_agent(self, node_name: str) -> str:
        """Resolve the Nexus agentId for a given graph node."""
        mapped = self._node_agent_map.get(node_name, "manager")

        if mapped == STEP_AGENT_SENTINEL and self._state is not None:
            metadata = self._state.get("metadata", {})
            steps: list[dict[str, Any]] = metadata.get("steps", [])
            step_index: int = metadata.get("current_step_index", 0)
            # current_step_index points to the NEXT step after execute_node
            # increments it, so the just-executed step is at index - 1.
            actual_index = max(0, step_index - 1)
            if actual_index < len(steps):
                return steps[actual_index].get("agent", "manager")
            return "manager"

        if mapped == STEP_AGENT_SENTINEL:
            return "manager"  # fallback when no state available

        return mapped

    def _get_step_bubble(self) -> str:
        """Resolve the bubble text from the current step's metadata."""
        if self._state is None:
            return "Trabalhando..."
        metadata = self._state.get("metadata", {})
        steps: list[dict[str, Any]] = metadata.get("steps", [])
        step_index: int = metadata.get("current_step_index", 0)
        actual_index = max(0, step_index - 1)
        if actual_index < len(steps):
            return steps[actual_index].get("bubble", "Trabalhando...")
        return "Trabalhando..."

    def _nexus_event(
        self,
        agent_id: str,
        event_type: str,
        **payload: Any,
    ) -> dict[str, Any]:
        """Build a Nexus event dict in event-protocol.js format."""
        # Truncate bubble if present
        if isinstance(payload.get("bubble"), str):
            payload["bubble"] = payload["bubble"][:_MAX_BUBBLE_CHARS]
        return {
            "schemaVersion": 1,
            "id": self._next_event_id(),
            "missionId": self.mission_id,
            "sequence": self._next_seq(),
            "agentId": agent_id,
            "type": event_type,
            "timestamp": time.time() * 1000,
            "payload": {k: v for k, v in payload.items() if v is not None},
        }

    def _translate(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Translate a single graph event into Nexus event(s)."""
        event_type = event.get("type", "")
        node = event.get("node", "")

        if event_type == "node_start":
            return self._on_node_start(node)
        if event_type == "node_end":
            return self._on_node_end(node, event)
        if event_type == "node_error":
            return self._on_node_error(node, event)
        if event_type == "graph_end":
            return self._on_graph_end(event)
        if event_type == "graph_suspended":
            return self._on_graph_suspended(node)
        # edge_taken, node_resumed → no Nexus equivalent
        return []

    def _on_node_start(self, node: str) -> list[dict[str, Any]]:
        agent = self._resolve_agent(node)
        bubble = _DEFAULT_BUBBLES.get(node, "Trabalhando...")

        if node == "execute_node":
            bubble = self._get_step_bubble()

        if node == "route_node":
            agents = []
            if self._state is not None:
                agents = self._state.get("metadata", {}).get(
                    "agents_involved", []
                )
            return [
                self._nexus_event(
                    agent,
                    "collaboration",
                    subtype="distribute",
                    to=agents,
                    bubble=bubble,
                    **{"from": "manager"},
                ),
            ]

        status = "thinking" if node == "plan_node" else "working"
        return [
            self._nexus_event(
                agent, "status_change", status=status, bubble=bubble,
            ),
        ]

    def _on_node_end(
        self, node: str, event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        agent = self._resolve_agent(node)
        events: list[dict[str, Any]] = []

        if node == "execute_node":
            # Agent finished working → done
            events.append(
                self._nexus_event(agent, "status_change", status="done", progress=100),
            )

        if node == "post_gate_node":
            events.append(
                self._nexus_event(agent, "status_change", status="done", progress=100),
            )

        return events

    def _on_node_error(
        self, node: str, event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        error_msg = event.get("error_message", "Erro interno")
        return [
            self._nexus_event(
                "manager",
                "message",
                message=f"❌ Erro em {node}: {error_msg}",
                bubble="❌ Erro interno",
            ),
        ]

    def _on_graph_end(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        status = event.get("status", "unknown")
        events: list[dict[str, Any]] = []

        if status == "completed":
            events.append(
                self._nexus_event(
                    "manager", "completion",
                    bubble="Missão concluída! 🎉", progress=100,
                ),
            )
        elif status == "failed":
            reason = event.get("reason", "")
            events.append(
                self._nexus_event(
                    "manager", "message",
                    message=f"Missão bloqueada: {reason}",
                    bubble="Missão bloqueada",
                ),
            )
        elif status == "circuit_broken":
            events.append(
                self._nexus_event(
                    "manager", "message",
                    message="Circuit breaker ativado — tentativas esgotadas.",
                    bubble="Circuit breaker ativado",
                ),
            )

        return events

    def _on_graph_suspended(self, node: str) -> list[dict[str, Any]]:
        return [
            self._nexus_event(
                "manager",
                "approval_request",
                bubble="Os portões pedem aprovação para esta missão. Aprovar?",
            ),
        ]

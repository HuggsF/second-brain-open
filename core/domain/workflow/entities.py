"""Workflow domain entities — canonical types for missions, steps and events.

These types define the shared vocabulary between:
- backend.orchestrator (execution engine)
- backend.ws_server (WebSocket transport)
- nexus/src/context.jsx (React state — via event-protocol.js)

Do NOT import any I/O, HTTP, or WebSocket libraries here.
This module has zero dependencies outside the standard library.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

from core.domain.nexus.entities import (
    ALLOWED_ROLES,
    AUTO_TOOLS,
    MISSION_EVENT_FIELDS,
    MISSION_STATUSES,
)


# ── Mission ID type ───────────────────────────────────────────────────────────
# Canonical type: positive int, 0 < id <= MAX_SAFE_INTEGER (2^53 - 1)
# Must match ws_server.py MAX_SAFE_INTEGER validation.
MAX_MISSION_ID: int = 2 ** 53 - 1


def is_valid_mission_id(value: Any) -> bool:
    """Return True if value is a valid missionId (positive int, JS-safe)."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 < value <= MAX_MISSION_ID
    )


# ── Step ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Step:
    """A single agent action within a mission.

    agent: one of ALLOWED_ROLES (from nexus domain)
    tool:  one of AUTO_TOOLS for auto-execution, or other ALLOWED_TOOLS needing approval
    input: tool-specific keyword arguments
    bubble: short text displayed above the agent station in the UI
    """
    agent: str
    tool: str
    input: Dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    bubble: str = ""

    def __post_init__(self):
        if self.agent not in ALLOWED_ROLES:
            raise ValueError(f"Step.agent '{self.agent}' is not in ALLOWED_ROLES")
        if not isinstance(self.tool, str) or not self.tool.strip():
            raise ValueError("Step.tool must be a non-empty string")

    @property
    def requires_approval(self) -> bool:
        """True if this tool requires explicit human approval before execution."""
        return self.tool not in AUTO_TOOLS


# ── Mission ───────────────────────────────────────────────────────────────────

@dataclass
class Mission:
    """A complete multi-agent mission.

    id: canonical missionId (positive int, JS-safe)
    task: original task text from the user
    steps: ordered list of Steps to execute
    status: current MISSION_STATUSES value
    """
    id: int
    task: str
    steps: List[Step] = field(default_factory=list)
    status: str = "pending"

    def __post_init__(self):
        if not is_valid_mission_id(self.id):
            raise ValueError(f"Mission.id must be a positive int <= {MAX_MISSION_ID}, got {self.id!r}")
        if not isinstance(self.task, str) or not self.task.strip():
            raise ValueError("Mission.task must be a non-empty string")
        if self.status not in MISSION_STATUSES:
            raise ValueError(f"Mission.status '{self.status}' not in MISSION_STATUSES")


# ── Event ─────────────────────────────────────────────────────────────────────

# Canonical event types (must match event-protocol.js on the Nexus frontend)
EVENT_TYPES: FrozenSet[str] = frozenset({
    "status_change",    # agentId changed operational status
    "message",          # agentId produced a text output
    "collaboration",    # handoff or coordination between agents
    "tool_result",      # agentId executed a tool (auto or approved)
    "approval_request", # agentId is waiting for human approval
    "completion",       # mission finished successfully
})


@dataclass(frozen=True)
class AgentEvent:
    """A single event emitted during mission execution.

    Fields match MISSION_EVENT_FIELDS from nexus.entities and event-protocol.js.
    """
    mission_id: int   # missionId (camelCase in JSON transport)
    agent_id: str     # agentId
    event_type: str   # type
    sequence: int     # monotonically increasing within mission
    timestamp_ms: float  # timestamp (ms since epoch, JS-compatible)
    payload: Dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    event_id: Optional[str] = None  # id (optional, set by Orchestrator)

    def __post_init__(self):
        if not is_valid_mission_id(self.mission_id):
            raise ValueError(f"AgentEvent.mission_id invalid: {self.mission_id!r}")
        if self.agent_id not in ALLOWED_ROLES:
            raise ValueError(f"AgentEvent.agent_id '{self.agent_id}' not in ALLOWED_ROLES")
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"AgentEvent.event_type '{self.event_type}' not in EVENT_TYPES")
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("AgentEvent.sequence must be a positive int")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the wire format expected by event-protocol.js."""
        return {
            "schemaVersion": 1,
            "id": self.event_id or f"evt:{self.mission_id}:{self.sequence}",
            "missionId": self.mission_id,
            "agentId": self.agent_id,
            "type": self.event_type,
            "sequence": self.sequence,
            "timestamp": self.timestamp_ms,
            "payload": self.payload,
        }


# ── Validation helpers ────────────────────────────────────────────────────────

def validate_mission_envelope(message: Dict[str, Any]) -> Optional[str]:
    """Validate a NEW_TASK/START WebSocket envelope.

    Returns None if valid, or an error description string if invalid.
    Expected shape: {"mission": {"id": <int>, "task": <str>}}
    """
    mission = message.get("mission")
    if not isinstance(mission, dict):
        return "envelope.mission must be an object"
    mission_id = mission.get("id")
    if not is_valid_mission_id(mission_id):
        return f"mission.id must be a positive int <= {MAX_MISSION_ID}"
    task = mission.get("task")
    if not isinstance(task, str) or not task.strip():
        return "mission.task must be a non-empty string"
    if len(task) > 4000:
        return "mission.task exceeds 4000 character limit"
    return None

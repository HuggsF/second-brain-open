"""Nexus domain entities — canonical source of truth for agents, rooms and tools.

All other modules that need these definitions (DagGate, Orchestrator, constants3d.js)
must derive from here.  Do NOT import any I/O or third-party libraries from this file.
"""
from typing import Dict, FrozenSet, List

# ── Agent roles ───────────────────────────────────────────────────────────────

AGENT_ROLES: Dict[str, Dict] = {
    "manager": {
        "label":  "Orquestradora",
        "name":   "Maia",
        "color":  "#ff007f",
        "room":   "orchestrator",
    },
    "researcher": {
        "label":  "Pesquisador",
        "name":   "Noah",
        "color":  "#00f0ff",
        "room":   "research",
    },
    "coder": {
        "label":  "Dev",
        "name":   "Theo",
        "color":  "#39ff14",
        "room":   "development",
    },
    "writer": {
        "label":  "Escritora",
        "name":   "Lia",
        "color":  "#a78bfa",
        "room":   "writing",
    },
    "reviewer": {
        "label":  "Revisora",
        "name":   "Eva",
        "color":  "#ffe600",
        "room":   "meeting",
    },
}

# Frozen set for fast membership checks (DagGate, tests)
ALLOWED_ROLES: FrozenSet[str] = frozenset(AGENT_ROLES.keys())

# ── Rooms ─────────────────────────────────────────────────────────────────────

ROOMS: Dict[str, Dict] = {
    "orchestrator": {
        "label":    "Orquestração",
        "position": [2.5,  0,  3],
        "size":     [5, 0.2, 4],
        "colorKey": "magenta",
    },
    "research": {
        "label":    "Investigação",
        "position": [-5.5, 0, -3],
        "size":     [5, 0.2, 4],
        "colorKey": "cyan",
    },
    "development": {
        "label":    "Desenvolvimento",
        "position": [0, 0, -3],
        "size":     [5, 0.2, 4],
        "colorKey": "green",
    },
    "writing": {
        "label":    "Redação",
        "position": [5.5, 0, -3],
        "size":     [5, 0.2, 4],
        "colorKey": "violet",
    },
    "meeting": {
        "label":    "Revisão",
        "position": [-2.5, 0,  3],
        "size":     [5, 0.2, 4],
        "colorKey": "amber",
    },
}

# ── Tool registry (per role) ──────────────────────────────────────────────────
# These are the MCP tools each agent role is authorized to use.
# DagGate.ALLOWED_TOOLS is the union of all values.

TOOL_REGISTRY: Dict[str, List[str]] = {
    "manager": [
        "search_knowledge_base",
        "get_brain_status",
        "list_rules",
        "get_rule_evidence",
    ],
    "researcher": [
        "search_knowledge_base",
        "get_adr",
        "get_system_architecture",
        "get_brain_status",
    ],
    "coder": [
        "search_knowledge_base",
        "read_vault_file",
        "get_system_architecture",
        "run_tests",
    ],
    "writer": [
        "search_knowledge_base",
        "read_vault_file",
        "write_doc",
        "get_adr",
    ],
    "reviewer": [
        "search_knowledge_base",
        "get_adr",
        "validate_plan",
        "get_rule_evidence",
    ],
}

# Flat set for DagGate.ALLOWED_TOOLS
ALLOWED_TOOLS: FrozenSet[str] = frozenset(
    tool for tools in TOOL_REGISTRY.values() for tool in tools
)

# ── Agent statuses ────────────────────────────────────────────────────────────

AGENT_STATUSES = frozenset({
    "idle",
    "working",
    "thinking",
    "waitingApproval",
    "done",
})

# ── Handoff types ─────────────────────────────────────────────────────────────

HANDOFF_TYPES = frozenset({
    "context_share",
    "handoff_review",
    "celebration",
    "approval",
})

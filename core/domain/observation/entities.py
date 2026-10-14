"""Observation domain entities: health of the observed hub and contradictions with test lights.

Standard library only; no I/O.  Statuses use the same vocabulary as dashboard/hub-topology.js.
"""
from dataclasses import dataclass
from typing import Tuple

NODE_IDS: Tuple[str, ...] = ("process", "internal", "external", "database")
HEALTH_STATUSES: Tuple[str, ...] = ("green", "yellow", "red", "unknown")
OBSERVED_ENVIRONMENTS: Tuple[str, ...] = ("production", "hml")


@dataclass(frozen=True)
class ServiceHealth:
    """Health of one aspect: id in process|internal|external|database."""
    id: str
    status: str
    reason: str


@dataclass(frozen=True)
class ObservationSnapshot:
    """Projection of one environment: per-aspect health plus the summary status/reason."""
    environment: str
    nodes: Tuple[ServiceHealth, ...]
    status: str
    reason: str
    stale: bool


@dataclass(frozen=True)
class Contradiction:
    """A rule whose tests are green while the observed health of an environment is red."""
    rule_id: str
    environment: str
    light: str
    health: str
    reason: str

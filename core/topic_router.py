"""Topic-based pub/sub router for inter-agent communication.

Extends the existing SSE event bus (``core.events``) with glob-like topic
matching.  Internal subscribers receive the **full** (PII-sanitised) payload,
while the external SSE bus continues to receive redacted envelopes via
``events.publish()``.

Events are persisted to ``.runtime/agent-events.jsonl``, separate from the
legacy ``events.jsonl``.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from config import settings
from core import events, tracing

# ---------------------------------------------------------------------------
# PII sanitisation patterns (aligned with dlp_guardrail.py / analytics_etl.py)
# ---------------------------------------------------------------------------
_PII_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?\d{4,5}[-\s]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{5}-?\d{3}\b"), "[CEP]"),
]

_AGENT_EVENTS_LOG: Path = settings.base_dir / ".runtime" / "agent-events.jsonl"

# Global monotonic sequence counter shared across all TopicRouter instances.
_sequence_counter: int = 0
_seq_lock = threading.Lock()


def _next_sequence() -> int:
    """Return the next globally-unique sequence number (thread-safe)."""
    global _sequence_counter
    with _seq_lock:
        _sequence_counter += 1
        return _sequence_counter


def _sanitise_value(value: Any) -> Any:
    """Recursively strip PII patterns from string values in a payload."""
    if isinstance(value, str):
        for pattern, replacement in _PII_PATTERNS:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, dict):
        return {k: _sanitise_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitise_value(item) for item in value]
    return value


def _matches_topic(pattern: str, topic: str) -> bool:
    """Return ``True`` if *topic* matches the glob-like *pattern*.

    Uses :func:`fnmatch.fnmatchcase` so ``diagnostic.*`` matches
    ``diagnostic.evidence`` but not ``diagnostic.deep.nested``.  Use ``**``
    for multi-level wildcards if needed.
    """
    return fnmatch.fnmatchcase(topic, pattern)


def _persist(event: Dict[str, Any], path: Optional[Path] = None) -> bool:
    """Append *event* as a JSON line to the agent-events log.

    Never raises — returns ``False`` on failure.
    """
    try:
        target = path or _AGENT_EVENTS_LOG
        line = (json.dumps(event, ensure_ascii=False, default=repr) + "\n").encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        tracing._rotate(target)
        with open(target, "ab") as fh:
            fh.write(line)
        return True
    except Exception:
        return False


class TopicRouter:
    """Topic-based publish/subscribe router for agent-to-agent events.

    Subscribers register with a glob pattern (e.g. ``"diagnostic.*"``) and
    receive the full, PII-sanitised payload on an :class:`asyncio.Queue`.

    Every published event is also forwarded to the legacy SSE bus
    (``core.events.publish``) in redacted form for backward compatibility.

    Parameters
    ----------
    maxsize:
        Maximum items in each subscriber queue.  When full, the event is
        silently dropped for that subscriber.
    log_path:
        Override the default persistence path for agent events.
    """

    def __init__(
        self,
        maxsize: int = 256,
        log_path: Optional[Path] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._subscribers: List[Tuple[str, asyncio.Queue[Dict[str, Any]]]] = []
        self._maxsize = maxsize
        self._log_path = log_path
        self._closed = False

    # -- public API ----------------------------------------------------------

    def subscribe(self, topic_pattern: str) -> asyncio.Queue[Dict[str, Any]]:
        """Register a new subscriber for *topic_pattern*.

        Parameters
        ----------
        topic_pattern:
            Glob-like pattern (e.g. ``"tool.*"``, ``"diagnostic.evidence"``).

        Returns
        -------
        asyncio.Queue
            A queue from which the subscriber can ``await q.get()`` events.
        """
        q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.append((topic_pattern, q))
        return q

    def unsubscribe(self, q: asyncio.Queue[Dict[str, Any]]) -> None:
        """Remove a subscriber queue from all topic registrations."""
        with self._lock:
            self._subscribers = [
                (pat, existing) for pat, existing in self._subscribers if existing is not q
            ]

    def publish(self, topic: str, event: dict) -> Dict[str, Any]:
        """Publish an event to *topic*.

        The event dict **must** contain at least ``agentId``, ``missionId``,
        and ``payload``.  The router enriches it with ``topic``, ``sequence``,
        ``timestamp``, and ``id`` if missing.

        Returns the fully-enriched, sanitised event that was dispatched.

        Parameters
        ----------
        topic:
            Dot-separated topic string (e.g. ``"diagnostic.evidence"``).
        event:
            Event dictionary.  Required keys: ``agentId``, ``missionId``,
            ``payload``.
        """
        enriched = self._enrich(topic, event)
        sanitised = _sanitise_value(enriched)
        assert isinstance(sanitised, dict)  # narrowing for mypy

        # 1. Fan-out to internal (topic-matched) subscribers
        dead: List[asyncio.Queue[Dict[str, Any]]] = []
        with self._lock:
            for pattern, q in self._subscribers:
                if _matches_topic(pattern, topic):
                    try:
                        q.put_nowait(sanitised)
                    except asyncio.QueueFull:
                        dead.append(q)

        # Evict dead subscribers
        if dead:
            with self._lock:
                self._subscribers = [
                    (pat, q) for pat, q in self._subscribers if q not in dead
                ]

        # 2. Persist to agent-events.jsonl
        _persist(sanitised, self._log_path)

        # 3. Forward (redacted) to legacy SSE bus
        try:
            events.publish(enriched)
        except Exception:
            pass  # SSE bus failure must not break agent comms

        return sanitised

    def close(self) -> None:
        """Mark the router as closed and clear subscribers."""
        with self._lock:
            self._closed = True
            self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        """Number of active subscriber registrations."""
        with self._lock:
            return len(self._subscribers)

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _enrich(topic: str, event: dict) -> Dict[str, Any]:
        """Add mandatory envelope fields if not already present."""
        enriched = dict(event)
        enriched.setdefault("id", str(uuid.uuid4()))
        enriched["topic"] = topic
        enriched.setdefault("agentId", "unknown")
        enriched.setdefault("missionId", "unknown")
        enriched["sequence"] = _next_sequence()
        enriched.setdefault("timestamp", int(time.time() * 1000))
        enriched.setdefault("payload", {})
        return enriched

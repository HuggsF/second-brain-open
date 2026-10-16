"""Redacted event log: one JSON line per envelope, never the payload."""

import json
import queue
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

from config import settings
from core import tracing

EVENTS_LOG: Path = settings.base_dir / ".runtime" / "events.jsonl"
FAILURES: int = 0


def redact(env: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of env without its payload; keeps only its size and safe fields."""
    out = {k: v for k, v in env.items() if k != "payload"}
    payload = env.get("payload")
    out["payload_bytes"] = (
        0 if payload is None else len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    )
    if isinstance(payload, dict):
        labels = payload.get("labels")
        if env.get("task") == "classify" and isinstance(labels, dict):
            # Só os rótulos do vocabulário; tags vêm do texto e ficam fora do log.
            out["labels"] = {k: labels[k] for k in ("type", "team") if k in labels}
        if env.get("task") == "validate" and "valid" in payload:
            out["valid"] = payload["valid"]
    return out


def record(env: Dict[str, Any], path: Optional[Path] = None) -> bool:
    """Append the redacted envelope. Never raises; False (and FAILURES+1) on error."""
    global FAILURES
    try:
        target = path or EVENTS_LOG
        line = (json.dumps(redact(env), ensure_ascii=False, default=repr) + "\n").encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        tracing._rotate(target)
        with open(target, "ab") as handle:
            handle.write(line)
        return True
    except Exception:
        FAILURES += 1
        return False


def failures() -> int:
    return FAILURES


# ── BUS-01: SSE Subscriber Management ──
SSE_SUBSCRIBERS: Set[queue.Queue] = set()
_sub_lock = threading.Lock()


def subscribe() -> queue.Queue:
    """Register a new SSE subscriber. Returns queue for consumption."""
    q = queue.Queue(maxsize=256)
    with _sub_lock:
        SSE_SUBSCRIBERS.add(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    """Remove an SSE subscriber."""
    with _sub_lock:
        SSE_SUBSCRIBERS.discard(q)


def publish(event: dict) -> None:
    """Fan-out: send redacted event to all SSE subscribers.
    Silently discards if queue is full (slow subscriber)."""
    safe = redact(event)
    dead: list[queue.Queue] = []
    with _sub_lock:
        for q in SSE_SUBSCRIBERS:
            try:
                q.put_nowait(safe)
            except queue.Full:
                dead.append(q)
    if dead:
        with _sub_lock:
            for q in dead:
                SSE_SUBSCRIBERS.discard(q)


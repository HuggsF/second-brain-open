"""Redacted event log: one JSON line per envelope, never the payload."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

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
        if env.get("task") == "classify" and "labels" in payload:
            out["labels"] = payload["labels"]
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

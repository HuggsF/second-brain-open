"""Trace log for MCP tool calls: W3C-shaped ids, argument redaction, bounded append, rotation.

Nothing here may make a tool call fail: write_record swallows every error.
"""
import hashlib
import json
import os
import re
import secrets
import sys
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from config import settings

TRACE_LOG: Path = settings.base_dir / ".runtime" / "trace-log.jsonl"
MAX_BYTES: int = 5 * 1024 * 1024
KEEP: int = 3
MAX_RECORD_BYTES: int = 4096

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_SECRET_PARTS = ("token", "password", "secret", "key", "authorization", "credential")
_LABEL_MAX = 80
_DEFAULT_LIMIT = 200
_COMMAND_LIMIT = 500


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


def _strip_control(text: str) -> str:
    return "".join(c for c in text if unicodedata.category(c) != "Cc").strip()


def derive_trace_id(task_id: object) -> Tuple[str, Optional[str]]:
    """Return (trace_id, task_label). Blank or non-string input gives a fresh id and no label."""
    if isinstance(task_id, str):
        cleaned = _strip_control(task_id)
        if cleaned:
            if _HEX32.match(cleaned):
                return cleaned, None
            return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:32], cleaned[:_LABEL_MAX]
    return new_trace_id(), None


_MAX_DEPTH = 4

# Values that must never reach a log or the evidence store, whatever the argument is called.
SENSITIVE_VALUES = (
    ("token", re.compile(r"ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|-----BEGIN[^\n]*")),
    ("cpf", re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|(?<!\d)\d{11}(?!\d)")),
    ("nf-key", re.compile(r"(?<!\d)\d{44}(?!\d)")),
)


def mask_sensitive(text: str) -> str:
    for _, pattern in SENSITIVE_VALUES:
        text = pattern.sub("[redacted]", text)
    return text


def _is_secret_key(name: str) -> bool:
    return any(part in name.lower() for part in _SECRET_PARTS)


def _summarise(value: Any, limit: int, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return mask_sensitive(value)[:limit]
    if isinstance(value, dict) and depth < _MAX_DEPTH:
        return {
            str(k): "[redacted]" if _is_secret_key(str(k)) else _summarise(v, limit, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)) and depth < _MAX_DEPTH:
        return [_summarise(v, limit, depth + 1) for v in value]
    if isinstance(value, (dict, list, tuple)):
        return "[nested value omitted]"  # too deep to inspect safely: never repr() it
    return mask_sensitive(repr(value))[:limit]


def redact_args(args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Bounded, JSON-safe copy of the call arguments with secret-looking values masked."""
    out: Dict[str, Any] = {}
    for key, value in (args or {}).items():
        name = str(key)
        if name == "task_id":
            continue
        if _is_secret_key(name):
            out[name] = "[redacted]"
        else:
            out[name] = _summarise(value, _COMMAND_LIMIT if name == "command" else _DEFAULT_LIMIT)
    return out


def _rotated(path: Path, index: int) -> Path:
    return path.with_name(f"{path.stem}.{index}{path.suffix}")


def _rotate(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_BYTES:
        return
    oldest = _rotated(path, KEEP)
    if oldest.exists():
        oldest.unlink()
    for index in range(KEEP - 1, 0, -1):
        source = _rotated(path, index)
        if source.exists():
            os.replace(source, _rotated(path, index + 1))
    os.replace(path, _rotated(path, 1))


def _encode(record: Dict[str, Any]) -> bytes:
    def fits(rec: Dict[str, Any]) -> Optional[bytes]:
        data = (json.dumps(rec, ensure_ascii=False, default=repr) + "\n").encode("utf-8")
        return data if len(data) <= MAX_RECORD_BYTES else None

    data = fits(record)
    if data is not None:
        return data
    args = record.get("args")
    if isinstance(args, dict):
        for limit in (100, 40, 0):
            shrunk = {k: (v[:limit] if isinstance(v, str) else v) for k, v in args.items()}
            data = fits({**record, "args": shrunk})
            if data is not None:
                return data
    data = fits({**record, "args": {"_truncated": True}})
    if data is not None:
        return data
    minimal = {k: record[k] for k in ("schema_version", "ts", "trace_id", "span_id", "tool", "event", "status") if k in record}
    return (json.dumps({**minimal, "args": {"_truncated": True}}, ensure_ascii=False) + "\n").encode("utf-8")


def write_record(record: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Append one record. Never raises."""
    try:
        target = path or TRACE_LOG
        target.parent.mkdir(parents=True, exist_ok=True)
        _rotate(target)
        with open(target, "ab") as handle:
            handle.write(_encode(record))
    except Exception as exc:  # tracing must never break the tool call
        print(f"trace: could not write record ({type(exc).__name__})", file=sys.stderr)


def _iter_records(path: Optional[Path]) -> Iterator[Dict[str, Any]]:
    target = path or TRACE_LOG
    for source in [*(_rotated(target, i) for i in range(KEEP, 0, -1)), target]:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.split("\n"):  # not splitlines(): U+2028/U+2029 are not escaped by json.dumps
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record


def read_trace(trace_id: str, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    return [r for r in _iter_records(path) if r.get("trace_id") == trace_id]


def read_recent(n: int, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    records = list(_iter_records(path))
    return records[-n:] if n > 0 else []


@dataclass
class CallState:
    """The tool call currently being traced; child events attach to it."""
    trace_id: str
    span_id: str
    server: str
    tool: str
    refused: bool = False
    path: Optional[Path] = None
    caller: str = "unknown"
    task_label: Optional[str] = None
    started_at: str = ""


current_call: ContextVar[Optional[CallState]] = ContextVar("trace_current_call", default=None)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def emit_child(
    event: str,
    status: str,
    args: Optional[Dict[str, Any]] = None,
    error_type: Optional[str] = None,
    path: Optional[Path] = None,
) -> None:
    """Record an event inside the current call (same trace, parent = the call). No-op outside a call."""
    try:
        state = current_call.get()
        if state is None:
            return
        if event == "ssh.refused":
            state.refused = True
        write_record(
            {
                "schema_version": 1,
                "ts": now_iso(),
                "trace_id": state.trace_id,
                "span_id": new_span_id(),
                "parent_span_id": state.span_id,
                "task_label": state.task_label,
                "server": state.server,
                "tool": state.tool,
                "event": event,
                "status": status,
                "caller": state.caller,
                "args": redact_args(args),
                "error_type": error_type,
            },
            path or state.path,
        )
    except Exception as exc:
        print(f"trace: could not emit child event ({type(exc).__name__})", file=sys.stderr)

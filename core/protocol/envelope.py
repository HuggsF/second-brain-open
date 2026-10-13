"""Envelope brain.task/1: construção e validação."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

PROTOCOL = "brain.task/1"
TASKS = ("classify", "extract", "summarize", "validate")
KINDS = ("task.request", "task.result", "task.event")
REASONS = frozenset({
    "local_unavailable", "schema_invalid", "input_too_large", "unknown_template",
    "unknown_task", "no_valid_label", "profile_not_found", "timeout",
})

_SCHEMA_PATH = Path(__file__).parent / "schemas" / "envelope.schema.json"
_validator: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    global _validator
    if _validator is None:
        _validator = Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))
    return _validator


def make_envelope(kind: str, task: str, *, sender: str, to: str, payload: dict,
                  template: str | None = None, trace_id: str | None = None,
                  parent_id: str | None = None, status: str | None = None,
                  reason: str | None = None, cost: dict | None = None) -> dict:
    env = {
        "protocol": PROTOCOL,
        "kind": kind,
        "id": str(uuid.uuid4()),
        "trace_id": trace_id,
        "parent_id": parent_id,
        "from": sender,
        "to": to,
        "task": task,
        "template": template,
        "payload": payload,
        "status": status,
        "reason": reason,
        "cost": cost,
        "ts": datetime.now().astimezone().isoformat(),
    }
    return env


def validate_envelope(env: dict) -> list[str]:
    errors = sorted(_get_validator().iter_errors(env), key=lambda e: list(e.absolute_path))
    out = [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
    if isinstance(env, dict) and env.get("task") not in TASKS and env.get("status") != "invalid":
        out.append("task: tarefa fora de TASKS só é aceita com status invalid")
    return out

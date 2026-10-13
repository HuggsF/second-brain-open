"""Roteador: determinístico -> modelo local -> validação. Sempre devolve um task.result."""
from __future__ import annotations

import json
import math
import re

from jsonschema import Draft202012Validator

from config import settings
from core import events, tracing
from core.local_tasks import tasks
from core.local_tasks.ollama_client import LocalModelError, OllamaClient
from core.local_tasks.profile import Profile, ProfileNotFound, load_profile
from core.protocol import registry
from core.protocol.envelope import TASKS, make_envelope

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def _loads(raw: str) -> dict | None:
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_json(text: str) -> dict | None:
    """JSON puro, entre cercas, ou o primeiro objeto `{...}` balanceado dentro de texto."""
    obj = _loads(text.strip())
    if obj is not None:
        return obj
    fenced = _FENCE.search(text)
    if fenced:
        obj = _loads(fenced.group(1).strip())
        if obj is not None:
            return obj
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return _loads(text[start:i + 1])
    return None


def _safe_task_name(task) -> str:
    name = re.sub(r"[^a-z0-9_-]", "_", str(task).lower())[:32]
    return name if re.match(r"^[a-z][a-z0-9_-]{0,31}$", name) else "unknown"


def _cost(model: str, tier: str, tin: int, tout: int, ms: int, profile: Profile | None) -> dict:
    ref = (profile.paid_reference if profile else None) or {}
    usd = (tin * float(ref.get("input", 0)) + tout * float(ref.get("output", 0))) / 1e6
    return {"model": model, "tier": tier, "tokens_in": tin, "tokens_out": tout, "ms": ms,
            "paid_equivalent_usd": usd}


def _errors(schema: dict, obj: dict) -> list[str]:
    errs = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs]


def _execute(task, text, template, target_words, profile, client):
    """Devolve (status, reason, payload, cost)."""
    model = profile.local_model
    det = _cost(model, "deterministic", 0, 0, 0, profile)
    if task not in TASKS:
        return "invalid", "unknown_task", {}, det
    if task == "extract":
        try:
            registry.load_schema(template)
        except registry.UnknownTemplate:
            return "invalid", "unknown_template", {}, det
    if estimate_tokens(text) > profile.max_input_tokens:
        return "escalate", "input_too_large", {}, det
    schema = tasks.output_schema(task, template)
    system, user = tasks.prompt(task, text, profile, schema, target_words)
    client = client or OllamaClient(timeout=profile.timeout_seconds)
    tin = tout = ms = 0
    last_errors: list[str] = []
    for _ in range(1 + max(0, profile.retries)):
        prompt_user = user
        if last_errors:
            prompt_user = f"{user}\n\nA resposta anterior falhou na validação: {'; '.join(last_errors[:3])}"
        try:
            done = client.chat(model, system, prompt_user, schema)
        except LocalModelError as exc:
            return "escalate", exc.reason, {}, _cost(model, "local", tin, tout, ms, profile)
        except Exception:
            return "error", None, {}, _cost(model, "local", tin, tout, ms, profile)
        tin += done.tokens_in
        tout += done.tokens_out
        ms += done.ms
        obj = parse_json(done.text)
        if obj is None:
            last_errors = ["resposta não é um objeto JSON"]
            continue
        last_errors = _errors(schema, obj)
        if last_errors:
            continue
        payload, why = tasks.postprocess(task, obj, profile)
        if payload is None:
            return "escalate", why, {}, _cost(model, "local", tin, tout, ms, profile)
        last_errors = _errors(schema, payload)
        if not last_errors:
            return "ok", None, payload, _cost(model, "local", tin, tout, ms, profile)
    return "escalate", "schema_invalid", {}, _cost(model, "local", tin, tout, ms, profile)


def run_task(task: str, *, text: str, template: str | None = None, target_words: int = 120,
             source: str | None = None, sender: str = "cli", trace_id: str | None = None,
             profile: Profile | None = None, client: OllamaClient | None = None) -> dict:
    trace_id = trace_id or tracing.new_trace_id()
    env_task = task if task in TASKS else _safe_task_name(task)
    payload = {"text": text}
    if template is not None:
        payload["template"] = template
    if task == "summarize":
        payload["target_words"] = target_words
    if source is not None:
        payload["source"] = source
    request = make_envelope("task.request", env_task, sender=sender, to="local", payload=payload,
                            template=template, trace_id=trace_id)
    events.record(request)

    if profile is None:
        try:
            profile = load_profile()
        except ProfileNotFound:
            status, reason, out = "invalid", "profile_not_found", {}
            cost = _cost(settings.chat_model, "deterministic", 0, 0, 0, None)
    if profile is not None:
        status, reason, out, cost = _execute(task, text, template, target_words, profile, client)
    result = make_envelope("task.result", env_task, sender="router", to="caller", payload=out,
                           template=template, trace_id=trace_id, parent_id=request["id"],
                           status=status, reason=reason, cost=cost)
    events.record(result)
    return result

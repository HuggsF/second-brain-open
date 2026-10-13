"""Roteador: determinístico -> modelo local -> validação. Sempre devolve um task.result."""
from __future__ import annotations

import json
import math
import re
import time

from jsonschema import Draft202012Validator

from config import settings
from core import events, tracing
from core.local_tasks import tasks
from core.local_tasks.ollama_client import LocalModelError, OllamaClient
from core.local_tasks.profile import Profile, ProfileNotFound, load_profile
from core.protocol import registry
from core.protocol.envelope import TASKS, make_envelope

_clock = time.monotonic
STATUS_TIMEOUT_SECONDS = 5  # sondagem de /api/tags: curta, independente do timeout do perfil


class _Deadline:
    """Envolve o cliente: depois do prazo total do run_task, nova chamada ao modelo vira timeout."""

    def __init__(self, client, seconds: float):
        self._client = client
        self._end = _clock() + seconds

    def chat(self, model, system, user, schema):
        if _clock() >= self._end:
            raise LocalModelError("timeout", "prazo total da tarefa")
        return self._client.chat(model, system, user, schema)


def deadline_seconds(profile: Profile) -> float:
    """Prazo total de um run_task: timeout_seconds x (1 + retries) x 2."""
    return profile.timeout_seconds * (1 + max(0, profile.retries)) * 2


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


def _price(ref: dict, key: str) -> float:
    """Preço por milhão de tokens; ausente ou inválido vale 0.0 (load_profile já recusa inválidos)."""
    value = ref.get(key)
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _cost(model: str, tier: str, tin: int, tout: int, ms: int, profile: Profile | None) -> dict:
    ref = (profile.paid_reference if profile else None) or {}
    usd = (tin * _price(ref, "input") + tout * _price(ref, "output")) / 1e6
    return {"model": model, "tier": tier, "tokens_in": tin, "tokens_out": tout, "ms": ms,
            "paid_equivalent_usd": usd}


def _errors(schema: dict, obj: dict) -> list[str]:
    errs = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs]


def _ask(task, system, user, schema, profile, client):
    """Laço de tentativas. Devolve (status, reason, payload, (tokens_in, tokens_out, ms))."""
    model = profile.local_model
    tin = tout = ms = 0
    last_errors: list[str] = []
    for _ in range(1 + max(0, profile.retries)):
        prompt_user = user
        if last_errors:
            prompt_user = f"{user}\n\nA resposta anterior falhou na validação: {'; '.join(last_errors[:3])}"
        try:
            done = client.chat(model, system, prompt_user, schema)
        except LocalModelError as exc:
            return "escalate", exc.reason, {}, (tin, tout, ms)
        except Exception:
            return "error", None, {}, (tin, tout, ms)
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
            return "escalate", why, {}, (tin, tout, ms)
        last_errors = _errors(schema, payload)
        if not last_errors:
            return "ok", None, payload, (tin, tout, ms)
    return "escalate", "schema_invalid", {}, (tin, tout, ms)


def _summarize(text, target_words, profile, client):
    """Map-reduce de um nível. Devolve (status, reason, payload, usage)."""
    schema = tasks.output_schema("summarize", None)
    max_chars = profile.max_input_tokens * 4
    if len(text) <= max_chars:
        system, user = tasks.prompt("summarize", text, profile, schema, target_words)
        return _ask("summarize", system, user, schema, profile, client)
    usage = [0, 0, 0]
    summaries: list[str] = []

    def call(chunk):
        system, user = tasks.prompt("summarize", chunk, profile, schema, target_words)
        status, reason, payload, used = _ask("summarize", system, user, schema, profile, client)
        for i in range(3):
            usage[i] += used[i]
        return status, reason, payload

    blocks = tasks.split_blocks(text, max_chars)
    if len(blocks) > profile.max_blocks:
        return "escalate", "input_too_large", {}, (0, 0, 0)
    for block in blocks:
        status, reason, payload = call(block)
        if status != "ok":
            return status, reason, {}, tuple(usage)
        summaries.append(payload["summary"])
    joined = "\n\n".join(summaries)
    if len(joined) > max_chars:
        return "escalate", "input_too_large", {}, tuple(usage)
    status, reason, payload = call(joined)
    return status, reason, payload, tuple(usage)


def _validate(text, template, source, profile, client):
    result = tasks.validate_document(text, template)
    if not source:
        return "ok", None, result, (0, 0, 0), False
    user_text = tasks.review_input(text, source)
    if estimate_tokens(user_text) > profile.max_input_tokens:
        return "escalate", "input_too_large", {}, (0, 0, 0), False
    schema = tasks.output_schema("validate", template)
    system, user = tasks.prompt("validate", user_text, profile, schema, 0)
    status, reason, payload, used = _ask("validate", system, user, schema, profile, client)
    if status == "ok":
        result["review"] = payload["review"]
        payload = result
    return status, reason, payload, used, True


def _execute(task, text, template, target_words, source, profile, client):
    """Devolve (status, reason, payload, cost)."""
    model = profile.local_model
    det = _cost(model, "deterministic", 0, 0, 0, profile)
    if task not in TASKS:
        return "invalid", "unknown_task", {}, det
    if task in ("extract", "validate"):
        try:
            registry.load_schema(template)
        except registry.UnknownTemplate:
            return "invalid", "unknown_template", {}, det
    client = _Deadline(client or OllamaClient(timeout=profile.timeout_seconds), deadline_seconds(profile))
    if task == "summarize":
        status, reason, payload, used = _summarize(text, target_words, profile, client)
        modelled = True
    elif task == "validate":
        status, reason, payload, used, modelled = _validate(text, template, source, profile, client)
    else:
        if estimate_tokens(text) > profile.max_input_tokens:
            return "escalate", "input_too_large", {}, det
        schema = tasks.output_schema(task, template)
        system, user = tasks.prompt(task, text, profile, schema, target_words)
        status, reason, payload, used = _ask(task, system, user, schema, profile, client)
        modelled = True
    if not modelled or (used == (0, 0, 0) and reason == "input_too_large"):
        return status, reason, payload, det
    return status, reason, payload, _cost(model, "local", *used, profile)


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
        except Exception:
            status, reason, out = "error", None, {}
            cost = _cost(settings.chat_model, "deterministic", 0, 0, 0, None)
    if profile is not None:
        status, reason, out, cost = _execute(task, text, template, target_words, source, profile, client)
    result = make_envelope("task.result", env_task, sender="router", to="caller", payload=out,
                           template=template, trace_id=trace_id, parent_id=request["id"],
                           status=status, reason=reason, cost=cost)
    events.record(result)
    return result


def status(profile: Profile | None = None, client: OllamaClient | None = None) -> dict:
    """Estado do runtime local. Nunca levanta exceção."""
    name = None
    model = settings.chat_model
    available = False
    try:
        profile = profile or load_profile()
        name, model = profile.name, profile.local_model
        available = bool((client or OllamaClient(timeout=STATUS_TIMEOUT_SECONDS)).available(model))
    except Exception:
        available = False
    return {
        "profile": name,
        "local_model": model,
        "model_available": available,
        "event_write_failures": events.failures(),
        "templates": registry.available(),
    }

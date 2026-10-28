"""Roteador: determinístico -> modelo local -> validação. Sempre devolve um task.result."""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time

from jsonschema import Draft202012Validator

from config import settings
from core import events, tracing
from core.local_tasks import tasks
from core.local_tasks.ollama_client import LocalModelError, OllamaClient
from core.local_tasks.profile import Profile, ProfileNotFound, load_profile
from core.local_tasks.providers import build_client, deadline_timeout, is_configured, probe_client
from core.protocol import registry
from core.cost import CostRecord
from core.protocol.envelope import TASKS, make_envelope

# ── Budget guard (T3, onda C) ───────────────────────────────────────


def _build_local_only_client(profile):
    """Build a FallbackClient with only local (non-cloud) providers.

    Filters out ``openai_compatible`` providers so that only Ollama (or
    other local providers) remain.  Returns ``None`` when no local
    provider exists.  Uses :func:`build_client` indirectly so that mocks
    on :class:`providers.OllamaClient` are respected.
    """
    from core.local_tasks.providers import FallbackClient
    local_specs = [s for s in (profile.providers or ()) if s.kind != "openai_compatible"]
    if not local_specs:
        return None
    # Import OllamaClient from providers so tests can mock it there
    from core.local_tasks import providers as _prov
    entries = []
    for spec in local_specs:
        if spec.kind == "ollama":
            client = _prov.OllamaClient(
                base_url=spec.base_url,
                timeout=spec.timeout_seconds,
                keep_alive=spec.keep_alive,
            )
        else:
            continue
        entries.append((spec, client))
    if not entries:
        return None
    return FallbackClient(entries)

_clock = time.monotonic
STATUS_TIMEOUT_SECONDS = 5  # prazo total da sonda de cada provedor, independente do timeout do perfil


class _Deadline:
    """Envolve o cliente durante um run_task.

    Depois do prazo total, nova chamada ao modelo vira timeout. Também guarda, só para este
    run_task, o provedor da última resposta e o custo real somado resposta a resposta (preço do
    provedor que respondeu cada uma).
    """

    def __init__(self, client, seconds: float):
        self._client = client
        self._end = _clock() + seconds
        self.last_provider = None
        self.actual_usd = 0.0
        if hasattr(client, "last_provider"):
            client.last_provider = None  # cliente reutilizado: nada da tarefa anterior

    def chat(self, model, system, user, schema):
        if _clock() >= self._end:
            raise LocalModelError("timeout", "prazo total da tarefa")
        done = self._client.chat(model, system, user, schema)
        spec = getattr(self._client, "last_provider", None)
        if spec is not None:
            self.last_provider = spec
            price = spec.price or {}
            self.actual_usd += (done.tokens_in * _price(price, "input")
                                + done.tokens_out * _price(price, "output")) / 1e6
        return done


def deadline_seconds(profile: Profile) -> float:
    """Prazo total de um run_task: deadline_timeout x (1 + retries) x 2."""
    return deadline_timeout(profile) * (1 + max(0, profile.retries)) * 2


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


def _cost(model: str, tier: str, tin: int, tout: int, ms: int, profile: Profile | None,
          provider_spec=None, actual_usd: float = 0.0) -> CostRecord:
    ref = (profile.paid_reference if profile else None) or {}
    usd = (tin * _price(ref, "input") + tout * _price(ref, "output")) / 1e6
    return CostRecord(
        model=model, tier=tier, tokens_in=tin, tokens_out=tout, ms=ms,
        paid_equivalent_usd=usd,
        provider=provider_spec.name if provider_spec is not None else None,
        actual_usd=actual_usd if provider_spec is not None else 0.0,
    )


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
            ms += int(getattr(exc, "ms", 0) or 0)  # tempo gasto nas tentativas que falharam
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
    client = _Deadline(client or build_client(profile), deadline_seconds(profile))
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
    lp = client.last_provider  # provedor da última resposta deste run_task, ou None
    if lp is not None:
        tier = "cloud" if lp.kind == "openai_compatible" else "local"
        return status, reason, payload, _cost(lp.model, tier, *used, profile, provider_spec=lp,
                                              actual_usd=client.actual_usd)
    return status, reason, payload, _cost(model, "local", *used, profile)



def _needs_model(task: str, template: str | None, source: str | None) -> bool:
    """Return True when the task will call the model (non-deterministic).

    Deterministic paths: unknown_task, unknown_template, validate-without-source.
    Those never call the model, so the budget guard should let them through.
    """
    if task not in TASKS:
        return False  # unknown_task → deterministic
    if task in ("extract", "validate"):
        try:
            registry.load_schema(template)
        except registry.UnknownTemplate:
            return False  # unknown_template → deterministic
    if task == "validate" and not source:
        return False  # validate without source → deterministic
    return True

def run_task(task: str, *, text: str, template: str | None = None, target_words: int = 120,
             source: str | None = None, sender: str = "cli", trace_id: str | None = None,
             profile: Profile | None = None, client: OllamaClient | None = None,
             budget_tracker=None) -> dict:
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

    status = reason = out = cost = None

    if profile is None:
        try:
            profile = load_profile()
        except ProfileNotFound:
            status, reason, out = "invalid", "profile_not_found", {}
            cost = _cost(settings.chat_model, "deterministic", 0, 0, 0, None)
        except Exception:
            status, reason, out = "error", None, {}
            cost = _cost(settings.chat_model, "deterministic", 0, 0, 0, None)
    if profile is not None and status is None:
        # Budget guard (T3, onda C): when exceeded, use only local providers
        exec_client = client
        if budget_tracker is not None:
            budget_st = budget_tracker.status()
            if budget_st.state == "exceeded":
                if not profile.providers:
                    # Legacy profile (no providers): uses Ollama implicitly,
                    # so there is no cloud to block — skip the guard.
                    pass
                else:
                    local_only = _build_local_only_client(profile)
                    if local_only is not None:
                        exec_client = local_only
                    elif _needs_model(task, template, source):
                        # Cloud-only profile, non-deterministic task: block
                        budget_reason = ("budget_daily" if budget_st.limiting_period == "daily"
                                         else "budget_monthly")
                        status, reason, out = "budget_exceeded", budget_reason, {}
                        cost = _cost(profile.local_model, "deterministic", 0, 0, 0, profile)
        if status is None:
            status, reason, out, cost = _execute(
                task, text, template, target_words, source, profile, exec_client)
    result = make_envelope("task.result", env_task, sender="router", to="caller", payload=out,
                           template=template, trace_id=trace_id, parent_id=request["id"],
                           status=status, reason=reason, cost=cost.to_dict() if cost is not None else None)
    events.record(result)
    # Record cost in budget tracker (always, including zero)
    if budget_tracker is not None:
        budget_tracker.record(
            cost, envelope_id=result["id"], trace_id=trace_id,
            task=env_task, sender=sender, ts=result.get("ts"))
    return result


def _probe_providers(specs) -> list[dict]:
    """Sonda os provedores em paralelo; cada um tem no máximo STATUS_TIMEOUT_SECONDS. Nunca levanta."""
    timeout = STATUS_TIMEOUT_SECONDS
    rows = [{"name": spec.name, "kind": spec.kind, "model": spec.model,
             "configured": is_configured(spec), "available": False} for spec in specs]

    def probe(row, client, spec):
        try:
            ok = client.available(spec.model) if spec.kind == "ollama" else client.available()
            row["available"] = bool(ok)
        except Exception:
            row["available"] = False

    threads = []
    for row, spec in zip(rows, specs):
        try:
            client = probe_client(spec, timeout)
        except Exception:
            continue
        done = {}
        t = threading.Thread(target=lambda r=done, c=client, sp=spec: probe(r, c, sp), daemon=True)
        t.start()
        threads.append((row, done, t))
    end = time.monotonic() + timeout
    for row, done, t in threads:
        t.join(max(0.0, end - time.monotonic()))
        # Sonda que não terminou no prazo conta como indisponível, mesmo que responda depois.
        row["available"] = bool(not t.is_alive() and done.get("available"))
    return rows


def status(profile: Profile | None = None, client: OllamaClient | None = None) -> dict:
    """Estado do runtime local. Nunca levanta exceção."""
    name = None
    model = settings.chat_model
    available = False
    providers_info: list[dict] = []
    try:
        profile = profile or load_profile()
        name, model = profile.name, profile.local_model
        if profile.providers:
            providers_info = _probe_providers(profile.providers)
            # Um provedor só conta se tiver a chave (quando exigida) e responder.
            available = any(p["configured"] and p["available"] for p in providers_info)
        else:
            available = bool((client or OllamaClient(timeout=STATUS_TIMEOUT_SECONDS)).available(model))
    except Exception:
        available = False
    return {
        "profile": name,
        "local_model": model,
        "model_available": available,
        "event_write_failures": events.failures(),
        "templates": registry.available(),
        "providers": providers_info,
    }

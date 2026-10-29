"""Resposta do assistente pela cadeia de provedores do perfil (ADR-038).

A recuperação (embedding, busca, piso, gate) acontece antes e fica local; aqui só a geração do
texto passa pela mesma cadeia das tarefas: nuvem primeiro, Ollama de reserva, orçamento e custo.
"""
from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from config import settings
from core.cost import CostRecord
from core.local_tasks.ollama_client import LocalModelError
from core.local_tasks.providers import build_client, deadline_timeout
from core.local_tasks.router import _budget_alert, _build_local_only_client, _cost, _Deadline, parse_json

__all__ = ["ANSWER_SCHEMA", "AnswerResult", "default_budget_tracker", "generate_answer"]

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

_tracker_cache: dict[str, object] = {}


@dataclass(frozen=True)
class AnswerResult:
    """`status`: `ok` ou `model_error` (todos os provedores falharam ou o orçamento barrou)."""

    status: str
    text: str | None
    reason: str | None
    provider: str | None
    cost: CostRecord


def default_budget_tracker(profile):
    """Rastreador do orçamento do perfil (um por processo); `None` sem bloco `budget`."""
    if getattr(profile, "budget", None) is None:
        return None
    cached = _tracker_cache.get(profile.name)
    if cached is not None:
        return cached
    try:
        from core.budget import BudgetTracker
        db_path = settings.base_dir / ".runtime" / "budget.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tracker = BudgetTracker(db_path, profile.budget)
    except Exception:
        from core.budget import FailedBudgetTracker
        return FailedBudgetTracker(profile.budget)  # sem cache: tenta de novo na próxima pergunta
    _tracker_cache[profile.name] = tracker
    return tracker


def _text_of(raw: str) -> str:
    """Texto da resposta: o campo `answer` do JSON pedido, ou o texto livre se o provedor ignorou o schema."""
    obj = parse_json(raw)
    if isinstance(obj, dict) and isinstance(obj.get("answer"), str):
        return obj["answer"].strip()
    return raw.strip()


def _record(budget_tracker, cost: CostRecord, trace_id: str | None, pre_state) -> None:
    """Grava o custo e alerta se o estado piorou; nunca derruba a resposta (ADR-036)."""
    if budget_tracker is None:
        return
    try:
        budget_tracker.record(cost, envelope_id=uuid.uuid4().hex, trace_id=trace_id, task="answer",
                              sender="retriever", ts=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        print(f"[budget] falha ao registrar custo da resposta: {type(exc).__name__}.", file=sys.stderr)
        return
    _budget_alert(budget_tracker, pre_state, trace_id)


def generate_answer(system: str, user: str, *, profile, client=None, budget_tracker=None,
                    trace_id: str | None = None) -> AnswerResult:
    """Gera a resposta pela cadeia do perfil. Nunca levanta: falha vira `model_error`."""
    pre_state = None
    if budget_tracker is not None:
        try:
            status = budget_tracker.status()
            pre_state = status.state
            exceeded, period = status.state == "exceeded", status.limiting_period
        except Exception as exc:
            print(f"[budget] estado do orçamento indisponível ({type(exc).__name__}); "
                  "nuvem bloqueada nesta resposta.", file=sys.stderr)
            exceeded, period = True, "daily"
        if exceeded and profile.providers:
            client = _build_local_only_client(profile)
            if client is None:
                reason = "budget_daily" if period == "daily" else "budget_monthly"
                return AnswerResult("model_error", None, reason, None,
                                    _cost(profile.local_model, "deterministic", 0, 0, 0, profile))

    tracked = _Deadline(client or build_client(profile), deadline_timeout(profile) * max(1, len(profile.providers)))
    try:
        done = tracked.chat(profile.local_model, system, user, ANSWER_SCHEMA)
    except LocalModelError as exc:
        ms = int(getattr(exc, "ms", 0) or 0)
        return AnswerResult("model_error", None, exc.reason, None,
                            _cost(profile.local_model, "local", 0, 0, ms, profile))
    except Exception:
        return AnswerResult("model_error", None, "error", None,
                            _cost(profile.local_model, "local", 0, 0, 0, profile))

    spec = tracked.last_provider
    if spec is not None:
        tier = "cloud" if spec.kind == "openai_compatible" else "local"
        cost = _cost(spec.model, tier, done.tokens_in, done.tokens_out, done.ms, profile,
                     provider_spec=spec, actual_usd=tracked.actual_usd)
    else:
        cost = _cost(profile.local_model, "local", done.tokens_in, done.tokens_out, done.ms, profile)
    _record(budget_tracker, cost, trace_id, pre_state)

    text = _text_of(done.text)
    if not text:
        return AnswerResult("model_error", None, "empty_answer", spec.name if spec else None, cost)
    return AnswerResult("ok", text, None, spec.name if spec else None, cost)

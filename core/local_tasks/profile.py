"""Perfis: vocabulario, limites e preco de referencia de uma instancia."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from config import settings
from core.budget import BudgetConfig
from core.local_tasks.providers import ProviderSpec, parse_providers

PROFILES_DIR = settings.base_dir / "profiles"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class ProfileNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    labels: dict[str, list[str]]
    local_model: str
    timeout_seconds: int
    max_input_tokens: int
    retries: int
    paid_reference: dict
    max_blocks: int = 4
    keep_alive: str | int = "30m"  # tempo que o Ollama mantém o modelo carregado (-1 = sempre)
    providers: tuple[ProviderSpec, ...] = ()
    budget: BudgetConfig | None = None


def _price(name: str, key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"profile {name}: paid_reference.{key} is not a number")
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"profile {name}: paid_reference.{key} is not a number") from None


def _paid_reference(name: str, raw) -> dict:
    if raw is None or raw == {}:
        return {"model": "none", "input": 0.0, "output": 0.0}
    if not isinstance(raw, dict):
        raise ValueError(f"profile {name}: paid_reference must be a mapping")
    ref = dict(raw)
    for key in ("input", "output"):
        ref[key] = _price(name, key, ref.get(key, 0.0))
    return ref


def load_profile(name: str | None = None, root: Path = PROFILES_DIR) -> Profile:
    name = name if name is not None else os.environ.get("BRAIN_PROFILE") or settings.default_profile
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ProfileNotFound(name)
    path = Path(root) / name / "profile.yaml"
    if not path.is_file():
        raise ProfileNotFound(name)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    labels = data.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise ValueError(f"profile {name}: labels missing")
    timeout_s = int(data.get("timeout_seconds", 30))
    keep_alive_val = data.get("keep_alive", "30m")
    providers = parse_providers(name, data.get("providers"),
                                {"timeout_seconds": timeout_s, "keep_alive": keep_alive_val})
    # Budget config (optional)
    budget_raw = data.get("budget")
    budget_cfg = None
    if budget_raw is not None:
        if not isinstance(budget_raw, dict):
            raise ValueError(f"profile {name}: budget must be a mapping")
        budget_cfg = BudgetConfig(
            daily_usd=float(budget_raw.get("daily_usd", 0.50)),
            monthly_usd=float(budget_raw.get("monthly_usd", 10.0)),
            warn_pct=float(budget_raw.get("warn_pct", 0.80)),
            critical_pct=float(budget_raw.get("critical_pct", 0.95)),
        )
        # Com orcamento, provedor pago sem preco faria o gasto contar US$ 0.
        for i, spec in enumerate(providers):
            if (spec.kind == "openai_compatible"
                    and spec.price["input"] == 0 and spec.price["output"] == 0):
                raise ValueError(
                    f"profile {name}: providers[{i}].price é obrigatório quando o perfil tem budget")

    return Profile(
        name=name,
        labels={str(k): [str(v) for v in vals] for k, vals in labels.items()},
        local_model=data.get("local_model") or settings.chat_model,
        timeout_seconds=timeout_s,
        max_input_tokens=int(data.get("max_input_tokens", 6000)),
        retries=int(data.get("retries", 1)),
        paid_reference=_paid_reference(name, data.get("paid_reference")),
        max_blocks=int(data.get("max_blocks", 4)),
        keep_alive=keep_alive_val,
        providers=providers,
        budget=budget_cfg,
    )

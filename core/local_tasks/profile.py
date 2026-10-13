"""Perfis: vocabulario, limites e preco de referencia de uma instancia."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from config import settings

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
    return Profile(
        name=name,
        labels={str(k): [str(v) for v in vals] for k, vals in labels.items()},
        local_model=data.get("local_model") or settings.chat_model,
        timeout_seconds=int(data.get("timeout_seconds", 30)),
        max_input_tokens=int(data.get("max_input_tokens", 6000)),
        retries=int(data.get("retries", 1)),
        paid_reference=_paid_reference(name, data.get("paid_reference")),
    )

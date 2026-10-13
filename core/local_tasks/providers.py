"""Cadeia de provedores: especificacao, parse e construcao de cliente."""
from __future__ import annotations

from dataclasses import dataclass, field

from config import settings

KINDS = ("openai_compatible", "ollama")
STRUCTURED = ("json_schema", "json_object", "none")


@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    name: str
    model: str
    base_url: str
    api_key_env: str | None = None
    timeout_seconds: int = 30
    keep_alive: str | int = "30m"
    structured: str = "json_schema"
    extra: dict = field(default_factory=dict)
    price: dict = field(default_factory=lambda: {"input": 0.0, "output": 0.0})


def _price_value(name: str, key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"profile {name}: providers[].price.{key} is not a number")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"profile {name}: providers[].price.{key} is not a number") from None


def parse_providers(name: str, raw, defaults: dict) -> tuple[ProviderSpec, ...]:
    """Converte a lista de dicionarios em tupla de ProviderSpec.

    ``defaults`` traz ``timeout_seconds`` e ``keep_alive`` do perfil.
    Levanta ``ValueError`` em caso de configuracao invalida.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"profile {name}: providers must be a list")
    specs: list[ProviderSpec] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"profile {name}: providers[{i}] must be a mapping")
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValueError(f"profile {name}: providers[{i}].kind unknown: {kind!r}")
        model = item.get("model")
        if not model:
            raise ValueError(f"profile {name}: providers[{i}].model is required")
        if kind == "openai_compatible" and not item.get("base_url"):
            raise ValueError(f"profile {name}: providers[{i}].base_url is required for openai_compatible")
        structured = item.get("structured", "json_schema")
        if structured not in STRUCTURED:
            raise ValueError(f"profile {name}: providers[{i}].structured invalid: {structured!r}")
        price_raw = item.get("price") or {}
        if not isinstance(price_raw, dict):
            raise ValueError(f"profile {name}: providers[{i}].price must be a mapping")
        price = {
            "input": _price_value(name, "input", price_raw.get("input", 0.0)),
            "output": _price_value(name, "output", price_raw.get("output", 0.0)),
        }
        base_url = item.get("base_url") or (settings.ollama_url if kind == "ollama" else "")
        specs.append(ProviderSpec(
            kind=kind,
            name=item.get("name") or kind,
            model=str(model),
            base_url=base_url,
            api_key_env=item.get("api_key_env") or None,
            timeout_seconds=int(item.get("timeout_seconds", defaults.get("timeout_seconds", 30))),
            keep_alive=item.get("keep_alive", defaults.get("keep_alive", "30m")),
            structured=structured,
            extra=dict(item.get("extra") or {}),
            price=price,
        ))
    return tuple(specs)

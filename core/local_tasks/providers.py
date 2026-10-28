"""Cadeia de provedores: especificacao, parse e construcao de cliente."""
from __future__ import annotations

import dataclasses
import math
import os
import time
from dataclasses import dataclass, field

from config import settings
from core.local_tasks.ollama_client import LocalModelError, OllamaClient
from core.local_tasks.openai_compat_client import OpenAICompatClient

_clock = time.perf_counter

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


def _price_value(name: str, i: int, key: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"profile {name}: providers[].price.{key} is not a number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"profile {name}: providers[].price.{key} is not a number") from None
    # Preco negativo reduziria o gasto acumulado; NaN/inf corrompem a soma do orcamento.
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"profile {name}: providers[{i}].price.{key} deve ser finito e >= 0")
    return result


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
            "input": _price_value(name, i, "input", price_raw.get("input", 0.0)),
            "output": _price_value(name, i, "output", price_raw.get("output", 0.0)),
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


def is_configured(spec: ProviderSpec) -> bool:
    """A chave exigida pelo provedor esta no ambiente e nao e vazia (ou nao e exigida)."""
    if spec.kind == "openai_compatible" and spec.api_key_env:
        return bool(os.environ.get(spec.api_key_env, ""))
    return True


def probe_client(spec: ProviderSpec, timeout: float):
    """Cliente usado so para sondar a disponibilidade, com o timeout curto do status."""
    if spec.kind == "ollama":
        return OllamaClient(base_url=spec.base_url, timeout=timeout)
    return OpenAICompatClient(base_url=spec.base_url, api_key_env=spec.api_key_env, timeout=timeout)


class FallbackClient:
    """Tenta provedores em ordem; guarda quem respondeu em ``last_provider``.

    ``last_provider`` volta a ``None`` no início de cada chamada: depois de uma chamada em que
    todos falharam, não sobra o provedor de uma resposta anterior. O ``ms`` devolvido soma o
    tempo das tentativas que falharam antes da resposta; o erro final leva esse tempo em ``ms``.
    """

    def __init__(self, entries: list[tuple[ProviderSpec, object]]):
        self.entries = list(entries)
        self.last_provider: ProviderSpec | None = None

    def chat(self, model: str, system: str, user: str, schema: dict):
        self.last_provider = None
        last_error: LocalModelError | None = None
        failed_ms = 0
        for spec, client in self.entries:
            if not is_configured(spec):
                continue  # chave exigida e ausente ou vazia: pula sem chamar
            started = _clock()
            try:
                result = client.chat(spec.model, system, user, schema)
            except LocalModelError as exc:
                failed_ms += int((_clock() - started) * 1000)
                last_error = exc
                continue
            self.last_provider = spec
            if failed_ms:
                result = dataclasses.replace(result, ms=result.ms + failed_ms)
            return result
        if last_error is None:
            last_error = LocalModelError("local_unavailable", "no usable provider")
        last_error.ms = failed_ms
        raise last_error


def build_client(profile):
    """Constroi o cliente conforme o perfil. Sem providers: OllamaClient como antes."""
    if not profile.providers:
        return OllamaClient(
            timeout=profile.timeout_seconds,
            keep_alive=profile.keep_alive,
        )
    entries = []
    for spec in profile.providers:
        if spec.kind == "ollama":
            client = OllamaClient(
                base_url=spec.base_url,
                timeout=spec.timeout_seconds,
                keep_alive=spec.keep_alive,
            )
        else:
            client = OpenAICompatClient(
                base_url=spec.base_url,
                api_key_env=spec.api_key_env,
                timeout=spec.timeout_seconds,
                structured=spec.structured,
                extra=spec.extra,
            )
        entries.append((spec, client))
    return FallbackClient(entries)


def deadline_timeout(profile) -> int:
    """Maior timeout entre os provedores, ou timeout_seconds do perfil sem providers."""
    if not profile.providers:
        return profile.timeout_seconds
    return max(spec.timeout_seconds for spec in profile.providers)

"""Typed cost record for task execution — replaces the untyped dict."""
from __future__ import annotations

from dataclasses import dataclass

_VALID_TIERS = frozenset({"local", "deterministic", "cloud"})


@dataclass(frozen=True, slots=True)
class CostRecord:
    """Immutable record of cost produced by a single ``run_task`` execution.

    Fields mirror the ``cost`` dict already present in the ``task.result``
    envelope (``core/protocol/schemas/envelope.schema.json``).  ``to_dict``
    reproduces the exact dict that ``_cost()`` in ``router.py`` builds today,
    including the rule that ``provider`` and ``actual_usd`` are present
    whenever ``provider is not None``, even when ``actual_usd == 0.0``.
    """

    model: str
    tier: str
    tokens_in: int
    tokens_out: int
    ms: int
    paid_equivalent_usd: float
    provider: str | None = None
    actual_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.tier not in _VALID_TIERS:
            raise ValueError(
                f"tier must be one of {sorted(_VALID_TIERS)}, got {self.tier!r}"
            )

    # ── Serialisation ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Convert to the envelope-compatible dict.

        When ``provider is not None`` both ``provider`` and ``actual_usd``
        are included — even when ``actual_usd`` is ``0.0``.  This matches
        the behaviour of ``router._cost()``.
        """
        d: dict = {
            "model": self.model,
            "tier": self.tier,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "ms": self.ms,
            "paid_equivalent_usd": self.paid_equivalent_usd,
        }
        if self.provider is not None:
            d["provider"] = self.provider
            d["actual_usd"] = self.actual_usd
        return d

    @classmethod
    def from_dict(cls, d: dict) -> CostRecord:
        """Reconstruct from an envelope ``cost`` dict."""
        return cls(
            model=d["model"],
            tier=d["tier"],
            tokens_in=d["tokens_in"],
            tokens_out=d["tokens_out"],
            ms=d["ms"],
            paid_equivalent_usd=d["paid_equivalent_usd"],
            provider=d.get("provider"),
            actual_usd=d.get("actual_usd", 0.0),
        )

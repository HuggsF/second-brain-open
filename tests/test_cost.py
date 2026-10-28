"""Tests for core.cost — CostRecord dataclass."""
from __future__ import annotations

import pytest

from core.cost import CostRecord


# ── Construction ─────────────────────────────────────────────────────


class TestCostRecordConstruction:
    def test_minimal(self):
        cr = CostRecord(
            model="m", tier="local", tokens_in=10, tokens_out=20,
            ms=100, paid_equivalent_usd=0.5,
        )
        assert cr.model == "m"
        assert cr.tier == "local"
        assert cr.provider is None
        assert cr.actual_usd == 0.0

    def test_with_provider(self):
        cr = CostRecord(
            model="m", tier="cloud", tokens_in=10, tokens_out=20,
            ms=100, paid_equivalent_usd=0.5, provider="openrouter",
            actual_usd=0.001,
        )
        assert cr.provider == "openrouter"
        assert cr.actual_usd == 0.001

    def test_invalid_tier_raises(self):
        with pytest.raises(ValueError, match="tier must be one of"):
            CostRecord(
                model="m", tier="fast", tokens_in=0, tokens_out=0,
                ms=0, paid_equivalent_usd=0.0,
            )

    def test_valid_tiers(self):
        for tier in ("local", "deterministic", "cloud"):
            cr = CostRecord(
                model="m", tier=tier, tokens_in=0, tokens_out=0,
                ms=0, paid_equivalent_usd=0.0,
            )
            assert cr.tier == tier

    def test_frozen(self):
        cr = CostRecord(
            model="m", tier="local", tokens_in=0, tokens_out=0,
            ms=0, paid_equivalent_usd=0.0,
        )
        with pytest.raises(AttributeError):
            cr.model = "x"  # type: ignore[misc]


# ── to_dict ──────────────────────────────────────────────────────────


class TestToDict:
    def test_without_provider(self):
        cr = CostRecord(
            model="llama3.2:3b", tier="local", tokens_in=100, tokens_out=50,
            ms=200, paid_equivalent_usd=0.123,
        )
        d = cr.to_dict()
        assert d == {
            "model": "llama3.2:3b",
            "tier": "local",
            "tokens_in": 100,
            "tokens_out": 50,
            "ms": 200,
            "paid_equivalent_usd": 0.123,
        }
        assert "provider" not in d
        assert "actual_usd" not in d

    def test_with_provider_and_zero_actual_usd(self):
        """When provider is not None, both provider and actual_usd are
        included — even when actual_usd is 0.0.  This matches _cost()."""
        cr = CostRecord(
            model="m", tier="cloud", tokens_in=10, tokens_out=20,
            ms=100, paid_equivalent_usd=0.5, provider="openrouter",
            actual_usd=0.0,
        )
        d = cr.to_dict()
        assert d["provider"] == "openrouter"
        assert d["actual_usd"] == 0.0

    def test_with_provider_and_positive_actual_usd(self):
        cr = CostRecord(
            model="deepseek/deepseek-v4-flash-0731", tier="cloud",
            tokens_in=500, tokens_out=200, ms=350,
            paid_equivalent_usd=0.195, provider="openrouter",
            actual_usd=0.00312,
        )
        d = cr.to_dict()
        assert d["provider"] == "openrouter"
        assert d["actual_usd"] == 0.00312
        assert d["paid_equivalent_usd"] == 0.195

    def test_matches_router_cost_dict_local(self):
        """Reproduce what router._cost(model, 'local', 0, 0, 0, profile)
        returns when provider_spec is None."""
        expected = {
            "model": "llama3.2:3b", "tier": "local",
            "tokens_in": 0, "tokens_out": 0, "ms": 0,
            "paid_equivalent_usd": 0.0,
        }
        cr = CostRecord(
            model="llama3.2:3b", tier="local", tokens_in=0, tokens_out=0,
            ms=0, paid_equivalent_usd=0.0,
        )
        assert cr.to_dict() == expected

    def test_matches_router_cost_dict_cloud(self):
        """Reproduce what router._cost() returns when provider_spec is set."""
        expected = {
            "model": "deepseek", "tier": "cloud",
            "tokens_in": 100, "tokens_out": 50, "ms": 200,
            "paid_equivalent_usd": 0.045,
            "provider": "openrouter",
            "actual_usd": 0.001,
        }
        cr = CostRecord(
            model="deepseek", tier="cloud", tokens_in=100, tokens_out=50,
            ms=200, paid_equivalent_usd=0.045, provider="openrouter",
            actual_usd=0.001,
        )
        assert cr.to_dict() == expected


# ── from_dict ────────────────────────────────────────────────────────


class TestFromDict:
    def test_round_trip_without_provider(self):
        cr = CostRecord(
            model="m", tier="deterministic", tokens_in=0, tokens_out=0,
            ms=0, paid_equivalent_usd=0.0,
        )
        assert CostRecord.from_dict(cr.to_dict()) == cr

    def test_round_trip_with_provider(self):
        cr = CostRecord(
            model="deepseek", tier="cloud", tokens_in=100, tokens_out=50,
            ms=200, paid_equivalent_usd=0.045, provider="openrouter",
            actual_usd=0.001,
        )
        assert CostRecord.from_dict(cr.to_dict()) == cr

    def test_from_dict_missing_provider(self):
        d = {
            "model": "m", "tier": "local", "tokens_in": 0,
            "tokens_out": 0, "ms": 0, "paid_equivalent_usd": 0.0,
        }
        cr = CostRecord.from_dict(d)
        assert cr.provider is None
        assert cr.actual_usd == 0.0

    def test_from_dict_missing_actual_usd_defaults_zero(self):
        d = {
            "model": "m", "tier": "cloud", "tokens_in": 10,
            "tokens_out": 20, "ms": 100, "paid_equivalent_usd": 0.5,
            "provider": "openrouter",
        }
        cr = CostRecord.from_dict(d)
        assert cr.actual_usd == 0.0

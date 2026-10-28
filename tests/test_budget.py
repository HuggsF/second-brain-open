"""Tests for core.budget — BudgetTracker with SQLite persistence."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.budget import BudgetConfig, BudgetStatus, BudgetTracker, _to_utc_iso
from core.cost import CostRecord


def _cost(actual_usd: float = 0.0, provider: str | None = None) -> CostRecord:
    return CostRecord(
        model="m", tier="cloud" if provider else "local",
        tokens_in=10, tokens_out=5, ms=100,
        paid_equivalent_usd=0.0, provider=provider,
        actual_usd=actual_usd,
    )


def _eid() -> str:
    return str(uuid.uuid4())


def _tracker(tmp_path: Path, daily: float = 0.50, monthly: float = 10.0) -> BudgetTracker:
    cfg = BudgetConfig(daily_usd=daily, monthly_usd=monthly)
    return BudgetTracker(tmp_path / "budget.db", cfg)


# ── BudgetConfig validation ─────────────────────────────────────────


class TestBudgetConfig:
    def test_defaults(self):
        c = BudgetConfig()
        assert c.daily_usd == 0.50
        assert c.monthly_usd == 10.0
        assert c.warn_pct == 0.80
        assert c.critical_pct == 0.95

    def test_negative_daily_raises(self):
        with pytest.raises(ValueError, match="daily_usd"):
            BudgetConfig(daily_usd=-1)

    def test_warn_pct_out_of_range(self):
        with pytest.raises(ValueError, match="warn_pct"):
            BudgetConfig(warn_pct=1.5)

    def test_warn_ge_critical_raises(self):
        with pytest.raises(ValueError, match="warn_pct.*critical_pct"):
            BudgetConfig(warn_pct=0.95, critical_pct=0.80)


# ── Status states ────────────────────────────────────────────────────


class TestBudgetStates:
    def test_normal(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(0.10, "p"), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "normal"
        assert s.daily_spent == pytest.approx(0.10)
        assert s.daily_remaining == pytest.approx(0.90)

    def test_warning_at_80_percent(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(0.80, "p"), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "warning"
        assert s.limiting_period == "daily"

    def test_critical_at_95_percent(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(0.95, "p"), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "critical"

    def test_exceeded_at_100_percent(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(1.00, "p"), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "exceeded"
        assert s.daily_remaining == 0.0

    def test_exceeded_above_100(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(1.50, "p"), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "exceeded"
        assert s.daily_remaining == 0.0


# ── Monthly limit triggers ───────────────────────────────────────────


class TestMonthlyLimit:
    def test_monthly_triggers_first(self, tmp_path):
        # Daily limit = 10 (high), monthly = 1.0 (low)
        t = _tracker(tmp_path, daily=10.0, monthly=1.0)
        t.record(_cost(0.80, "p"), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "warning"
        assert s.limiting_period == "monthly"


# ── Period rollover ──────────────────────────────────────────────────


class TestPeriodRollover:
    def test_daily_rolls_over(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0, monthly=100.0)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        yesterday_ts = yesterday.isoformat()
        t.record(_cost(0.90, "p"), envelope_id=_eid(), task="classify",
                 ts=yesterday_ts)
        s = t.status()
        assert s.state == "normal"  # Yesterday doesn't count for today
        assert s.daily_spent == 0.0
        assert s.monthly_spent == pytest.approx(0.90)  # But counts for month

    def test_monthly_rolls_over_year_boundary(self, tmp_path):
        t = _tracker(tmp_path, daily=100.0, monthly=1.0)
        # December of last year
        dec = datetime(datetime.now().year - 1, 12, 15, 12, 0, 0, tzinfo=timezone.utc)
        t.record(_cost(0.90, "p"), envelope_id=_eid(), task="classify",
                 ts=dec.isoformat())
        s = t.status()
        assert s.state == "normal"  # December last year != this month
        assert s.monthly_spent == 0.0


# ── Zero cost recording ─────────────────────────────────────────────


class TestZeroCost:
    def test_record_zero_cost(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(0.0), envelope_id=_eid(), task="classify")
        s = t.status()
        assert s.state == "normal"
        assert s.daily_spent == 0.0


# ── Timestamp handling ───────────────────────────────────────────────


class TestTimestamps:
    def test_to_utc_iso_with_offset(self):
        result = _to_utc_iso("2026-10-28T09:00:00-03:00")
        assert "12:00:00" in result  # 09:00 -03:00 = 12:00 UTC

    def test_to_utc_iso_none_returns_current(self):
        result = _to_utc_iso(None)
        assert "+00:00" in result

    def test_record_preserves_custom_ts(self, tmp_path):
        t = _tracker(tmp_path, daily=1.0)
        t.record(_cost(0.10, "p"), envelope_id=_eid(), task="classify",
                 ts="2026-10-28T09:00:00-03:00")
        # Query the raw row
        cur = t._conn.execute("SELECT ts FROM cost_log LIMIT 1")
        stored_ts = cur.fetchone()[0]
        assert "12:00:00" in stored_ts  # Stored as UTC

    def test_ts_with_offset_counts_in_correct_utc_day(self, tmp_path):
        """23:30 local (-03:00) = 02:30 UTC next day."""
        t = _tracker(tmp_path, daily=1.0, monthly=100.0)
        # Use a specific date to avoid edge cases
        t.record(_cost(0.10, "p"), envelope_id=_eid(), task="classify",
                 ts="2026-10-28T23:30:00-03:00")
        # 23:30 -03:00 = 02:30 UTC on Oct 29
        oct28 = datetime(2026, 10, 28, tzinfo=timezone.utc)
        oct29 = datetime(2026, 10, 29, tzinfo=timezone.utc)
        assert t.daily_spent(oct28) == 0.0
        assert t.daily_spent(oct29) == pytest.approx(0.10)


# ── Concurrent writes ────────────────────────────────────────────────


class TestConcurrency:
    def test_concurrent_records(self, tmp_path):
        t = _tracker(tmp_path, daily=100.0)
        errors: list[Exception] = []

        def writer(n: int) -> None:
            try:
                for i in range(10):
                    t.record(_cost(0.01, "p"), envelope_id=_eid(),
                             task=f"task_{n}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == []
        assert t.daily_spent() == pytest.approx(0.40)


# ── Map-reduce cost ──────────────────────────────────────────────────


class TestMapReduceCost:
    def test_accumulated_cost(self, tmp_path):
        """Simulate a summarize map-reduce: 5 blocks × 2 retries = 10 calls."""
        t = _tracker(tmp_path, daily=100.0)
        total = 0.0
        for i in range(10):
            c = 0.0003
            total += c
        # Record the accumulated cost as one entry (as the router does)
        t.record(_cost(total, "p"), envelope_id=_eid(), task="summarize")
        assert t.daily_spent() == pytest.approx(total)

    def test_invalid_response_retry_cost(self, tmp_path):
        """Two calls (1 retry due to schema_invalid) → cost = sum of both."""
        t = _tracker(tmp_path, daily=100.0)
        total = 0.0003 * 2  # 2 calls
        t.record(_cost(total, "p"), envelope_id=_eid(), task="extract")
        assert t.daily_spent() == pytest.approx(total)


# ── Rebuild support ──────────────────────────────────────────────────


class TestRebuild:
    def test_clear_and_rebuild_idempotent(self, tmp_path):
        t = _tracker(tmp_path, daily=100.0)
        eid = _eid()
        t.record(_cost(0.10, "p"), envelope_id=eid, task="classify")

        # First rebuild simulation
        t.clear()
        t.record(_cost(0.10, "p"), envelope_id=eid, task="classify")
        assert t.daily_spent() == pytest.approx(0.10)

        # Second rebuild — same result
        t.clear()
        t.record(_cost(0.10, "p"), envelope_id=eid, task="classify")
        assert t.daily_spent() == pytest.approx(0.10)

    def test_rebuild_reconcile_preserves_concurrent(self, tmp_path):
        """Records inserted into cost_log during population survive the swap."""
        t = _tracker(tmp_path, daily=100.0)

        # Pre-existing record
        eid_old = _eid()
        t.record(_cost(0.10, "p"), envelope_id=eid_old, task="classify")

        # Create staging table and populate from "events"
        t.create_staging_table()
        t.insert_staging(
            envelope_id=eid_old, ts=datetime.now(timezone.utc).isoformat(),
            trace_id=None, task="classify", sender="cli",
            provider="p", model="m", tier="cloud",
            tokens_in=10, tokens_out=5, actual_usd=0.10,
            paid_equivalent_usd=0.0,
        )
        t.commit_staging()

        # Simulate a concurrent record that arrived during population
        eid_concurrent = _eid()
        t.record(_cost(0.05, "p"), envelope_id=eid_concurrent, task="extract")

        # Reconcile and swap
        t.rebuild_reconcile()

        # Both records should survive
        cur = t._conn.execute("SELECT COUNT(*) FROM cost_log")
        assert cur.fetchone()[0] == 2
        assert t.daily_spent() == pytest.approx(0.15)

    def test_rebuild_reconcile_two_executions_same_trace(self, tmp_path):
        """Two executions with same trace_id but different envelope_id
        and different costs: both survive the rebuild."""
        t = _tracker(tmp_path, daily=100.0)
        trace = "shared-trace-id"

        eid1 = _eid()
        eid2 = _eid()
        t.record(_cost(0.10, "p"), envelope_id=eid1, trace_id=trace, task="classify")
        t.record(_cost(0.20, "p"), envelope_id=eid2, trace_id=trace, task="classify")

        # Rebuild: staging has same two records
        t.create_staging_table()
        now_ts = datetime.now(timezone.utc).isoformat()
        t.insert_staging(
            envelope_id=eid1, ts=now_ts, trace_id=trace, task="classify",
            sender="cli", provider="p", model="m", tier="cloud",
            tokens_in=10, tokens_out=5, actual_usd=0.10,
            paid_equivalent_usd=0.0,
        )
        t.insert_staging(
            envelope_id=eid2, ts=now_ts, trace_id=trace, task="classify",
            sender="cli", provider="p", model="m", tier="cloud",
            tokens_in=10, tokens_out=5, actual_usd=0.20,
            paid_equivalent_usd=0.0,
        )
        t.commit_staging()
        t.rebuild_reconcile()

        cur = t._conn.execute("SELECT COUNT(*) FROM cost_log")
        assert cur.fetchone()[0] == 2
        assert t.daily_spent() == pytest.approx(0.30)

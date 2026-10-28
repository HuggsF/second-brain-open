"""Budget tracker — persistent daily/monthly spend tracking with SQLite."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from core.cost import CostRecord

# ── Configuration ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BudgetConfig:
    """Spending limits and alert thresholds.

    Loaded from the ``budget:`` block in the profile YAML.
    """

    daily_usd: float = 0.50
    monthly_usd: float = 10.0
    warn_pct: float = 0.80
    critical_pct: float = 0.95

    def __post_init__(self) -> None:
        if self.daily_usd < 0:
            raise ValueError(f"daily_usd must be >= 0, got {self.daily_usd}")
        if self.monthly_usd < 0:
            raise ValueError(f"monthly_usd must be >= 0, got {self.monthly_usd}")
        if not (0 < self.warn_pct < 1):
            raise ValueError(f"warn_pct must be in (0, 1), got {self.warn_pct}")
        if not (0 < self.critical_pct < 1):
            raise ValueError(f"critical_pct must be in (0, 1), got {self.critical_pct}")
        if self.warn_pct >= self.critical_pct:
            raise ValueError(
                f"warn_pct ({self.warn_pct}) must be < critical_pct ({self.critical_pct})"
            )


BudgetState = Literal["normal", "warning", "critical", "exceeded"]


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    """Snapshot of the current budget state."""

    state: BudgetState
    daily_spent: float
    daily_limit: float
    daily_remaining: float
    monthly_spent: float
    monthly_limit: float
    monthly_remaining: float
    limiting_period: Literal["daily", "monthly"] | None


# ── Helpers ──────────────────────────────────────────────────────────


def _to_utc_iso(ts: str | None) -> str:
    """Parse an ISO 8601 timestamp (possibly with local offset) and return
    a UTC ISO string.  When *ts* is ``None``, return the current UTC time."""
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _utc_date_str(ts_utc: str) -> str:
    """Extract ``YYYY-MM-DD`` from a UTC ISO timestamp."""
    return ts_utc[:10]


def _utc_month_str(ts_utc: str) -> str:
    """Extract ``YYYY-MM`` from a UTC ISO timestamp."""
    return ts_utc[:7]


# ── Schema ───────────────────────────────────────────────────────────

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS cost_log (
    id              INTEGER PRIMARY KEY,
    envelope_id     TEXT UNIQUE,
    ts              TEXT NOT NULL,
    trace_id        TEXT,
    task            TEXT,
    sender          TEXT,
    provider        TEXT,
    model           TEXT,
    tier            TEXT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    actual_usd      REAL NOT NULL DEFAULT 0.0,
    paid_equivalent_usd REAL NOT NULL DEFAULT 0.0
)
"""

_INSERT = """\
INSERT OR IGNORE INTO cost_log
    (envelope_id, ts, trace_id, task, sender, provider, model, tier,
     tokens_in, tokens_out, actual_usd, paid_equivalent_usd)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_COLUMNS_NO_ID = (
    "envelope_id", "ts", "trace_id", "task", "sender", "provider", "model",
    "tier", "tokens_in", "tokens_out", "actual_usd", "paid_equivalent_usd",
)

_SUM_DAY = "SELECT COALESCE(SUM(actual_usd), 0.0) FROM cost_log WHERE ts >= ? AND ts < ?"
_SUM_MONTH = "SELECT COALESCE(SUM(actual_usd), 0.0) FROM cost_log WHERE ts >= ? AND ts < ?"

# ── Tracker ──────────────────────────────────────────────────────────


class BudgetTracker:
    """Persistent budget tracker backed by SQLite in WAL mode.

    Thread-safe: all writes go through a ``threading.Lock`` so that
    concurrent ``record()`` calls are serialised.  Reads (``status()``,
    ``daily_spent()``, etc.) do not acquire the lock and benefit from
    WAL concurrent readers.
    """

    def __init__(self, db_path: str | Path, config: BudgetConfig) -> None:
        self._db_path = str(db_path)
        self._config = config
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ── Write ────────────────────────────────────────────────────────

    def record(
        self,
        cost: CostRecord,
        *,
        envelope_id: str,
        trace_id: str | None = None,
        task: str | None = None,
        sender: str | None = None,
        ts: str | None = None,
    ) -> None:
        """Record a cost entry.  ``ts`` is converted to UTC."""
        ts_utc = _to_utc_iso(ts)
        with self._lock:
            self._conn.execute(_INSERT, (
                envelope_id, ts_utc, trace_id, task, sender,
                cost.provider, cost.model, cost.tier,
                cost.tokens_in, cost.tokens_out,
                cost.actual_usd, cost.paid_equivalent_usd,
            ))
            self._conn.commit()

    # ── Read ─────────────────────────────────────────────────────────

    def status(self) -> BudgetStatus:
        """Current budget status.  Reads are lock-free (WAL)."""
        now = datetime.now(timezone.utc)
        day_start = now.strftime("%Y-%m-%dT00:00:00+00:00")
        day_end = now.strftime("%Y-%m-%dT23:59:59.999999+00:00")
        month_start = now.strftime("%Y-%m-01T00:00:00+00:00")
        # First day of next month
        if now.month == 12:
            next_month = f"{now.year + 1}-01-01T00:00:00+00:00"
        else:
            next_month = f"{now.year}-{now.month + 1:02d}-01T00:00:00+00:00"

        cur = self._conn.cursor()
        cur.execute(_SUM_DAY, (day_start, day_end + "Z"))
        daily_spent = cur.fetchone()[0]
        cur.execute(_SUM_MONTH, (month_start, next_month))
        monthly_spent = cur.fetchone()[0]

        daily_pct = daily_spent / self._config.daily_usd if self._config.daily_usd > 0 else 0.0
        monthly_pct = monthly_spent / self._config.monthly_usd if self._config.monthly_usd > 0 else 0.0

        daily_state = self._classify(daily_pct)
        monthly_state = self._classify(monthly_pct)

        # Most restrictive state wins
        state_order: dict[BudgetState, int] = {
            "normal": 0, "warning": 1, "critical": 2, "exceeded": 3,
        }
        if state_order[daily_state] >= state_order[monthly_state]:
            state = daily_state
            limiting = "daily" if state != "normal" else None
        else:
            state = monthly_state
            limiting = "monthly" if state != "normal" else None

        return BudgetStatus(
            state=state,
            daily_spent=daily_spent,
            daily_limit=self._config.daily_usd,
            daily_remaining=max(0.0, self._config.daily_usd - daily_spent),
            monthly_spent=monthly_spent,
            monthly_limit=self._config.monthly_usd,
            monthly_remaining=max(0.0, self._config.monthly_usd - monthly_spent),
            limiting_period=limiting,
        )

    def daily_spent(self, date: datetime | None = None) -> float:
        """Total ``actual_usd`` for a single UTC day."""
        d = date or datetime.now(timezone.utc)
        day_start = d.strftime("%Y-%m-%dT00:00:00+00:00")
        day_end = d.strftime("%Y-%m-%dT23:59:59.999999+00:00")
        cur = self._conn.execute(_SUM_DAY, (day_start, day_end + "Z"))
        return cur.fetchone()[0]

    def monthly_spent(self, year: int, month: int) -> float:
        """Total ``actual_usd`` for a calendar month."""
        month_start = f"{year}-{month:02d}-01T00:00:00+00:00"
        if month == 12:
            next_month = f"{year + 1}-01-01T00:00:00+00:00"
        else:
            next_month = f"{year}-{month + 1:02d}-01T00:00:00+00:00"
        cur = self._conn.execute(_SUM_MONTH, (month_start, next_month))
        return cur.fetchone()[0]

    def history(self, days: int = 7) -> list[dict]:
        """Daily spend for the last *days* days."""
        now = datetime.now(timezone.utc)
        rows: list[dict] = []
        for offset in range(days - 1, -1, -1):
            from datetime import timedelta
            d = now - timedelta(days=offset)
            spent = self.daily_spent(d)
            rows.append({"date": d.strftime("%Y-%m-%d"), "actual_usd": spent})
        return rows

    # ── Rebuild support ──────────────────────────────────────────────

    def clear(self) -> None:
        """Drop and recreate the table (used by ``--rebuild``)."""
        with self._lock:
            self._conn.execute("DROP TABLE IF EXISTS cost_log")
            self._conn.execute(_CREATE_TABLE)
            self._conn.commit()

    def rebuild_reconcile(self) -> None:
        """Reconcile: copy records from cost_log that are not in
        cost_log_new, then swap tables.  Must be called after populating
        cost_log_new externally.  Uses an exclusive transaction."""
        cols = ", ".join(_COLUMNS_NO_ID)
        with self._lock:
            self._conn.execute("BEGIN EXCLUSIVE")
            try:
                self._conn.execute(
                    f"INSERT INTO cost_log_new ({cols}) "
                    f"SELECT {cols} FROM cost_log "
                    f"WHERE envelope_id NOT IN (SELECT envelope_id FROM cost_log_new)"
                )
                self._conn.execute("DROP TABLE IF EXISTS cost_log")
                self._conn.execute("ALTER TABLE cost_log_new RENAME TO cost_log")
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def create_staging_table(self) -> None:
        """Create the staging table for rebuild population.

        Opens a **separate** SQLite connection in autocommit mode so
        that staging inserts do not hold a persistent write lock that
        would block ``record()`` on the main connection.  Each
        ``insert_staging()`` call commits immediately; the write lock
        is held only for the duration of each individual INSERT.
        """
        self._staging_conn = sqlite3.connect(
            self._db_path, check_same_thread=False, isolation_level=None)
        self._staging_conn.execute("PRAGMA journal_mode=WAL")
        self._staging_conn.execute("PRAGMA busy_timeout=5000")
        self._staging_conn.execute("DROP TABLE IF EXISTS cost_log_new")
        self._staging_conn.execute(_CREATE_TABLE.replace("cost_log", "cost_log_new"))

    def insert_staging(
        self,
        envelope_id: str,
        ts: str,
        trace_id: str | None,
        task: str | None,
        sender: str | None,
        provider: str | None,
        model: str | None,
        tier: str | None,
        tokens_in: int,
        tokens_out: int,
        actual_usd: float,
        paid_equivalent_usd: float,
    ) -> None:
        """Insert a row into the staging table (for rebuild).

        Commits immediately (autocommit connection) so the write lock
        is released between inserts and ``record()`` is never blocked.
        """
        ts_utc = _to_utc_iso(ts)
        self._staging_conn.execute(
            _INSERT.replace("cost_log", "cost_log_new"),
            (envelope_id, ts_utc, trace_id, task, sender, provider, model, tier,
             tokens_in, tokens_out, actual_usd, paid_equivalent_usd),
        )

    def commit_staging(self) -> None:
        """Close the staging connection.

        Since each ``insert_staging()`` auto-commits, there is nothing
        pending.  The staging table is already visible to all WAL
        readers.  ``rebuild_reconcile()`` proceeds on the main connection.
        """
        self._staging_conn.close()
        self._staging_conn = None

    # ── Internal ─────────────────────────────────────────────────────

    def _classify(self, pct: float) -> BudgetState:
        if pct >= 1.0:
            return "exceeded"
        if pct >= self._config.critical_pct:
            return "critical"
        if pct >= self._config.warn_pct:
            return "warning"
        return "normal"

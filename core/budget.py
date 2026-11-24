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


# ── Failed sentinel ──────────────────────────────────────────────────


class FailedBudgetTracker:
    """Sentinel returned when budget IS configured but SQLite init failed.

    Reports ``exceeded`` state so the router blocks cloud calls or falls
    back to local execution.  ``record()`` is a silent no-op.
    The caller retries real init on the next invocation.
    """

    def __init__(self, config: BudgetConfig) -> None:
        self._config = config

    def status(self) -> BudgetStatus:
        return BudgetStatus(
            state="exceeded",
            daily_spent=self._config.daily_usd,
            daily_limit=self._config.daily_usd,
            daily_remaining=0.0,
            monthly_spent=self._config.monthly_usd,
            monthly_limit=self._config.monthly_usd,
            monthly_remaining=0.0,
            limiting_period="daily",
        )

    def record(self, *args, **kwargs) -> None:
        """No-op — cannot record without a database."""


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

_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_cost_log_ts ON cost_log(ts)"

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

# ── Custo equivalente da assinatura (fora do orçamento) ──────────────

_PROVEDOR_ASSINATURA = "assinatura"

# actual_usd de todas as linhas; paid_equivalent_usd só das linhas da assinatura
# (nas outras ele é o preço de referência de uma chamada já cobrada ou local).
_SOMA_EQUIVALENTE = (
    "SELECT trace_id, SUM(actual_usd"
    f" + CASE WHEN provider = '{_PROVEDOR_ASSINATURA}' THEN paid_equivalent_usd ELSE 0 END) FROM cost_log"
    " WHERE trace_id IN ({marcadores}) GROUP BY trace_id"
)


def _ids_validos(trace_ids: list[str]) -> list[str]:
    return [t for t in dict.fromkeys(trace_ids) if t]


def registrar_custo_assinatura(
    db_path: str | Path,
    *,
    envelope_id: str,
    trace_id: str,
    task: str,
    modelo: str,
    tokens_in: int,
    tokens_out: int,
    paid_equivalent_usd: float,
    ts: str | None = None,
) -> bool:
    """Grava o custo equivalente de uma sessão coberta por assinatura.

    ``actual_usd`` fica em 0: o registro não entra no orçamento diário nem
    mensal. Retorna ``True`` se inseriu e ``False`` se o ``envelope_id`` já existia.
    """
    return registrar_custos_assinatura(db_path, [dict(
        envelope_id=envelope_id, trace_id=trace_id, task=task, modelo=modelo,
        tokens_in=tokens_in, tokens_out=tokens_out,
        paid_equivalent_usd=paid_equivalent_usd, ts=ts)])[0]


def registrar_custos_assinatura(db_path: str | Path, linhas: list[dict]) -> list[bool]:
    """Lote de :func:`registrar_custo_assinatura` numa conexão e numa transação.

    Cada linha leva as mesmas chaves (``ts`` opcional). Devolve, na ordem, ``True`` para
    cada linha inserida e ``False`` para ``envelope_id`` repetido. Lote vazio não abre o banco.
    """
    if not linhas:
        return []
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_INDEX)
        inseridas = []
        for linha in linhas:
            cur = conn.execute(_INSERT, (
                linha["envelope_id"], _to_utc_iso(linha.get("ts")), linha["trace_id"], linha["task"],
                "sessao-ide", _PROVEDOR_ASSINATURA, linha["modelo"], "cloud",
                linha["tokens_in"], linha["tokens_out"], 0.0, linha["paid_equivalent_usd"],
            ))
            inseridas.append(cur.rowcount == 1)
        conn.commit()
        return inseridas
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def equivalente_por_trace(db_path: str | Path, trace_ids: list[str]) -> dict[str, float]:
    """Por ``trace_id``: ``actual_usd`` de tudo mais ``paid_equivalent_usd`` da assinatura."""
    ids = _ids_validos(trace_ids)
    if not ids:
        return {}
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        conn.execute(_CREATE_TABLE)
        marcadores = ",".join("?" for _ in ids)
        cur = conn.execute(_SOMA_EQUIVALENTE.format(marcadores=marcadores), ids)
        return {r[0]: float(r[1]) for r in cur.fetchall()}
    finally:
        conn.close()


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
        self._conn.execute(_CREATE_INDEX)
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

        # A limit of 0 means "no paid spend allowed": always exceeded.
        daily_pct = self._pct(daily_spent, self._config.daily_usd)
        monthly_pct = self._pct(monthly_spent, self._config.monthly_usd)

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

    def resumo(self, dias: int = 30, ultimas: int = 20) -> dict:
        """Gasto agregado para painel: por dia, por origem e últimas chamadas.

        ``por_dia`` traz todos os dias da janela (mais antigo primeiro), inclusive os sem gasto.
        """
        if not isinstance(dias, int) or not 1 <= dias <= 365:
            raise ValueError(f"dias deve ficar entre 1 e 365, recebido {dias!r}")
        from datetime import timedelta
        hoje = datetime.now(timezone.utc).date()
        inicio = hoje - timedelta(days=dias - 1)
        desde = f"{inicio.isoformat()}T00:00:00+00:00"
        cur = self._conn.cursor()

        cur.execute(
            "SELECT substr(ts, 1, 10), COUNT(*), COALESCE(SUM(actual_usd), 0),"
            " COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0)"
            " FROM cost_log WHERE ts >= ? GROUP BY substr(ts, 1, 10)", (desde,))
        por_data = {r[0]: r for r in cur.fetchall()}
        por_dia = []
        for i in range(dias):
            data = (inicio + timedelta(days=i)).isoformat()
            r = por_data.get(data)
            por_dia.append({
                "data": data,
                "chamadas": r[1] if r else 0,
                "usd": float(r[2]) if r else 0.0,
                "tokens_in": int(r[3]) if r else 0,
                "tokens_out": int(r[4]) if r else 0,
            })

        cur.execute(
            "SELECT task, sender, COUNT(*), COALESCE(SUM(actual_usd), 0),"
            " COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0)"
            " FROM cost_log WHERE ts >= ? GROUP BY task, sender"
            " ORDER BY SUM(actual_usd) DESC, COUNT(*) DESC", (desde,))
        por_origem = [
            {"tarefa": r[0], "remetente": r[1], "chamadas": r[2], "usd": float(r[3]),
             "tokens_in": int(r[4]), "tokens_out": int(r[5])}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT ts, task, sender, model, tokens_in, tokens_out, actual_usd, trace_id"
            " FROM cost_log ORDER BY ts DESC, id DESC LIMIT ?", (max(0, int(ultimas)),))
        recentes = [
            {"ts": r[0], "tarefa": r[1], "remetente": r[2], "modelo": r[3],
             "tokens_in": r[4], "tokens_out": r[5], "usd": float(r[6]), "trace_id": r[7]}
            for r in cur.fetchall()
        ]
        return {"por_dia": por_dia, "por_origem": por_origem, "ultimas": recentes}

    def usd_por_trace(self, trace_ids: list[str]) -> dict[str, float]:
        """Soma de ``actual_usd`` por ``trace_id``; ids sem registro ficam de fora."""
        ids = [t for t in dict.fromkeys(trace_ids) if t]
        if not ids:
            return {}
        marcadores = ",".join("?" for _ in ids)
        cur = self._conn.execute(
            f"SELECT trace_id, SUM(actual_usd) FROM cost_log WHERE trace_id IN ({marcadores})"
            " GROUP BY trace_id", ids)
        return {r[0]: float(r[1]) for r in cur.fetchall()}

    def equivalente_por_trace(self, trace_ids: list[str]) -> dict[str, float]:
        """Por ``trace_id``: ``actual_usd`` de tudo mais ``paid_equivalent_usd`` da assinatura."""
        ids = _ids_validos(trace_ids)
        if not ids:
            return {}
        marcadores = ",".join("?" for _ in ids)
        cur = self._conn.execute(_SOMA_EQUIVALENTE.format(marcadores=marcadores), ids)
        return {r[0]: float(r[1]) for r in cur.fetchall()}

    # ── Rebuild support ──────────────────────────────────────────────

    def clear(self) -> None:
        """Drop and recreate the table (used by ``--rebuild``)."""
        with self._lock:
            self._conn.execute("DROP TABLE IF EXISTS cost_log")
            self._conn.execute(_CREATE_TABLE)
            self._conn.execute(_CREATE_INDEX)
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
                self._conn.execute(_CREATE_INDEX)
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

    @staticmethod
    def _pct(spent: float, limit: float) -> float:
        if limit <= 0:
            return float("inf")
        return spent / limit

    def _classify(self, pct: float) -> BudgetState:
        if pct >= 1.0:
            return "exceeded"
        if pct >= self._config.critical_pct:
            return "critical"
        if pct >= self._config.warn_pct:
            return "warning"
        return "normal"

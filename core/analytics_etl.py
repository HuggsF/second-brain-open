"""ETL pipeline for Hub Logístico analytics data.

Extracts aggregate data from the Hub's SQLite via SSH, stores locally
in data/analytics.db for statistical analysis. No PII stored (NEG-03).
"""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import paramiko
from dotenv import load_dotenv

from config import settings

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
PIN = ROOT / ".runtime" / "known_hosts"
ANALYTICS_DB = ROOT / "data" / "analytics.db"

# --- SSH helper (same pattern as hub_observability_mcp.py) ---

def _ssh_exec(command: str) -> str:
    """Opens SSH session to SRV-API, runs one read-only command, returns stdout."""
    client = paramiko.SSHClient()
    try:
        client.load_host_keys(str(PIN))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        key = paramiko.RSAKey.from_private_key_file(
            os.getenv("SRV_API_KEY_PATH", r"C:\KIOSK\SRV-API_key.pem"))
        client.connect(
            os.getenv("SRV_API_HOST", "191.233.18.195"),
            port=int(os.getenv("SRV_API_PORT", "22")),
            username=os.getenv("SRV_API_USER", "ti-kiosk"),
            pkey=key, timeout=15,
            banner_timeout=15, auth_timeout=15,
            allow_agent=False, look_for_keys=False)
        _, stdout, _ = client.exec_command(command, timeout=60)
        data = stdout.read(512 * 1024 + 1)
        if len(data) > 512 * 1024:
            raise ValueError("Oversized response")
        return data.decode("utf-8")
    except Exception:
        raise RuntimeError("SSH_UNAVAILABLE") from None
    finally:
        client.close()


def _hub_db_path(environment: str = "production") -> str:
    """Returns the SQLite DB path on the server."""
    if environment == "production":
        return "/home/ti-kiosk/hub/hub.db"
    return "/home/ti-kiosk/hub-homolog/hub.db"


def _hub_query(sql: str, environment: str = "production") -> str:
    """Runs a SELECT query on the Hub SQLite DB via SSH. Only SELECT allowed."""
    sql_clean = sql.strip().rstrip(";")
    if not sql_clean.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed (NEG-02)")
    db_path = _hub_db_path(environment)
    # Use sqlite3 CLI with JSON mode for structured output
    command = f'sqlite3 -json "{db_path}" "{sql_clean};"'
    return _ssh_exec(command)


# --- Batched SSH session (NEG-09: max 1 SSH connection per ETL cycle) ---

@contextmanager
def _ssh_session():
    """Context manager that yields a connected SSH client. Use for batched queries (NEG-09)."""
    client = paramiko.SSHClient()
    try:
        client.load_host_keys(str(PIN))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        key = paramiko.RSAKey.from_private_key_file(
            os.getenv("SRV_API_KEY_PATH", r"C:\KIOSK\SRV-API_key.pem"))
        client.connect(
            os.getenv("SRV_API_HOST", "191.233.18.195"),
            port=int(os.getenv("SRV_API_PORT", "22")),
            username=os.getenv("SRV_API_USER", "ti-kiosk"),
            pkey=key, timeout=15,
            banner_timeout=15, auth_timeout=15,
            allow_agent=False, look_for_keys=False)
        yield client
    finally:
        client.close()


def _hub_query_on(client: paramiko.SSHClient, sql: str, environment: str = "production") -> str:
    """Runs a SELECT query on the Hub SQLite DB using an existing SSH client."""
    sql_clean = sql.strip().rstrip(";")
    if not sql_clean.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed (NEG-02)")
    db_path = _hub_db_path(environment)
    command = f'sqlite3 -json "{db_path}" "{sql_clean};"'
    _, stdout, _ = client.exec_command(command, timeout=60)
    data = stdout.read(512 * 1024 + 1)
    if len(data) > 512 * 1024:
        raise ValueError("Oversized response")
    return data.decode("utf-8")


# --- Local analytics DB ---

def _ensure_analytics_db() -> sqlite3.Connection:
    """Creates the local analytics DB and tables if they don't exist."""
    ANALYTICS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ANALYTICS_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS emission_daily (
            date TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'production',
            total_orders INTEGER DEFAULT 0,
            successful INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            review_required INTEGER DEFAULT 0,
            avg_retry_count REAL DEFAULT 0,
            avg_processing_seconds REAL DEFAULT 0,
            extracted_at TEXT NOT NULL,
            PRIMARY KEY (date, environment)
        );

        CREATE TABLE IF NOT EXISTS error_patterns (
            date TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'production',
            error_type TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            last_message TEXT,
            extracted_at TEXT NOT NULL,
            PRIMARY KEY (date, environment, error_type)
        );

        CREATE TABLE IF NOT EXISTS throughput_hourly (
            date TEXT NOT NULL,
            hour INTEGER NOT NULL,
            environment TEXT NOT NULL DEFAULT 'production',
            emissions_started INTEGER DEFAULT 0,
            emissions_completed INTEGER DEFAULT 0,
            avg_duration_seconds REAL DEFAULT 0,
            extracted_at TEXT NOT NULL,
            PRIMARY KEY (date, hour, environment)
        );

        CREATE TABLE IF NOT EXISTS logistics_status (
            date TEXT NOT NULL,
            environment TEXT NOT NULL DEFAULT 'production',
            total_with_logistics INTEGER DEFAULT 0,
            total_without_logistics INTEGER DEFAULT 0,
            review_logistics_missing INTEGER DEFAULT 0,
            review_multiple_volumes INTEGER DEFAULT 0,
            extracted_at TEXT NOT NULL,
            PRIMARY KEY (date, environment)
        );
    """)
    conn.commit()
    return conn


# --- ETL Extraction Queries ---

_DAILY_STATS_SQL = """
SELECT
    date(created_at) as date,
    COUNT(*) as total_orders,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    SUM(CASE WHEN status LIKE '%REVIEW%' THEN 1 ELSE 0 END) as review_required,
    AVG(retry_count) as avg_retry_count,
    AVG(CASE WHEN completed_at IS NOT NULL
        THEN (julianday(completed_at) - julianday(created_at)) * 86400
        ELSE NULL END) as avg_processing_seconds
FROM orders_queue
WHERE created_at >= date('now', '-{days} days')
GROUP BY date(created_at)
ORDER BY date DESC
"""

_ERROR_PATTERNS_SQL = """
SELECT
    date(timestamp) as date,
    CASE
        WHEN message LIKE '%429%' OR message LIKE '%rate limit%' THEN 'RATE_LIMIT'
        WHEN message LIKE '%timeout%' OR message LIKE '%ETIMEDOUT%' THEN 'TIMEOUT'
        WHEN message LIKE '%REVIEW_REQUIRED%' THEN 'REVIEW_REQUIRED'
        WHEN message LIKE '%uncertain%' THEN 'UNCERTAIN_STATE'
        WHEN message LIKE '%cancel%' THEN 'CANCELLATION'
        ELSE 'OTHER'
    END as error_type,
    COUNT(*) as count,
    MAX(message) as last_message
FROM system_logs
WHERE level IN ('error', 'warn')
    AND timestamp >= date('now', '-{days} days')
GROUP BY date(timestamp), error_type
ORDER BY date DESC, count DESC
"""

_THROUGHPUT_HOURLY_SQL = """
SELECT
    date(created_at) as date,
    CAST(strftime('%H', created_at) AS INTEGER) as hour,
    COUNT(*) as emissions_started,
    SUM(CASE WHEN status IN ('success', 'confirmed') THEN 1 ELSE 0 END) as emissions_completed,
    AVG(CASE WHEN completed_at IS NOT NULL
        THEN (julianday(completed_at) - julianday(created_at)) * 86400
        ELSE NULL END) as avg_duration_seconds
FROM orders_queue
WHERE created_at >= date('now', '-{days} days')
GROUP BY date(created_at), CAST(strftime('%H', created_at) AS INTEGER)
ORDER BY date DESC, hour
"""

_LOGISTICS_STATUS_SQL = """
SELECT
    date(oq.created_at) as date,
    SUM(CASE WHEN blc.id IS NOT NULL THEN 1 ELSE 0 END) as total_with_logistics,
    SUM(CASE WHEN blc.id IS NULL THEN 1 ELSE 0 END) as total_without_logistics,
    SUM(CASE WHEN oq.status LIKE '%LOGISTICS_OBJECT_MISSING%' THEN 1 ELSE 0 END) as review_logistics_missing,
    SUM(CASE WHEN oq.status LIKE '%MULTIPLE_VOLUMES%' THEN 1 ELSE 0 END) as review_multiple_volumes
FROM orders_queue oq
LEFT JOIN bling_logistics_creations blc ON oq.erp_id = blc.erp_order_id
WHERE oq.created_at >= date('now', '-{days} days')
GROUP BY date(oq.created_at)
ORDER BY date DESC
"""


def extract_and_store(days: int = 7, environment: str = "production") -> Dict[str, Any]:
    """Run the full ETL: extract from Hub via SSH, store in local analytics DB."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _ensure_analytics_db()
    results = {"extracted_at": now, "environment": environment, "tables": {}}

    try:
        with _ssh_session() as client:
            # 1. Daily stats
            raw = _hub_query_on(client, _DAILY_STATS_SQL.format(days=days), environment)
            rows = json.loads(raw) if raw.strip() else []
            for row in rows:
                conn.execute("""
                    INSERT OR REPLACE INTO emission_daily
                    (date, environment, total_orders, successful, failed, review_required,
                     avg_retry_count, avg_processing_seconds, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (row["date"], environment, row["total_orders"], row["successful"],
                      row["failed"], row["review_required"],
                      row.get("avg_retry_count", 0), row.get("avg_processing_seconds", 0), now))
            results["tables"]["emission_daily"] = len(rows)

            # 2. Error patterns
            raw = _hub_query_on(client, _ERROR_PATTERNS_SQL.format(days=days), environment)
            rows = json.loads(raw) if raw.strip() else []
            for row in rows:
                # Sanitize: truncate last_message, remove any PII patterns
                msg = (row.get("last_message") or "")[:200]
                msg = re.sub(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', '[CPF]', msg)
                msg = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[EMAIL]', msg)
                conn.execute("""
                    INSERT OR REPLACE INTO error_patterns
                    (date, environment, error_type, count, last_message, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row["date"], environment, row["error_type"], row["count"], msg, now))
            results["tables"]["error_patterns"] = len(rows)

            # 3. Throughput hourly
            raw = _hub_query_on(client, _THROUGHPUT_HOURLY_SQL.format(days=days), environment)
            rows = json.loads(raw) if raw.strip() else []
            for row in rows:
                conn.execute("""
                    INSERT OR REPLACE INTO throughput_hourly
                    (date, hour, environment, emissions_started, emissions_completed,
                     avg_duration_seconds, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (row["date"], row["hour"], environment, row["emissions_started"],
                      row["emissions_completed"], row.get("avg_duration_seconds", 0), now))
            results["tables"]["throughput_hourly"] = len(rows)

            # 4. Logistics status
            raw = _hub_query_on(client, _LOGISTICS_STATUS_SQL.format(days=days), environment)
            rows = json.loads(raw) if raw.strip() else []
            for row in rows:
                conn.execute("""
                    INSERT OR REPLACE INTO logistics_status
                    (date, environment, total_with_logistics, total_without_logistics,
                     review_logistics_missing, review_multiple_volumes, extracted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (row["date"], environment, row.get("total_with_logistics", 0),
                      row.get("total_without_logistics", 0), row.get("review_logistics_missing", 0),
                      row.get("review_multiple_volumes", 0), now))
            results["tables"]["logistics_status"] = len(rows)

            conn.commit()
    except Exception as e:
        results["error"] = str(e)
    finally:
        conn.close()

    return results


# --- Statistical Analysis Functions ---

def get_emission_trends(days: int = 30) -> Dict[str, Any]:
    """Compute emission trends and simple predictions from local data."""
    conn = _ensure_analytics_db()
    try:
        rows = conn.execute("""
            SELECT date, total_orders, successful, failed, review_required,
                   avg_retry_count, avg_processing_seconds
            FROM emission_daily
            WHERE date >= date('now', ? || ' days')
            ORDER BY date ASC
        """, (f"-{days}",)).fetchall()

        if not rows:
            return {"error": "No data available. Run ETL first."}

        dates = [r[0] for r in rows]
        totals = [r[1] for r in rows]
        successes = [r[2] for r in rows]
        failures = [r[3] for r in rows]
        reviews = [r[4] for r in rows]

        n = len(totals)
        avg_total = sum(totals) / n if n else 0
        avg_success_rate = sum(successes) / sum(totals) * 100 if sum(totals) else 0
        avg_failure_rate = sum(failures) / sum(totals) * 100 if sum(totals) else 0

        # Simple linear trend (slope)
        if n >= 2:
            x_mean = (n - 1) / 2
            y_mean = sum(totals) / n
            numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(totals))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            slope = numerator / denominator if denominator else 0
            trend = "increasing" if slope > 0.5 else "decreasing" if slope < -0.5 else "stable"
        else:
            slope = 0
            trend = "insufficient_data"

        return {
            "period": {"start": dates[0], "end": dates[-1], "days": n},
            "summary": {
                "avg_daily_orders": round(avg_total, 1),
                "avg_success_rate": round(avg_success_rate, 1),
                "avg_failure_rate": round(avg_failure_rate, 1),
                "total_reviews": sum(reviews),
            },
            "trend": {
                "direction": trend,
                "daily_change": round(slope, 2),
                "projected_next_day": round(totals[-1] + slope, 0) if totals else 0,
            },
            "daily_data": [
                {"date": d, "total": t, "success": s, "failed": f, "review": rv}
                for d, t, s, f, rv in zip(dates, totals, successes, failures, reviews)
            ][-14:]  # last 14 days for display
        }
    finally:
        conn.close()


def get_error_analysis(days: int = 14) -> Dict[str, Any]:
    """Analyze error patterns and frequencies."""
    conn = _ensure_analytics_db()
    try:
        rows = conn.execute("""
            SELECT error_type, SUM(count) as total, MAX(date) as last_seen
            FROM error_patterns
            WHERE date >= date('now', ? || ' days')
            GROUP BY error_type
            ORDER BY total DESC
        """, (f"-{days}",)).fetchall()

        daily = conn.execute("""
            SELECT date, SUM(count) as total_errors
            FROM error_patterns
            WHERE date >= date('now', ? || ' days')
            GROUP BY date
            ORDER BY date ASC
        """, (f"-{days}",)).fetchall()

        return {
            "period_days": days,
            "by_type": [
                {"type": r[0], "total": r[1], "last_seen": r[2]}
                for r in rows
            ],
            "daily_trend": [
                {"date": r[0], "total_errors": r[1]}
                for r in daily
            ],
            "top_issue": rows[0][0] if rows else "none",
        }
    finally:
        conn.close()


def get_throughput_analysis(days: int = 7) -> Dict[str, Any]:
    """Analyze throughput patterns by hour of day."""
    conn = _ensure_analytics_db()
    try:
        rows = conn.execute("""
            SELECT hour,
                   AVG(emissions_started) as avg_started,
                   AVG(emissions_completed) as avg_completed,
                   AVG(avg_duration_seconds) as avg_duration
            FROM throughput_hourly
            WHERE date >= date('now', ? || ' days')
            GROUP BY hour
            ORDER BY hour
        """, (f"-{days}",)).fetchall()

        if not rows:
            return {"error": "No data available. Run ETL first."}

        peak_hour = max(rows, key=lambda r: r[1])
        low_hour = min(rows, key=lambda r: r[1])

        return {
            "period_days": days,
            "hourly_avg": [
                {"hour": r[0], "avg_started": round(r[1], 1),
                 "avg_completed": round(r[2], 1), "avg_duration_s": round(r[3] or 0, 1)}
                for r in rows
            ],
            "peak": {"hour": peak_hour[0], "avg_emissions": round(peak_hour[1], 1)},
            "low": {"hour": low_hour[0], "avg_emissions": round(low_hour[1], 1)},
            "recommended_maintenance_window": f"{low_hour[0]:02d}:00-{(low_hour[0]+2)%24:02d}:00 UTC",
        }
    finally:
        conn.close()


def get_logistics_health(days: int = 14) -> Dict[str, Any]:
    """Analyze logistics object health and missing/multiple volume issues."""
    conn = _ensure_analytics_db()
    try:
        rows = conn.execute("""
            SELECT date, total_with_logistics, total_without_logistics,
                   review_logistics_missing, review_multiple_volumes
            FROM logistics_status
            WHERE date >= date('now', ? || ' days')
            ORDER BY date ASC
        """, (f"-{days}",)).fetchall()

        if not rows:
            return {"error": "No data available. Run ETL first."}

        total_with = sum(r[1] for r in rows)
        total_without = sum(r[2] for r in rows)
        total_missing = sum(r[3] for r in rows)
        total_multi = sum(r[4] for r in rows)
        grand_total = total_with + total_without

        return {
            "period_days": days,
            "summary": {
                "logistics_coverage_pct": round(total_with / grand_total * 100, 1) if grand_total else 0,
                "total_missing_reviews": total_missing,
                "total_multi_volume_reviews": total_multi,
            },
            "daily": [
                {"date": r[0], "with_logistics": r[1], "without": r[2],
                 "missing_review": r[3], "multi_volume_review": r[4]}
                for r in rows
            ],
        }
    finally:
        conn.close()

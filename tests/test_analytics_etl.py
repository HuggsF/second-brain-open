"""Tests for T5 — analytics ETL pipeline (unit tests, no SSH needed)."""
import json
import pytest
import sqlite3
from pathlib import Path
from unittest import mock

from core.analytics_etl import (
    _ensure_analytics_db,
    _hub_query,
    get_emission_trends,
    get_error_analysis,
    get_throughput_analysis,
    get_logistics_health,
    ANALYTICS_DB,
)


class TestAnalyticsDB:
    def test_ensure_creates_tables(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("core.analytics_etl.ANALYTICS_DB", db_path)
        conn = _ensure_analytics_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "emission_daily" in table_names
        assert "error_patterns" in table_names
        assert "throughput_hourly" in table_names
        assert "logistics_status" in table_names
        conn.close()


class TestHubQuery:
    def test_rejects_non_select(self):
        with pytest.raises(ValueError, match="Only SELECT"):
            _hub_query("DELETE FROM orders_queue")

    def test_rejects_insert(self):
        with pytest.raises(ValueError, match="Only SELECT"):
            _hub_query("INSERT INTO orders_queue VALUES (1)")

    def test_rejects_update(self):
        with pytest.raises(ValueError, match="Only SELECT"):
            _hub_query("UPDATE orders_queue SET status='x'")


class TestStatisticalFunctions:
    def test_emission_trends_no_data(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("core.analytics_etl.ANALYTICS_DB", db_path)
        _ensure_analytics_db()
        result = get_emission_trends(30)
        assert "error" in result

    def test_error_analysis_no_data(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("core.analytics_etl.ANALYTICS_DB", db_path)
        _ensure_analytics_db()
        result = get_error_analysis(14)
        assert result["by_type"] == []

    def test_emission_trends_with_data(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("core.analytics_etl.ANALYTICS_DB", db_path)
        conn = _ensure_analytics_db()
        # Insert sample data
        for i in range(5):
            conn.execute("""
                INSERT INTO emission_daily
                (date, environment, total_orders, successful, failed, review_required,
                 avg_retry_count, avg_processing_seconds, extracted_at)
                VALUES (date('now', ? || ' days'), 'production', ?, ?, ?, ?, 1.5, 45.0, datetime('now'))
            """, (f"-{i}", 100 + i * 10, 90 + i * 8, 5, 5 + i, ))
        conn.commit()
        conn.close()

        result = get_emission_trends(30)
        assert "error" not in result
        assert "summary" in result
        assert result["summary"]["avg_daily_orders"] > 0
        assert "trend" in result
        assert result["trend"]["direction"] in ("increasing", "decreasing", "stable")

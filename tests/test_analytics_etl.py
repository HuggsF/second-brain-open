"""Tests for T5 — analytics ETL pipeline (unit tests, no SSH needed)."""
import json
import pytest
import sqlite3
from pathlib import Path
from unittest import mock

from core.analytics_etl import (
    _ensure_analytics_db,
    _hub_query,
    _hub_query_on,
    _ssh_session,
    extract_and_store,
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


class TestHubQueryOn:
    """Tests for _hub_query_on (batched query on existing SSH client)."""

    def test_rejects_non_select(self):
        fake_client = mock.MagicMock()
        with pytest.raises(ValueError, match="Only SELECT"):
            _hub_query_on(fake_client, "DELETE FROM orders_queue")
        fake_client.exec_command.assert_not_called()

    def test_rejects_insert(self):
        fake_client = mock.MagicMock()
        with pytest.raises(ValueError, match="Only SELECT"):
            _hub_query_on(fake_client, "INSERT INTO orders_queue VALUES (1)")

    def test_rejects_update(self):
        fake_client = mock.MagicMock()
        with pytest.raises(ValueError, match="Only SELECT"):
            _hub_query_on(fake_client, "UPDATE orders_queue SET status='x'")

    def test_select_returns_output(self):
        fake_client = mock.MagicMock()
        fake_stdout = mock.MagicMock()
        fake_stdout.read.return_value = b'[{"count":42}]'
        fake_client.exec_command.return_value = (None, fake_stdout, None)
        result = _hub_query_on(fake_client, "SELECT COUNT(*) as count FROM orders_queue")
        assert result == '[{"count":42}]'
        fake_client.exec_command.assert_called_once()

    def test_oversized_response_raises(self):
        fake_client = mock.MagicMock()
        fake_stdout = mock.MagicMock()
        fake_stdout.read.return_value = b"x" * (512 * 1024 + 1)
        fake_client.exec_command.return_value = (None, fake_stdout, None)
        with pytest.raises(ValueError, match="Oversized response"):
            _hub_query_on(fake_client, "SELECT * FROM orders_queue")


class TestExtractAndStoreNEG09:
    """NEG-09: ETL must use at most 1 SSH connection per collection cycle."""

    def test_single_ssh_connection(self, tmp_path, monkeypatch):
        """extract_and_store() opens exactly 1 SSH session for all 4 queries."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("core.analytics_etl.ANALYTICS_DB", db_path)

        empty_json = "[]"
        call_count = {"hub_query_on": 0}

        def fake_hub_query_on(client, sql, environment="production"):
            call_count["hub_query_on"] += 1
            return empty_json

        ssh_session_enters = {"count": 0}
        original_ssh_session = _ssh_session

        from contextlib import contextmanager

        @contextmanager
        def counting_ssh_session():
            ssh_session_enters["count"] += 1
            # Yield a mock client instead of real SSH
            yield mock.MagicMock()

        monkeypatch.setattr("core.analytics_etl._ssh_session", counting_ssh_session)
        monkeypatch.setattr("core.analytics_etl._hub_query_on", fake_hub_query_on)

        result = extract_and_store(days=7, environment="production")

        # NEG-09: exactly 1 SSH session
        assert ssh_session_enters["count"] == 1, (
            f"Expected 1 SSH session, got {ssh_session_enters['count']}"
        )
        # All 4 queries executed
        assert call_count["hub_query_on"] == 4, (
            f"Expected 4 queries, got {call_count['hub_query_on']}"
        )
        assert "error" not in result
        assert len(result["tables"]) == 4

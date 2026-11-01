"""Tests for the concrete agents: Diagnostician and ReportComposer.

Covers:
- Diagnostician: finding extraction, severity classification, confidence
  calculation, verdict formulation, action recommendations, end-to-end
  window processing.
- ReportComposer: hypothesis extraction, severity aggregation, Markdown
  rendering, summary generation, end-to-end report composition.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from core.agents.diagnostician import Diagnostician
from core.agents.report_composer import ReportComposer
from core.topic_router import TopicRouter


# ═══════════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════════

def _tool_end_event(tool_name: str, agent: str = "coder", mission: str = "M1",
                    payload_extra: Optional[dict] = None) -> dict:
    """Create a tool.end event for testing."""
    payload = {"tool_name": tool_name, "status": "end", "duration_ms": 500, "payload_bytes": 1024}
    if payload_extra:
        payload.update(payload_extra)
    return {
        "type": "tool.end",
        "topic": "tool.end",
        "agentId": agent,
        "missionId": mission,
        "tool_name": tool_name,
        "status": "end",
        "duration_ms": 500,
        "payload": payload,
    }


def _tool_timeout_event(tool_name: str, duration_ms: int = 15000) -> dict:
    """Create a tool.timeout event for testing."""
    return {
        "type": "tool.timeout",
        "topic": "tool.timeout",
        "agentId": "coder",
        "missionId": "M1",
        "tool_name": tool_name,
        "status": "timeout",
        "payload": {"tool_name": tool_name, "status": "timeout", "duration_ms": duration_ms},
    }


def _tool_denied_event(tool_name: str, reason: str = "approval_required") -> dict:
    """Create a tool.denied event for testing."""
    return {
        "type": "tool.denied",
        "topic": "tool.denied",
        "agentId": "system",
        "missionId": "M1",
        "tool_name": tool_name,
        "payload": {"tool_name": tool_name, "status": "denied", "reason": reason},
    }


def _tool_error_event(tool_name: str, error: str = "ConnectionError") -> dict:
    """Create a tool.end event with error for testing."""
    return {
        "type": "tool.end",
        "topic": "tool.end",
        "agentId": "coder",
        "missionId": "M1",
        "tool_name": tool_name,
        "payload": {"tool_name": tool_name, "status": "error", "error": error},
    }


def _evidence_event(agent: str = "researcher", data: Optional[dict] = None) -> dict:
    """Create a diagnostic.evidence event for testing."""
    return {
        "type": "diagnostic.evidence",
        "topic": "diagnostic.evidence",
        "agentId": agent,
        "missionId": "M1",
        "payload": data or {"rules": ["INV-01", "INV-02"], "context": "hub"},
    }


def _hypothesis_payload(
    diagnosis_id: str = "DX-0001",
    severity: str = "info",
    confidence: float = 0.7,
    verdict: str = "Sistema operando normalmente.",
    findings: Optional[list] = None,
    actions: Optional[list] = None,
) -> dict:
    """Create a hypothesis payload for ReportComposer tests."""
    return {
        "topic": "diagnostic.hypothesis",
        "agentId": "diagnostician",
        "payload": {
            "diagnosis_id": diagnosis_id,
            "timestamp": 1700000000000,
            "verdict": verdict,
            "severity": severity,
            "confidence": confidence,
            "findings": findings or [{"type": "health_signal", "tool": "observe_hub", "severity": "info",
                                       "detail": "Health check ok"}],
            "recommended_actions": actions or ["Nenhuma ação necessária"],
            "evidence_count": 5,
            "window_events": [
                {"topic": "tool.end", "agentId": "coder", "tool_name": "observe_hub", "sequence": 1},
                {"topic": "tool.end", "agentId": "coder", "tool_name": "pm2_status", "sequence": 2},
            ],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Diagnostician: Finding Extraction
# ═══════════════════════════════════════════════════════════════════════════

class TestDiagnosticianExtraction:
    """Tests for Diagnostician._extract_findings."""

    def test_timeout_creates_finding(self) -> None:
        events = [_tool_timeout_event("observe_hub")]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "timeout"
        assert findings[0]["tool"] == "observe_hub"
        assert findings[0]["severity"] == "warning"

    def test_denied_creates_finding(self) -> None:
        events = [_tool_denied_event("run_safe_command", "not_allowed")]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "access_denied"
        assert findings[0]["reason"] == "not_allowed"

    def test_tool_error_creates_finding(self) -> None:
        events = [_tool_error_event("observe_hub", "ConnectionError")]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "tool_error"
        assert findings[0]["error"] == "ConnectionError"

    def test_health_tool_creates_health_signal(self) -> None:
        events = [_tool_end_event("observe_hub")]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "health_signal"
        assert findings[0]["tool"] == "observe_hub"

    def test_knowledge_tool_creates_knowledge_signal(self) -> None:
        events = [_tool_end_event("search_knowledge_base")]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "knowledge_signal"

    def test_evidence_event_creates_evidence_finding(self) -> None:
        events = [_evidence_event("researcher", {"rules": ["INV-01"]})]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "evidence"
        assert findings[0]["source_agent"] == "researcher"

    def test_tool_start_skipped(self) -> None:
        events = [{"type": "tool.start", "topic": "tool.start", "payload": {}}]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 0

    def test_generic_tool_creates_tool_result(self) -> None:
        events = [_tool_end_event("some_custom_tool")]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 1
        assert findings[0]["type"] == "tool_result"

    def test_mixed_events(self) -> None:
        events = [
            _tool_end_event("observe_hub"),
            _tool_timeout_event("pm2_status"),
            _evidence_event(),
            _tool_end_event("search_knowledge_base"),
            _tool_error_event("etl_run"),
        ]
        findings = Diagnostician._extract_findings(events)
        assert len(findings) == 5
        types = [f["type"] for f in findings]
        assert "health_signal" in types
        assert "timeout" in types
        assert "evidence" in types
        assert "knowledge_signal" in types
        assert "tool_error" in types


# ═══════════════════════════════════════════════════════════════════════════
# Diagnostician: Severity Classification
# ═══════════════════════════════════════════════════════════════════════════

class TestDiagnosticianSeverity:
    """Tests for Diagnostician._classify_severity."""

    def test_all_healthy_is_info(self) -> None:
        findings = [{"type": "health_signal"}, {"type": "knowledge_signal"}]
        assert Diagnostician._classify_severity(findings) == "info"

    def test_one_timeout_is_warning(self) -> None:
        # 1 timeout in 5 findings = 20% error ratio → warning (not critical)
        findings = [
            {"type": "health_signal"}, {"type": "health_signal"},
            {"type": "health_signal"}, {"type": "knowledge_signal"},
            {"type": "timeout"},
        ]
        assert Diagnostician._classify_severity(findings) == "warning"

    def test_high_error_ratio_is_critical(self) -> None:
        findings = [{"type": "tool_error"}, {"type": "timeout"}, {"type": "tool_error"}]
        assert Diagnostician._classify_severity(findings) == "critical"

    def test_three_timeouts_is_critical(self) -> None:
        findings = [
            {"type": "timeout"}, {"type": "timeout"}, {"type": "timeout"},
            {"type": "health_signal"}, {"type": "health_signal"},
        ]
        assert Diagnostician._classify_severity(findings) == "critical"

    def test_empty_findings_is_info(self) -> None:
        assert Diagnostician._classify_severity([]) == "info"


# ═══════════════════════════════════════════════════════════════════════════
# Diagnostician: Confidence Calculation
# ═══════════════════════════════════════════════════════════════════════════

class TestDiagnosticianConfidence:
    """Tests for Diagnostician._calculate_confidence."""

    def test_empty_findings_zero_confidence(self) -> None:
        assert Diagnostician._calculate_confidence([], []) == 0.0

    def test_confidence_bounded_zero_to_one(self) -> None:
        findings = [{"type": "health_signal", "tool": f"t{i}"} for i in range(10)]
        events = [{}] * 10
        conf = Diagnostician._calculate_confidence(findings, events)
        assert 0.0 <= conf <= 1.0

    def test_more_events_higher_confidence(self) -> None:
        findings = [{"type": "health_signal", "tool": "observe_hub"}]
        conf_2 = Diagnostician._calculate_confidence(findings, [{}] * 2)
        conf_5 = Diagnostician._calculate_confidence(findings, [{}] * 5)
        assert conf_5 >= conf_2

    def test_errors_reduce_confidence(self) -> None:
        healthy = [{"type": "health_signal", "tool": "t1"}]
        errored = [{"type": "tool_error", "tool": "t1"}]
        events = [{}] * 5
        conf_h = Diagnostician._calculate_confidence(healthy, events)
        conf_e = Diagnostician._calculate_confidence(errored, events)
        assert conf_h > conf_e


# ═══════════════════════════════════════════════════════════════════════════
# Diagnostician: Verdict & Actions
# ═══════════════════════════════════════════════════════════════════════════

class TestDiagnosticianVerdict:
    """Tests for verdict and action generation."""

    def test_critical_verdict_mentions_tools(self) -> None:
        findings = [{"type": "tool_error", "tool": "observe_hub"}]
        verdict = Diagnostician._formulate_verdict(findings, "critical")
        assert "observe_hub" in verdict
        assert "críticas" in verdict.lower()

    def test_info_verdict_is_positive(self) -> None:
        findings = [{"type": "health_signal", "tool": "pm2_status"}]
        verdict = Diagnostician._formulate_verdict(findings, "info")
        assert "pm2_status" in verdict

    def test_critical_actions_include_escalation(self) -> None:
        findings = [{"type": "timeout", "tool": "x"}]
        actions = Diagnostician._recommend_actions(findings, "critical")
        assert any("escalar" in a.lower() for a in actions)

    def test_timeout_actions_include_investigation(self) -> None:
        findings = [{"type": "timeout", "tool": "pm2_status"}]
        actions = Diagnostician._recommend_actions(findings, "warning")
        assert any("pm2_status" in a for a in actions)

    def test_info_actions_include_no_action(self) -> None:
        findings = [{"type": "health_signal", "tool": "t"}]
        actions = Diagnostician._recommend_actions(findings, "info")
        assert any("nenhuma" in a.lower() for a in actions)


# ═══════════════════════════════════════════════════════════════════════════
# Diagnostician: End-to-End
# ═══════════════════════════════════════════════════════════════════════════

class TestDiagnosticianE2E:
    """End-to-end tests for Diagnostician through the event bus."""

    @pytest.mark.asyncio
    async def test_processes_window_and_publishes_hypothesis(self) -> None:
        router = TopicRouter()
        result_q = router.subscribe("diagnostic.hypothesis")

        diag = Diagnostician(router=router, window_size=3, timeout_seconds=5.0)
        diag.start()

        # Publish 3 diagnostic events
        router.publish("diagnostic.evidence", {
            "agentId": "researcher", "missionId": "M1",
            "payload": {"rules": ["INV-01"]},
        })
        router.publish("tool.end", {
            "agentId": "coder", "missionId": "M1",
            "tool_name": "observe_hub",
            "payload": {"tool_name": "observe_hub", "status": "end", "duration_ms": 300, "payload_bytes": 512},
        })
        router.publish("tool.end", {
            "agentId": "coder", "missionId": "M1",
            "tool_name": "pm2_status",
            "payload": {"tool_name": "pm2_status", "status": "end", "duration_ms": 200, "payload_bytes": 256},
        })

        await asyncio.sleep(0.5)
        await diag.stop()

        assert not result_q.empty()
        hypothesis = result_q.get_nowait()
        payload = hypothesis.get("payload", {})
        assert "diagnosis_id" in payload
        assert payload["diagnosis_id"] == "DX-0001"
        assert payload["severity"] == "info"
        assert payload["confidence"] > 0
        assert len(payload["findings"]) > 0
        assert diag.diagnosis_count == 1

    @pytest.mark.asyncio
    async def test_critical_diagnosis_on_errors(self) -> None:
        router = TopicRouter()
        result_q = router.subscribe("diagnostic.hypothesis")

        diag = Diagnostician(router=router, window_size=3, timeout_seconds=5.0)
        diag.start()

        # 3 errors should produce critical severity
        for tool in ["observe_hub", "pm2_status", "etl_run"]:
            router.publish("tool.timeout", {
                "agentId": "coder", "missionId": "M1",
                "tool_name": tool,
                "payload": {"tool_name": tool, "status": "timeout", "duration_ms": 15000},
            })

        await asyncio.sleep(0.5)
        await diag.stop()

        assert not result_q.empty()
        hypothesis = result_q.get_nowait()
        assert hypothesis["payload"]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_no_output_when_only_tool_starts(self) -> None:
        router = TopicRouter()
        result_q = router.subscribe("diagnostic.hypothesis")

        diag = Diagnostician(router=router, window_size=3, timeout_seconds=0.2)
        diag.start()

        # tool.start events produce no findings
        for i in range(3):
            router.publish("tool.start", {
                "agentId": "coder", "missionId": "M1",
                "payload": {"tool_name": f"t{i}", "status": "start"},
            })

        await asyncio.sleep(0.5)
        await diag.stop()

        # Window closed but no actionable findings → no hypothesis
        assert result_q.empty()

    @pytest.mark.asyncio
    async def test_diagnosis_count_increments(self) -> None:
        router = TopicRouter()
        diag = Diagnostician(router=router, window_size=1, timeout_seconds=5.0)
        diag.start()

        for i in range(3):
            router.publish("tool.end", {
                "agentId": "coder", "missionId": "M1",
                "tool_name": "observe_hub",
                "payload": {"tool_name": "observe_hub", "status": "end", "duration_ms": 100, "payload_bytes": 64},
            })
            await asyncio.sleep(0.2)  # let each window process before next

        await asyncio.sleep(0.3)
        await diag.stop()

        assert diag.diagnosis_count == 3


# ═══════════════════════════════════════════════════════════════════════════
# ReportComposer: Extraction & Severity
# ═══════════════════════════════════════════════════════════════════════════

class TestReportComposerExtraction:
    """Tests for ReportComposer helper methods."""

    def test_extract_hypotheses_from_events(self) -> None:
        events = [_hypothesis_payload()]
        hypotheses = ReportComposer._extract_hypotheses(events)
        assert len(hypotheses) == 1
        assert hypotheses[0]["diagnosis_id"] == "DX-0001"

    def test_extract_skips_non_hypothesis(self) -> None:
        events = [{"topic": "tool.end", "payload": {"status": "end"}}]
        hypotheses = ReportComposer._extract_hypotheses(events)
        assert len(hypotheses) == 0

    def test_worst_severity_picks_critical(self) -> None:
        hypotheses = [
            {"severity": "info"},
            {"severity": "critical"},
            {"severity": "warning"},
        ]
        assert ReportComposer._worst_severity(hypotheses) == "critical"

    def test_worst_severity_single_info(self) -> None:
        assert ReportComposer._worst_severity([{"severity": "info"}]) == "info"


# ═══════════════════════════════════════════════════════════════════════════
# ReportComposer: Markdown Rendering
# ═══════════════════════════════════════════════════════════════════════════

class TestReportComposerRendering:
    """Tests for Markdown report rendering."""

    def test_markdown_contains_title(self) -> None:
        router = TopicRouter()
        composer = ReportComposer(router=router, report_title="Test Report")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        hypotheses = [_hypothesis_payload()["payload"]]
        md = composer._render_markdown("RPT-0001", now, "info", hypotheses)
        assert "Test Report" in md
        assert "RPT-0001" in md

    def test_markdown_contains_sections(self) -> None:
        router = TopicRouter()
        composer = ReportComposer(router=router)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        hypotheses = [_hypothesis_payload()["payload"]]
        md = composer._render_markdown("RPT-0001", now, "info", hypotheses)
        assert "## Resumo Executivo" in md
        assert "## Achados Detalhados" in md
        assert "## Ações Recomendadas" in md
        assert "## Trilha de Evidências" in md

    def test_markdown_critical_has_red_emoji(self) -> None:
        router = TopicRouter()
        composer = ReportComposer(router=router)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        hypotheses = [{
            "diagnosis_id": "DX-0001",
            "severity": "critical",
            "confidence": 0.9,
            "verdict": "Falha crítica",
            "findings": [{"type": "timeout", "tool": "x", "severity": "warning", "detail": "timeout"}],
            "recommended_actions": ["Escalar"],
            "window_events": [],
        }]
        md = composer._render_markdown("RPT-0001", now, "critical", hypotheses)
        assert "🔴" in md
        assert "CRÍTICO" in md

    def test_summary_format(self) -> None:
        hypotheses = [{"diagnosis_id": "DX-0001", "severity": "info"}]
        summary = ReportComposer._render_summary("info", hypotheses)
        assert "🟢" in summary
        assert "DX-0001" in summary
        assert "SAUDÁVEL" in summary


# ═══════════════════════════════════════════════════════════════════════════
# ReportComposer: End-to-End
# ═══════════════════════════════════════════════════════════════════════════

class TestReportComposerE2E:
    """End-to-end tests for ReportComposer through the event bus."""

    @pytest.mark.asyncio
    async def test_composes_report_from_hypothesis(self) -> None:
        router = TopicRouter()
        report_q = router.subscribe("report.ready")

        composer = ReportComposer(router=router, window_size=1, timeout_seconds=5.0)
        composer.start()

        router.publish("diagnostic.hypothesis", {
            "agentId": "diagnostician",
            "missionId": "M1",
            "payload": {
                "diagnosis_id": "DX-0001",
                "timestamp": 1700000000000,
                "verdict": "Sistema saudável",
                "severity": "info",
                "confidence": 0.85,
                "findings": [{"type": "health_signal", "tool": "observe_hub",
                              "severity": "info", "detail": "OK"}],
                "recommended_actions": ["Nenhuma ação necessária"],
                "evidence_count": 5,
                "window_events": [
                    {"topic": "tool.end", "agentId": "coder", "tool_name": "observe_hub", "sequence": 1},
                ],
            },
        })

        await asyncio.sleep(0.5)
        await composer.stop()

        assert not report_q.empty()
        report = report_q.get_nowait()
        payload = report.get("payload", {})
        assert payload["report_id"] == "RPT-0001"
        assert "markdown" in payload
        assert "## Resumo Executivo" in payload["markdown"]
        assert payload["severity"] == "info"
        assert composer.report_count == 1

    @pytest.mark.asyncio
    async def test_full_pipeline_diagnostician_to_composer(self) -> None:
        """Integration: Diagnostician → hypothesis → ReportComposer → report."""
        router = TopicRouter()
        report_q = router.subscribe("report.ready")

        diag = Diagnostician(router=router, window_size=2, timeout_seconds=5.0)
        composer = ReportComposer(router=router, window_size=1, timeout_seconds=5.0)

        diag.start()
        composer.start()

        # Publish 2 tool results → triggers diagnostician → hypothesis → report
        router.publish("tool.end", {
            "agentId": "coder", "missionId": "M1",
            "tool_name": "observe_hub",
            "payload": {"tool_name": "observe_hub", "status": "end",
                        "duration_ms": 200, "payload_bytes": 512},
        })
        router.publish("tool.end", {
            "agentId": "coder", "missionId": "M1",
            "tool_name": "pm2_status",
            "payload": {"tool_name": "pm2_status", "status": "end",
                        "duration_ms": 150, "payload_bytes": 256},
        })

        # Wait for the pipeline: events → diag accumulates → hypothesis → composer → report
        await asyncio.sleep(1.0)

        await diag.stop()
        await composer.stop()

        assert diag.diagnosis_count >= 1
        assert not report_q.empty()

        report = report_q.get_nowait()
        payload = report.get("payload", {})
        assert "RPT-" in payload.get("report_id", "")
        assert "markdown" in payload
        assert payload["severity"] == "info"

    @pytest.mark.asyncio
    async def test_report_count_increments(self) -> None:
        router = TopicRouter()
        composer = ReportComposer(router=router, window_size=1, timeout_seconds=5.0)
        composer.start()

        for i in range(2):
            router.publish("diagnostic.hypothesis", {
                "agentId": "diagnostician",
                "missionId": "M1",
                "payload": {
                    "diagnosis_id": f"DX-{i+1:04d}",
                    "verdict": "OK",
                    "severity": "info",
                    "confidence": 0.8,
                    "findings": [],
                    "recommended_actions": [],
                    "evidence_count": 5,
                    "window_events": [],
                },
            })

        await asyncio.sleep(0.5)
        await composer.stop()

        assert composer.report_count == 2

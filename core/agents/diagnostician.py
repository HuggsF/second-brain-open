"""Diagnostician agent — Rex.

Listens to ``diagnostic.*`` topics, accumulates evidence from tool results,
knowledge-base lookups and health checks, then synthesizes a structured
diagnosis with verdict, confidence, findings and recommended actions.

Publishes results to ``diagnostic.hypothesis``.

Usage::

    router = TopicRouter()
    diag = Diagnostician(router=router)
    diag.start()
    # ... events flow through the router ...
    await diag.stop()
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.agent_listener import AgentListener
from core.topic_router import TopicRouter

logger = logging.getLogger(__name__)

# ── Severity classification thresholds ─────────────────────────────────────

_SEVERITY_THRESHOLDS = {
    "critical": {"error_ratio": 0.5, "timeout_count": 3},
    "warning":  {"error_ratio": 0.2, "timeout_count": 1},
}

# Tool names that indicate health-check evidence
_HEALTH_TOOLS = frozenset({
    "observe_hub", "pm2_status", "pm2_logs",
    "srv_api_health_check", "srv_api_resource_usage",
    "analyze_error_patterns", "analyze_throughput",
    "analyze_logistics_health", "etl_run",
    "predict_emission_trends",
})

# Tool names that indicate knowledge/rule evidence
_KNOWLEDGE_TOOLS = frozenset({
    "search_knowledge_base", "get_brain_status",
    "get_system_architecture", "list_rules",
    "get_rule_evidence",
})


class Diagnostician(AgentListener):
    """Concrete agent that synthesizes diagnostic hypotheses from accumulated evidence.

    Subscribes to ``diagnostic.*`` and ``tool.*`` topics.  When the window
    closes (default 5 events or 30 s timeout), classifies findings by
    severity and publishes a structured hypothesis to ``diagnostic.hypothesis``.

    Parameters
    ----------
    router:
        The :class:`TopicRouter` instance to subscribe to and publish on.
    window_size:
        Number of events to accumulate before triggering diagnosis.
    timeout_seconds:
        Maximum seconds to wait for a full window.
    """

    LISTEN_TOPICS = ["diagnostic.evidence", "diagnostic.tool_result", "tool.*"]
    OUTPUT_TOPIC = "diagnostic.hypothesis"

    def __init__(
        self,
        router: TopicRouter,
        window_size: int = 5,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            agent_id="diagnostician",
            listen_topics=self.LISTEN_TOPICS,
            router=router,
            window_size=window_size,
            timeout_seconds=timeout_seconds,
        )
        self._diagnosis_count: int = 0

    # ── properties ─────────────────────────────────────────────────────────

    @property
    def diagnosis_count(self) -> int:
        """Total number of diagnoses produced."""
        return self._diagnosis_count

    # ── core logic ─────────────────────────────────────────────────────────

    async def on_window_closed(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Synthesize a diagnosis from accumulated evidence events.

        Returns a structured hypothesis event to be published to
        ``diagnostic.hypothesis``, or ``None`` if no actionable findings.
        """
        findings = self._extract_findings(events)

        if not findings:
            logger.info("Diagnostician: window closed with %d events but no actionable findings", len(events))
            return None

        severity = self._classify_severity(findings)
        confidence = self._calculate_confidence(findings, events)
        verdict = self._formulate_verdict(findings, severity)
        actions = self._recommend_actions(findings, severity)

        self._diagnosis_count += 1

        hypothesis = {
            "topic": self.OUTPUT_TOPIC,
            "agentId": self._agent_id,
            "payload": {
                "diagnosis_id": f"DX-{self._diagnosis_count:04d}",
                "timestamp": int(time.time() * 1000),
                "verdict": verdict,
                "severity": severity,
                "confidence": confidence,
                "findings": findings,
                "recommended_actions": actions,
                "evidence_count": len(events),
                "window_events": [
                    {
                        "topic": e.get("topic", "unknown"),
                        "agentId": e.get("agentId", "unknown"),
                        "tool_name": e.get("tool_name", e.get("payload", {}).get("tool_name", "unknown")),
                        "sequence": e.get("sequence"),
                    }
                    for e in events
                ],
            },
        }

        logger.info(
            "Diagnostician: diagnosis DX-%04d — severity=%s confidence=%.0f%% findings=%d",
            self._diagnosis_count, severity, confidence * 100, len(findings),
        )

        return hypothesis

    # ── extraction ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_findings(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract structured findings from raw events.

        Classifies each event as a health signal, knowledge signal, error,
        timeout, or denial, and extracts relevant data.
        """
        findings: List[Dict[str, Any]] = []

        for event in events:
            event_type = event.get("type", event.get("topic", ""))
            payload = event.get("payload", {})
            tool_name = event.get("tool_name", payload.get("tool_name", ""))

            # ── Tool errors ────────────────────────────────────────────
            if event_type in ("tool.timeout", "diagnostic.timeout"):
                findings.append({
                    "type": "timeout",
                    "tool": tool_name,
                    "duration_ms": payload.get("duration_ms"),
                    "severity": "warning",
                    "detail": f"Tool '{tool_name}' timed out after {payload.get('duration_ms', '?')}ms",
                })
                continue

            if event_type == "tool.denied":
                findings.append({
                    "type": "access_denied",
                    "tool": tool_name,
                    "reason": payload.get("reason", "unknown"),
                    "severity": "info",
                    "detail": f"Tool '{tool_name}' denied: {payload.get('reason', 'unknown')}",
                })
                continue

            # ── Tool completions ───────────────────────────────────────
            if event_type in ("tool.end", "diagnostic.tool_result"):
                status = payload.get("status", "")
                has_error = "error" in payload or status == "error"

                if has_error:
                    findings.append({
                        "type": "tool_error",
                        "tool": tool_name,
                        "error": payload.get("error", "unknown"),
                        "severity": "warning",
                        "detail": f"Tool '{tool_name}' returned error: {payload.get('error', 'unknown')}",
                    })
                elif tool_name in _HEALTH_TOOLS:
                    findings.append({
                        "type": "health_signal",
                        "tool": tool_name,
                        "severity": "info",
                        "data": {k: v for k, v in payload.items()
                                 if k not in ("tool_name", "status", "payload_bytes")},
                        "detail": f"Health check '{tool_name}' completed successfully",
                    })
                elif tool_name in _KNOWLEDGE_TOOLS:
                    findings.append({
                        "type": "knowledge_signal",
                        "tool": tool_name,
                        "severity": "info",
                        "data": {k: v for k, v in payload.items()
                                 if k not in ("tool_name", "status", "payload_bytes")},
                        "detail": f"Knowledge lookup '{tool_name}' returned data",
                    })
                else:
                    findings.append({
                        "type": "tool_result",
                        "tool": tool_name,
                        "severity": "info",
                        "detail": f"Tool '{tool_name}' completed",
                    })
                continue

            # ── Evidence events (from other agents) ────────────────────
            if "diagnostic.evidence" in event_type:
                findings.append({
                    "type": "evidence",
                    "source_agent": event.get("agentId", "unknown"),
                    "severity": "info",
                    "data": payload,
                    "detail": f"Evidence from agent '{event.get('agentId', 'unknown')}'",
                })
                continue

            # ── Generic tool.start (no finding, just context) ──────────
            if event_type == "tool.start":
                continue

            # ── Fallback: unknown event type ───────────────────────────
            findings.append({
                "type": "observation",
                "event_type": event_type,
                "severity": "info",
                "detail": f"Observed event: {event_type}",
            })

        return findings

    # ── classification ─────────────────────────────────────────────────────

    @staticmethod
    def _classify_severity(findings: List[Dict[str, Any]]) -> str:
        """Determine overall severity: ``critical``, ``warning``, or ``info``."""
        error_count = sum(1 for f in findings if f["type"] in ("tool_error", "timeout"))
        total = len(findings) or 1
        timeout_count = sum(1 for f in findings if f["type"] == "timeout")
        error_ratio = error_count / total

        if (error_ratio >= _SEVERITY_THRESHOLDS["critical"]["error_ratio"]
                or timeout_count >= _SEVERITY_THRESHOLDS["critical"]["timeout_count"]):
            return "critical"

        if (error_ratio >= _SEVERITY_THRESHOLDS["warning"]["error_ratio"]
                or timeout_count >= _SEVERITY_THRESHOLDS["warning"]["timeout_count"]):
            return "warning"

        return "info"

    @staticmethod
    def _calculate_confidence(findings: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> float:
        """Calculate confidence score (0.0–1.0) based on evidence quality.

        More diverse tool sources and more health signals increase confidence.
        Timeouts and errors decrease it.
        """
        if not findings:
            return 0.0

        unique_tools = len({f.get("tool", f.get("source_agent", "")) for f in findings})
        health_signals = sum(1 for f in findings if f["type"] == "health_signal")
        knowledge_signals = sum(1 for f in findings if f["type"] in ("knowledge_signal", "evidence"))
        errors = sum(1 for f in findings if f["type"] in ("tool_error", "timeout"))

        # Base confidence from event count (more events = more data)
        base = min(len(events) / 5.0, 1.0) * 0.3

        # Diversity bonus (more tools = broader picture)
        diversity = min(unique_tools / 3.0, 1.0) * 0.25

        # Signal quality (health + knowledge signals boost confidence)
        quality = min((health_signals + knowledge_signals) / 3.0, 1.0) * 0.30

        # Error penalty
        penalty = min(errors / 3.0, 1.0) * 0.15

        confidence = base + diversity + quality - penalty
        return max(0.0, min(1.0, round(confidence, 2)))

    @staticmethod
    def _formulate_verdict(findings: List[Dict[str, Any]], severity: str) -> str:
        """Generate a human-readable verdict string."""
        error_types = [f for f in findings if f["type"] in ("tool_error", "timeout", "access_denied")]
        health_types = [f for f in findings if f["type"] == "health_signal"]

        if severity == "critical":
            error_tools = ", ".join(f.get("tool", "?") for f in error_types[:3])
            return f"Sistema com falhas críticas detectadas em: {error_tools}. Ação imediata necessária."

        if severity == "warning":
            issues = [f["detail"] for f in error_types[:2]]
            return f"Problemas detectados: {'; '.join(issues)}. Monitorar de perto."

        if health_types:
            healthy_tools = ", ".join(f.get("tool", "?") for f in health_types[:3])
            return f"Sistema operando dentro dos parâmetros. Verificações positivas: {healthy_tools}."

        return "Diagnóstico inconclusivo — dados insuficientes para veredito."

    @staticmethod
    def _recommend_actions(findings: List[Dict[str, Any]], severity: str) -> List[str]:
        """Generate recommended actions based on findings and severity."""
        actions: List[str] = []

        timeouts = [f for f in findings if f["type"] == "timeout"]
        errors = [f for f in findings if f["type"] == "tool_error"]
        denied = [f for f in findings if f["type"] == "access_denied"]

        if severity == "critical":
            actions.append("🚨 Escalar para equipe de operações imediatamente")
            actions.append("Verificar status dos serviços via PM2 e health checks")

        for t in timeouts:
            actions.append(f"Investigar latência do serviço '{t.get('tool', '?')}' — timeout detectado")

        for e in errors:
            actions.append(f"Revisar logs de erro em '{e.get('tool', '?')}': {e.get('error', 'desconhecido')}")

        for d in denied:
            if d.get("reason") == "approval_required":
                actions.append(f"Solicitar aprovação humana para executar '{d.get('tool', '?')}'")
            else:
                actions.append(f"Verificar permissões para '{d.get('tool', '?')}': {d.get('reason', '?')}")

        if severity == "info" and not actions:
            actions.append("Nenhuma ação necessária — sistema saudável")
            actions.append("Próxima verificação programada conforme SLA de monitoramento")

        return actions

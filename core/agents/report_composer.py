"""Report Composer agent — Lia (Writer role, report function).

Listens to ``diagnostic.hypothesis`` topics, accumulates diagnoses,
and composes a structured Markdown report ready for human consumption
or Telegram delivery.

Publishes results to ``report.ready``.

Usage::

    router = TopicRouter()
    composer = ReportComposer(router=router)
    composer.start()
    # ... diagnostic hypotheses flow in ...
    await composer.stop()
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.agent_listener import AgentListener
from core.topic_router import TopicRouter

logger = logging.getLogger(__name__)

# Severity → emoji mapping for reports
_SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning":  "🟡",
    "info":     "🟢",
}

_SEVERITY_LABEL = {
    "critical": "CRÍTICO",
    "warning":  "ATENÇÃO",
    "info":     "SAUDÁVEL",
}


class ReportComposer(AgentListener):
    """Concrete agent that composes diagnostic reports from hypotheses.

    Subscribes to ``diagnostic.hypothesis``.  When the window closes
    (default 1 event — each hypothesis gets its own report), generates
    a Markdown report and publishes to ``report.ready``.

    For batch reports, increase ``window_size`` to accumulate multiple
    hypotheses before composing.

    Parameters
    ----------
    router:
        The :class:`TopicRouter` instance to subscribe to and publish on.
    window_size:
        Number of hypotheses to accumulate before composing.  Default 1
        means each hypothesis gets an immediate report.
    timeout_seconds:
        Maximum seconds to wait for a full window.
    report_title:
        Title prefix for generated reports.
    """

    LISTEN_TOPICS = ["diagnostic.hypothesis"]
    OUTPUT_TOPIC = "report.ready"

    def __init__(
        self,
        router: TopicRouter,
        window_size: int = 1,
        timeout_seconds: float = 60.0,
        report_title: str = "Relatório de Diagnóstico — Hub Logístico",
    ) -> None:
        super().__init__(
            agent_id="report_composer",
            listen_topics=self.LISTEN_TOPICS,
            router=router,
            window_size=window_size,
            timeout_seconds=timeout_seconds,
        )
        self._report_title = report_title
        self._report_count: int = 0

    # ── properties ─────────────────────────────────────────────────────────

    @property
    def report_count(self) -> int:
        """Total number of reports produced."""
        return self._report_count

    # ── core logic ─────────────────────────────────────────────────────────

    async def on_window_closed(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Compose a Markdown report from accumulated hypothesis events.

        Returns a report event to be published to ``report.ready``.
        """
        hypotheses = self._extract_hypotheses(events)

        if not hypotheses:
            logger.info("ReportComposer: no hypotheses found in %d events", len(events))
            return None

        self._report_count += 1
        report_id = f"RPT-{self._report_count:04d}"
        now = datetime.now(timezone.utc)

        # Determine overall severity (worst-case across all hypotheses)
        overall_severity = self._worst_severity(hypotheses)
        markdown = self._render_markdown(report_id, now, overall_severity, hypotheses)
        summary = self._render_summary(overall_severity, hypotheses)

        report_event = {
            "topic": self.OUTPUT_TOPIC,
            "agentId": self._agent_id,
            "payload": {
                "report_id": report_id,
                "timestamp": int(time.time() * 1000),
                "title": self._report_title,
                "severity": overall_severity,
                "summary": summary,
                "markdown": markdown,
                "hypothesis_count": len(hypotheses),
                "diagnosis_ids": [h.get("diagnosis_id", "?") for h in hypotheses],
            },
        }

        logger.info(
            "ReportComposer: report %s — severity=%s hypotheses=%d",
            report_id, overall_severity, len(hypotheses),
        )

        return report_event

    # ── extraction ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_hypotheses(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract hypothesis payloads from events."""
        hypotheses: List[Dict[str, Any]] = []
        for event in events:
            payload = event.get("payload", {})
            # Hypothesis events have diagnosis_id in their payload
            if "diagnosis_id" in payload or "verdict" in payload:
                hypotheses.append(payload)
            elif "payload" in payload and "diagnosis_id" in payload.get("payload", {}):
                # Nested payload (from TopicRouter enrichment)
                hypotheses.append(payload["payload"])
        return hypotheses

    # ── severity ───────────────────────────────────────────────────────────

    @staticmethod
    def _worst_severity(hypotheses: List[Dict[str, Any]]) -> str:
        """Return the worst (most severe) severity across all hypotheses."""
        severity_rank = {"critical": 3, "warning": 2, "info": 1}
        worst = "info"
        worst_rank = 1
        for h in hypotheses:
            sev = h.get("severity", "info")
            rank = severity_rank.get(sev, 0)
            if rank > worst_rank:
                worst = sev
                worst_rank = rank
        return worst

    # ── rendering ──────────────────────────────────────────────────────────

    def _render_markdown(
        self,
        report_id: str,
        now: datetime,
        overall_severity: str,
        hypotheses: List[Dict[str, Any]],
    ) -> str:
        """Render a full Markdown diagnostic report."""
        emoji = _SEVERITY_EMOJI.get(overall_severity, "⚪")
        label = _SEVERITY_LABEL.get(overall_severity, "DESCONHECIDO")
        ts = now.strftime("%d/%m/%Y %H:%M UTC")

        lines: List[str] = [
            f"# {emoji} {self._report_title}",
            "",
            f"**ID:** `{report_id}`  ",
            f"**Data:** {ts}  ",
            f"**Status Geral:** {emoji} {label}  ",
            f"**Diagnósticos:** {len(hypotheses)}",
            "",
            "---",
            "",
        ]

        # ── Summary section ────────────────────────────────────────────
        lines.append("## Resumo Executivo")
        lines.append("")

        for i, hyp in enumerate(hypotheses, 1):
            dx_id = hyp.get("diagnosis_id", f"DX-{i}")
            sev = hyp.get("severity", "info")
            sev_emoji = _SEVERITY_EMOJI.get(sev, "⚪")
            verdict = hyp.get("verdict", "Sem veredito")
            confidence = hyp.get("confidence", 0)

            lines.append(f"### {sev_emoji} {dx_id} (confiança: {confidence:.0%})")
            lines.append("")
            lines.append(f"> {verdict}")
            lines.append("")

        # ── Findings section ───────────────────────────────────────────
        lines.append("---")
        lines.append("")
        lines.append("## Achados Detalhados")
        lines.append("")

        for hyp in hypotheses:
            dx_id = hyp.get("diagnosis_id", "?")
            findings = hyp.get("findings", [])

            if not findings:
                lines.append(f"### {dx_id}: Nenhum achado registrado")
                lines.append("")
                continue

            lines.append(f"### {dx_id}")
            lines.append("")
            lines.append("| Tipo | Ferramenta | Severidade | Detalhe |")
            lines.append("|------|-----------|------------|---------|")

            for f in findings:
                f_type = f.get("type", "?")
                f_tool = f.get("tool", f.get("source_agent", "—"))
                f_sev = f.get("severity", "info")
                f_detail = f.get("detail", "—")
                # Truncate long details for table readability
                if len(f_detail) > 80:
                    f_detail = f_detail[:77] + "..."
                lines.append(f"| {f_type} | `{f_tool}` | {f_sev} | {f_detail} |")

            lines.append("")

        # ── Actions section ────────────────────────────────────────────
        lines.append("---")
        lines.append("")
        lines.append("## Ações Recomendadas")
        lines.append("")

        all_actions: List[str] = []
        for hyp in hypotheses:
            all_actions.extend(hyp.get("recommended_actions", []))

        if all_actions:
            for j, action in enumerate(all_actions, 1):
                lines.append(f"{j}. {action}")
        else:
            lines.append("_Nenhuma ação recomendada._")

        lines.append("")

        # ── Evidence trail section ─────────────────────────────────────
        lines.append("---")
        lines.append("")
        lines.append("## Trilha de Evidências")
        lines.append("")
        lines.append("| # | Tópico | Agente | Ferramenta |")
        lines.append("|---|--------|--------|-----------|")

        seq = 1
        for hyp in hypotheses:
            for ev in hyp.get("window_events", []):
                topic = ev.get("topic", "?")
                agent = ev.get("agentId", "?")
                tool = ev.get("tool_name", "?")
                lines.append(f"| {seq} | `{topic}` | {agent} | `{tool}` |")
                seq += 1

        lines.append("")
        lines.append("---")
        lines.append(f"_Gerado automaticamente por ReportComposer (Lia) em {ts}_")

        return "\n".join(lines)

    @staticmethod
    def _render_summary(overall_severity: str, hypotheses: List[Dict[str, Any]]) -> str:
        """Render a one-line summary suitable for notifications."""
        emoji = _SEVERITY_EMOJI.get(overall_severity, "⚪")
        label = _SEVERITY_LABEL.get(overall_severity, "?")
        count = len(hypotheses)
        dx_ids = ", ".join(h.get("diagnosis_id", "?") for h in hypotheses[:3])

        if count > 3:
            dx_ids += f" (+{count - 3})"

        return f"{emoji} {label} — {count} diagnóstico(s): {dx_ids}"

"""Testes para core/governance — HITL Protocol e Handoff Protocol.

Sprint 6 (Gaps G2 + G10): Cobertura de protocolo HITL com frames
governance.hitl_required/governance.hitl_decision e handoff tipado
com scoped_context_artifact.
"""

import pytest

from core.governance.hitl_protocol import (
    HITLDecision,
    HITLReason,
    HITLRequest,
    HITLResponse,
    HITLPendingStore,
)
from core.governance.handoff_protocol import (
    HandoffType,
    HandoffPriority,
    ScopedContextArtifact,
    HandoffEnvelope,
    create_delegation,
    create_escalation,
)


# ─────────────────────────────────────────────
# HITLRequest
# ─────────────────────────────────────────────

class TestHITLRequest:
    def test_create_with_defaults(self):
        req = HITLRequest(
            request_id="",
            trace_id="abc123",
            mission_id=1,
            persona_id="maia",
            tool_name="run_safe_command",
            reason=HITLReason.HIGH_RISK_TOOL,
        )
        assert req.request_id.startswith("hitl-")
        assert req.timestamp != ""
        assert req.timeout_seconds == 300.0

    def test_create_with_explicit_values(self):
        req = HITLRequest(
            request_id="hitl-custom",
            trace_id="trace-001",
            mission_id=5,
            persona_id="devops",
            tool_name="run_safe_command",
            reason=HITLReason.FINANCIAL_THRESHOLD,
            context_summary="Operação financeira",
            timeout_seconds=60.0,
            financial_amount=10000.0,
        )
        assert req.request_id == "hitl-custom"
        assert req.financial_amount == 10000.0

    def test_to_frame(self):
        req = HITLRequest(
            request_id="hitl-001",
            trace_id="t1",
            mission_id=1,
            persona_id="maia",
            tool_name="tool_x",
            reason=HITLReason.GATE_YELLOW,
        )
        frame = req.to_frame()
        assert frame["type"] == "governance.hitl_required"
        assert frame["request_id"] == "hitl-001"
        assert frame["reason"] == "gate_yellow"
        assert frame["mission_id"] == 1


# ─────────────────────────────────────────────
# HITLResponse
# ─────────────────────────────────────────────

class TestHITLResponse:
    def test_create_approve(self):
        resp = HITLResponse(
            request_id="hitl-001",
            decision=HITLDecision.APPROVE,
            operator_id="hugo@kiosk.com",
            justification="Operação autorizada",
        )
        assert resp.decision == HITLDecision.APPROVE
        assert resp.timestamp != ""

    def test_operator_hash(self):
        resp = HITLResponse(
            request_id="hitl-001",
            decision=HITLDecision.APPROVE,
            operator_id="hugo@kiosk.com",
        )
        h = resp.operator_hash
        assert len(h) == 16
        # Determinístico
        assert resp.operator_hash == h

    def test_to_frame(self):
        resp = HITLResponse(
            request_id="hitl-001",
            decision=HITLDecision.REJECT,
            operator_id="admin",
            justification="Risco alto demais",
        )
        frame = resp.to_frame()
        assert frame["type"] == "governance.hitl_decision"
        assert frame["decision"] == "REJECT"
        assert frame["justification"] == "Risco alto demais"
        assert "operator_hash" in frame

    def test_from_frame(self):
        frame = {
            "request_id": "hitl-002",
            "decision": "APPROVE",
            "operator_id": "hugo",
            "justification": "OK",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        resp = HITLResponse.from_frame(frame)
        assert resp.request_id == "hitl-002"
        assert resp.decision == HITLDecision.APPROVE
        assert resp.justification == "OK"

    def test_from_frame_defaults(self):
        resp = HITLResponse.from_frame({})
        assert resp.decision == HITLDecision.REJECT  # fallback seguro


# ─────────────────────────────────────────────
# HITLPendingStore
# ─────────────────────────────────────────────

class TestHITLPendingStore:
    def _make_request(self, rid="hitl-001"):
        return HITLRequest(
            request_id=rid,
            trace_id="t1",
            mission_id=1,
            persona_id="maia",
            tool_name="tool",
            reason=HITLReason.HIGH_RISK_TOOL,
        )

    def test_register_and_pending(self):
        store = HITLPendingStore()
        req = self._make_request()
        store.register(req)
        assert store.pending_count == 1
        assert store.is_pending("hitl-001")

    def test_resolve_approve(self):
        store = HITLPendingStore()
        req = self._make_request()
        store.register(req)

        resp = HITLResponse(
            request_id="hitl-001",
            decision=HITLDecision.APPROVE,
            operator_id="hugo",
        )
        original = store.resolve(resp)
        assert original is not None
        assert original.request_id == "hitl-001"
        assert store.pending_count == 0
        assert store.decision_count == 1

    def test_resolve_unknown_request(self):
        store = HITLPendingStore()
        resp = HITLResponse(
            request_id="unknown",
            decision=HITLDecision.APPROVE,
        )
        assert store.resolve(resp) is None

    def test_timeout_expired(self):
        store = HITLPendingStore()
        req = self._make_request()
        store.register(req)

        expired = store.timeout_expired("hitl-001")
        assert expired is not None
        assert store.pending_count == 0
        decision = store.get_decision("hitl-001")
        assert decision.decision == HITLDecision.TIMEOUT

    def test_get_pending_list(self):
        store = HITLPendingStore()
        store.register(self._make_request("hitl-a"))
        store.register(self._make_request("hitl-b"))
        pending = store.get_pending()
        assert len(pending) == 2

    def test_clear(self):
        store = HITLPendingStore()
        store.register(self._make_request())
        store.clear()
        assert store.pending_count == 0
        assert store.decision_count == 0

    def test_double_resolve_returns_none(self):
        store = HITLPendingStore()
        store.register(self._make_request())
        resp = HITLResponse(request_id="hitl-001", decision=HITLDecision.APPROVE)
        store.resolve(resp)
        assert store.resolve(resp) is None  # já resolvido


# ─────────────────────────────────────────────
# HITLDecision enum
# ─────────────────────────────────────────────

class TestHITLDecision:
    def test_values(self):
        assert HITLDecision.APPROVE.value == "APPROVE"
        assert HITLDecision.REJECT.value == "REJECT"
        assert HITLDecision.TIMEOUT.value == "TIMEOUT"


# ─────────────────────────────────────────────
# ScopedContextArtifact
# ─────────────────────────────────────────────

class TestScopedContextArtifact:
    def test_to_dict_from_dict_roundtrip(self):
        ctx = ScopedContextArtifact(
            scope_policy="FINANCIAL_ISOLATED_VIEW",
            mission_summary="Pagamento de NF",
            relevant_findings=["NF-e emitida"],
            metadata={"amount": 1000},
            excluded_fields=["cpu_usage"],
        )
        d = ctx.to_dict()
        restored = ScopedContextArtifact.from_dict(d)
        assert restored.scope_policy == "FINANCIAL_ISOLATED_VIEW"
        assert restored.metadata == {"amount": 1000}

    def test_orchestrator_full_shows_everything(self):
        full = {"mission_summary": "test", "findings": ["f1", "f2"],
                "metadata": {"key": "val", "amount": 100}}
        ctx = ScopedContextArtifact.create_scoped(full, "ORCHESTRATOR_FULL")
        assert len(ctx.relevant_findings) == 2
        assert len(ctx.metadata) == 2
        assert ctx.excluded_fields == []

    def test_financial_isolated_filters(self):
        full = {"mission_summary": "test",
                "findings": ["billing issue", "cpu spike"],
                "metadata": {"amount_total": 500, "cpu_percent": 80, "invoice_id": "NF123"}}
        ctx = ScopedContextArtifact.create_scoped(full, "FINANCIAL_ISOLATED_VIEW")
        assert "amount_total" in ctx.metadata
        assert "invoice_id" in ctx.metadata
        assert "cpu_percent" not in ctx.metadata
        assert "cpu_percent" in ctx.excluded_fields
        assert any("billing" in f for f in ctx.relevant_findings)

    def test_technical_metrics_filters(self):
        full = {"mission_summary": "test",
                "findings": ["latency high", "payment failed"],
                "metadata": {"cpu_usage": 90, "amount": 100, "memory_free": 2048}}
        ctx = ScopedContextArtifact.create_scoped(full, "TECHNICAL_METRICS_ONLY")
        assert "cpu_usage" in ctx.metadata
        assert "memory_free" in ctx.metadata
        assert "amount" not in ctx.metadata
        assert any("latency" in f for f in ctx.relevant_findings)

    def test_customer_facing_filters(self):
        full = {"mission_summary": "test",
                "findings": ["order shipped", "cpu spike"],
                "metadata": {"customer_name": "João", "cpu_usage": 90}}
        ctx = ScopedContextArtifact.create_scoped(full, "CUSTOMER_FACING_ONLY")
        assert "customer_name" in ctx.metadata
        assert "cpu_usage" not in ctx.metadata

    def test_scoped_summary_excludes_sensitive(self):
        full = {"mission_summary": "test",
                "findings": ["result ok"],
                "metadata": {"summary": "ok", "payment_id": "123", "cpf_hash": "abc"}}
        ctx = ScopedContextArtifact.create_scoped(full, "SCOPED_SUMMARY")
        assert "summary" in ctx.metadata
        assert "payment_id" not in ctx.metadata
        assert "cpf_hash" not in ctx.metadata

    def test_empty_context(self):
        ctx = ScopedContextArtifact.create_scoped({}, "ORCHESTRATOR_FULL")
        assert ctx.mission_summary == ""
        assert ctx.relevant_findings == []


# ─────────────────────────────────────────────
# HandoffEnvelope
# ─────────────────────────────────────────────

class TestHandoffEnvelope:
    def test_auto_generated_ids(self):
        env = HandoffEnvelope(
            from_persona="maia",
            to_persona="devops",
        )
        assert env.handoff_id.startswith("ho-")
        assert len(env.trace_id) == 32
        assert env.timestamp != ""

    def test_validate_valid(self):
        env = HandoffEnvelope(
            from_persona="maia",
            to_persona="devops",
        )
        assert env.validate() == []

    def test_validate_missing_from(self):
        env = HandoffEnvelope(to_persona="devops")
        errors = env.validate()
        assert any("from_persona" in e for e in errors)

    def test_validate_missing_to(self):
        env = HandoffEnvelope(from_persona="maia")
        errors = env.validate()
        assert any("to_persona" in e for e in errors)

    def test_validate_same_persona(self):
        env = HandoffEnvelope(from_persona="maia", to_persona="maia")
        errors = env.validate()
        assert any("iguais" in e for e in errors)

    def test_to_dict_roundtrip(self):
        original = HandoffEnvelope(
            handoff_type=HandoffType.ESCALATION,
            from_persona="devops",
            to_persona="maia",
            mission_id=42,
            priority=HandoffPriority.HIGH,
            scoped_context=ScopedContextArtifact(
                scope_policy="ORCHESTRATOR_FULL",
                mission_summary="Escalação de incidente",
            ),
            typed_payload={"reason": "server down"},
            requires_ack=True,
        )
        d = original.to_dict()
        assert d["type"] == "governance.handoff"
        assert d["handoff_type"] == "escalation"
        assert d["priority"] == "high"
        assert d["requires_ack"] is True

        restored = HandoffEnvelope.from_dict(d)
        assert restored.handoff_type == HandoffType.ESCALATION
        assert restored.to_persona == "maia"
        assert restored.scoped_context.mission_summary == "Escalação de incidente"


# ─────────────────────────────────────────────
# Factory functions
# ─────────────────────────────────────────────

class TestFactoryFunctions:
    def test_create_delegation(self):
        env = create_delegation(
            from_persona="maia",
            to_persona="devops",
            mission_id=1,
            task_description="Deploy do hotfix",
            full_context={
                "mission_summary": "Hotfix para bug crítico",
                "findings": ["Bug reproduzido", "latency issue"],
                "metadata": {"cpu_usage": 90, "billing_ref": "NF-123"},
            },
            scope_policy="TECHNICAL_METRICS_ONLY",
        )
        assert env.handoff_type == HandoffType.DELEGATION
        assert env.from_persona == "maia"
        assert env.to_persona == "devops"
        assert env.typed_payload["task_description"] == "Deploy do hotfix"
        assert "cpu_usage" in env.scoped_context.metadata
        assert "billing_ref" not in env.scoped_context.metadata

    def test_create_escalation(self):
        env = create_escalation(
            from_persona="finops",
            to_persona="maia",
            mission_id=2,
            reason="Valor acima do limite",
            full_context={
                "mission_summary": "Pagamento de NF",
                "findings": [],
                "metadata": {"amount": 15000},
            },
            financial_amount=15000.0,
        )
        assert env.handoff_type == HandoffType.ESCALATION
        assert env.priority == HandoffPriority.HIGH
        assert env.requires_ack is True
        assert env.typed_payload["financial_amount"] == 15000.0
        assert env.scoped_context.scope_policy == "ORCHESTRATOR_FULL"

    def test_delegation_default_scope(self):
        env = create_delegation(
            from_persona="maia", to_persona="eva",
            mission_id=1, task_description="review",
            full_context={"mission_summary": "test", "findings": [], "metadata": {}},
        )
        assert env.scoped_context.scope_policy == "SCOPED_SUMMARY"

    def test_escalation_default_scope(self):
        env = create_escalation(
            from_persona="devops", to_persona="maia",
            mission_id=1, reason="incident",
            full_context={"mission_summary": "test", "findings": [], "metadata": {}},
        )
        assert env.scoped_context.scope_policy == "ORCHESTRATOR_FULL"


# ─────────────────────────────────────────────
# Integration: HITL + Handoff
# ─────────────────────────────────────────────

class TestHITLHandoffIntegration:
    def test_escalation_triggers_hitl(self):
        """Cenário: FinOps escala para Maia → Maia emite HITL para operador."""
        # 1. Handoff de escalação
        handoff = create_escalation(
            from_persona="persona-finops",
            to_persona="maia-orchestrator",
            mission_id=1,
            reason="Pagamento R$15.000 acima do limite",
            full_context={
                "mission_summary": "Pagamento NF-e",
                "findings": ["NF emitida com sucesso"],
                "metadata": {"amount": 15000},
            },
            financial_amount=15000.0,
        )
        assert handoff.validate() == []

        # 2. Maia cria requisição HITL
        hitl_req = HITLRequest(
            request_id="",
            trace_id=handoff.trace_id,
            mission_id=handoff.mission_id,
            persona_id=handoff.from_persona,
            tool_name="billing_payment",
            reason=HITLReason.FINANCIAL_THRESHOLD,
            context_summary=handoff.scoped_context.mission_summary,
            financial_amount=15000.0,
        )
        frame = hitl_req.to_frame()
        assert frame["type"] == "governance.hitl_required"
        assert frame["financial_amount"] == 15000.0

        # 3. Store registra e operador aprova
        store = HITLPendingStore()
        store.register(hitl_req)
        resp = HITLResponse(
            request_id=hitl_req.request_id,
            decision=HITLDecision.APPROVE,
            operator_id="hugo@kiosk.com",
        )
        resolved = store.resolve(resp)
        assert resolved is not None
        assert store.pending_count == 0

        # 4. Frame de decisão para audit
        decision_frame = resp.to_frame()
        assert decision_frame["type"] == "governance.hitl_decision"
        assert decision_frame["decision"] == "APPROVE"

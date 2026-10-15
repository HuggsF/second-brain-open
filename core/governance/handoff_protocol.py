"""Protocolo de Handoff Tipado entre personas.

Sprint 6 (Gap G10 — Plano de Convergência KIOSK AI-OS + MoE):
Define envelopes tipados de handoff entre agentes, incluindo
contexto escopado e artefatos de delegação.

Tipos de handoff:
  - DELEGATION: Persona A delega tarefa para Persona B
  - ESCALATION: Persona A escala para supervisor
  - REVIEW_REQUEST: Persona A pede revisão a Persona B
  - COLLABORATION: Persona A compartilha contexto com Persona B
  - COMPLETION: Persona A notifica conclusão ao orquestrador

Cada handoff inclui:
  - scoped_context_artifact: visão escopada do contexto (apenas campos
    permitidos para a persona destinatária, baseado no ScopePolicy)
  - typed_payload: dados estruturados específicos do tipo de handoff
  - audit_trail: referência para o WORM audit

Thread-safe. Compatível com o envelope protocol do Nexus WS.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.tracing import new_trace_id, now_iso


class HandoffType(str, Enum):
    """Tipos de handoff entre personas."""
    DELEGATION = "delegation"
    ESCALATION = "escalation"
    REVIEW_REQUEST = "review_request"
    COLLABORATION = "collaboration"
    COMPLETION = "completion"


class HandoffPriority(str, Enum):
    """Prioridade do handoff."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScopedContextArtifact:
    """Artefato de contexto escopado para handoff.

    Contém apenas os campos que a persona destinatária tem
    permissão de ver, baseado no scope_policy do PersonaContract.

    Attributes:
        scope_policy: Política de escopo aplicada (SCOPED_SUMMARY, etc).
        mission_summary: Resumo da missão (sempre visível).
        relevant_findings: Achados relevantes filtrados pelo escopo.
        metadata: Metadados adicionais escopados.
        excluded_fields: Campos que foram excluídos pelo escopo.
    """
    scope_policy: str = "SCOPED_SUMMARY"
    mission_summary: str = ""
    relevant_findings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    excluded_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope_policy": self.scope_policy,
            "mission_summary": self.mission_summary,
            "relevant_findings": list(self.relevant_findings),
            "metadata": dict(self.metadata),
            "excluded_fields": list(self.excluded_fields),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScopedContextArtifact":
        return cls(
            scope_policy=data.get("scope_policy", "SCOPED_SUMMARY"),
            mission_summary=data.get("mission_summary", ""),
            relevant_findings=data.get("relevant_findings", []),
            metadata=data.get("metadata", {}),
            excluded_fields=data.get("excluded_fields", []),
        )

    @classmethod
    def create_scoped(
        cls,
        full_context: Dict[str, Any],
        scope_policy: str,
    ) -> "ScopedContextArtifact":
        """Cria artefato escopado a partir do contexto completo.

        Aplica o scope_policy para filtrar campos:
        - ORCHESTRATOR_FULL: tudo visível
        - SCOPED_SUMMARY: apenas mission_summary + findings não-financeiros
        - FINANCIAL_ISOLATED_VIEW: apenas dados financeiros
        - TECHNICAL_METRICS_ONLY: apenas métricas técnicas
        - CUSTOMER_FACING_ONLY: apenas dados do cliente
        """
        mission_summary = full_context.get("mission_summary", "")
        all_findings = full_context.get("findings", [])
        all_metadata = full_context.get("metadata", {})
        excluded = []

        if scope_policy == "ORCHESTRATOR_FULL":
            return cls(
                scope_policy=scope_policy,
                mission_summary=mission_summary,
                relevant_findings=list(all_findings),
                metadata=dict(all_metadata),
            )

        if scope_policy == "FINANCIAL_ISOLATED_VIEW":
            financial_keys = {"amount", "valor", "total", "billing", "invoice",
                              "cost", "revenue", "budget", "nf_key", "payment"}
            filtered_meta = {k: v for k, v in all_metadata.items()
                            if any(fk in k.lower() for fk in financial_keys)}
            excluded = [k for k in all_metadata if k not in filtered_meta]
            return cls(
                scope_policy=scope_policy,
                mission_summary=mission_summary,
                relevant_findings=[f for f in all_findings if any(
                    fk in f.lower() for fk in financial_keys
                )],
                metadata=filtered_meta,
                excluded_fields=excluded,
            )

        if scope_policy == "TECHNICAL_METRICS_ONLY":
            tech_keys = {"cpu", "memory", "latency", "uptime", "error_rate",
                         "requests", "throughput", "status", "health", "version"}
            filtered_meta = {k: v for k, v in all_metadata.items()
                            if any(tk in k.lower() for tk in tech_keys)}
            excluded = [k for k in all_metadata if k not in filtered_meta]
            return cls(
                scope_policy=scope_policy,
                mission_summary=mission_summary,
                relevant_findings=[f for f in all_findings if any(
                    tk in f.lower() for tk in tech_keys
                )],
                metadata=filtered_meta,
                excluded_fields=excluded,
            )

        if scope_policy == "CUSTOMER_FACING_ONLY":
            customer_keys = {"customer", "order", "pedido", "tracking",
                             "delivery", "product", "produto", "client"}
            filtered_meta = {k: v for k, v in all_metadata.items()
                            if any(ck in k.lower() for ck in customer_keys)}
            excluded = [k for k in all_metadata if k not in filtered_meta]
            return cls(
                scope_policy=scope_policy,
                mission_summary=mission_summary,
                relevant_findings=[f for f in all_findings if any(
                    ck in f.lower() for ck in customer_keys
                )],
                metadata=filtered_meta,
                excluded_fields=excluded,
            )

        # SCOPED_SUMMARY (default): resumo + findings sem dados financeiros
        sensitive_keys = {"amount", "valor", "total", "billing", "payment",
                          "cpf", "cnpj", "card", "password", "token"}
        filtered_meta = {k: v for k, v in all_metadata.items()
                        if not any(sk in k.lower() for sk in sensitive_keys)}
        excluded = [k for k in all_metadata if k not in filtered_meta]
        return cls(
            scope_policy=scope_policy,
            mission_summary=mission_summary,
            relevant_findings=list(all_findings),
            metadata=filtered_meta,
            excluded_fields=excluded,
        )


@dataclass
class HandoffEnvelope:
    """Envelope tipado de handoff entre personas.

    Attributes:
        handoff_id: ID único do handoff.
        handoff_type: Tipo de handoff (DELEGATION, ESCALATION, etc).
        from_persona: Persona que origina o handoff.
        to_persona: Persona destinatária.
        trace_id: W3C trace_id da operação.
        mission_id: ID da missão.
        priority: Prioridade do handoff.
        scoped_context: Artefato de contexto escopado.
        typed_payload: Dados específicos do tipo de handoff.
        timestamp: ISO 8601 timestamp.
        requires_ack: Se True, destinatário deve confirmar recebimento.
    """
    handoff_id: str = ""
    handoff_type: HandoffType = HandoffType.DELEGATION
    from_persona: str = ""
    to_persona: str = ""
    trace_id: str = ""
    mission_id: int = 0
    priority: HandoffPriority = HandoffPriority.NORMAL
    scoped_context: ScopedContextArtifact = field(default_factory=ScopedContextArtifact)
    typed_payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    requires_ack: bool = False

    def __post_init__(self):
        if not self.handoff_id:
            self.handoff_id = f"ho-{new_trace_id()[:16]}"
        if not self.trace_id:
            self.trace_id = new_trace_id()
        if not self.timestamp:
            self.timestamp = now_iso()

    def validate(self) -> List[str]:
        """Valida o envelope de handoff."""
        errors = []
        if not self.from_persona:
            errors.append("from_persona é obrigatório")
        if not self.to_persona:
            errors.append("to_persona é obrigatório")
        if self.from_persona == self.to_persona:
            errors.append("from_persona e to_persona não podem ser iguais")
        if not isinstance(self.handoff_type, HandoffType):
            errors.append(f"handoff_type inválido: {self.handoff_type}")
        if not isinstance(self.priority, HandoffPriority):
            errors.append(f"priority inválida: {self.priority}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Serializa como dict para transmissão WS."""
        return {
            "type": "governance.handoff",
            "handoff_id": self.handoff_id,
            "handoff_type": self.handoff_type.value,
            "from_persona": self.from_persona,
            "to_persona": self.to_persona,
            "trace_id": self.trace_id,
            "mission_id": self.mission_id,
            "priority": self.priority.value,
            "scoped_context": self.scoped_context.to_dict(),
            "typed_payload": self.typed_payload,
            "timestamp": self.timestamp,
            "requires_ack": self.requires_ack,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HandoffEnvelope":
        """Deserializa de dict."""
        ctx_raw = data.get("scoped_context", {})
        return cls(
            handoff_id=data.get("handoff_id", ""),
            handoff_type=HandoffType(data.get("handoff_type", "delegation")),
            from_persona=data.get("from_persona", ""),
            to_persona=data.get("to_persona", ""),
            trace_id=data.get("trace_id", ""),
            mission_id=data.get("mission_id", 0),
            priority=HandoffPriority(data.get("priority", "normal")),
            scoped_context=ScopedContextArtifact.from_dict(ctx_raw),
            typed_payload=data.get("typed_payload", {}),
            timestamp=data.get("timestamp", ""),
            requires_ack=data.get("requires_ack", False),
        )


def create_delegation(
    from_persona: str,
    to_persona: str,
    mission_id: int,
    task_description: str,
    full_context: Dict[str, Any],
    scope_policy: str = "SCOPED_SUMMARY",
    priority: HandoffPriority = HandoffPriority.NORMAL,
) -> HandoffEnvelope:
    """Factory para criar um handoff de delegação."""
    return HandoffEnvelope(
        handoff_type=HandoffType.DELEGATION,
        from_persona=from_persona,
        to_persona=to_persona,
        mission_id=mission_id,
        priority=priority,
        scoped_context=ScopedContextArtifact.create_scoped(full_context, scope_policy),
        typed_payload={"task_description": task_description},
    )


def create_escalation(
    from_persona: str,
    to_persona: str,
    mission_id: int,
    reason: str,
    full_context: Dict[str, Any],
    scope_policy: str = "ORCHESTRATOR_FULL",
    financial_amount: Optional[float] = None,
) -> HandoffEnvelope:
    """Factory para criar um handoff de escalação."""
    return HandoffEnvelope(
        handoff_type=HandoffType.ESCALATION,
        from_persona=from_persona,
        to_persona=to_persona,
        mission_id=mission_id,
        priority=HandoffPriority.HIGH,
        scoped_context=ScopedContextArtifact.create_scoped(full_context, scope_policy),
        typed_payload={
            "escalation_reason": reason,
            "financial_amount": financial_amount,
        },
        requires_ack=True,
    )

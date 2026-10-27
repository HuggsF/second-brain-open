"""Protocolo HITL (Human-In-The-Loop) para governança zero-trust.

Sprint 6 (Gap G2 — Plano de Convergência AI-OS + MoE):
Define o protocolo de frames HITL para o Nexus WebSocket, permitindo
que ações de alto risco sejam congeladas até aprovação humana.

Fluxo:
  1. Broker/Orchestrator detecta ação que requer HITL
  2. Emite frame `governance.hitl_required` → congela estado
  3. Frontend exibe prompt de aprovação ao operador humano
  4. Operador envia `governance.hitl_decision` com APPROVE ou REJECT
  5. Pipeline desbloqueia ou aborta com base na decisão

O protocolo é independente do transporte (WebSocket, HTTP, fila) —
opera sobre dicts serializáveis que podem ser transmitidos por qualquer canal.

Thread-safe via threading.Lock para o estado de pendências.
"""

import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.tracing import new_trace_id, now_iso


class HITLDecision(str, Enum):
    """Decisão do operador humano."""
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    TIMEOUT = "TIMEOUT"


class HITLReason(str, Enum):
    """Motivo pelo qual HITL foi requerido."""
    HIGH_RISK_TOOL = "high_risk_tool"
    FINANCIAL_THRESHOLD = "financial_threshold"
    PERSONA_CONTRACT = "persona_contract"
    GATE_YELLOW = "gate_yellow"
    AUTONOMY_ESCALATION = "autonomy_escalation"
    MANUAL_ESCALATION = "manual_escalation"


@dataclass
class HITLRequest:
    """Requisição de aprovação HITL.

    Attributes:
        request_id: ID único da requisição HITL.
        trace_id: W3C trace_id da operação.
        mission_id: ID da missão em execução.
        persona_id: Persona que originou a requisição.
        tool_name: Ferramenta que será executada.
        reason: Motivo pelo qual HITL é necessário.
        context_summary: Resumo do contexto para o operador.
        args_redacted: Args da tool com dados sensíveis mascarados.
        timestamp: ISO 8601 timestamp da criação.
        timeout_seconds: Segundos até timeout automático.
        financial_amount: Valor financeiro envolvido (se aplicável).
    """
    request_id: str
    trace_id: str
    mission_id: int
    persona_id: str
    tool_name: str
    reason: HITLReason
    context_summary: str = ""
    args_redacted: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    timeout_seconds: float = 300.0
    financial_amount: Optional[float] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = now_iso()
        if not self.request_id:
            self.request_id = f"hitl-{new_trace_id()[:16]}"

    def to_frame(self) -> Dict[str, Any]:
        """Serializa como frame `governance.hitl_required` para o Nexus WS."""
        return {
            "type": "governance.hitl_required",
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "mission_id": self.mission_id,
            "persona_id": self.persona_id,
            "tool_name": self.tool_name,
            "reason": self.reason.value,
            "context_summary": self.context_summary,
            "args_redacted": self.args_redacted,
            "timestamp": self.timestamp,
            "timeout_seconds": self.timeout_seconds,
            "financial_amount": self.financial_amount,
        }


@dataclass
class HITLResponse:
    """Resposta do operador humano a uma requisição HITL.

    Attributes:
        request_id: ID da requisição HITL original.
        decision: APPROVE, REJECT ou TIMEOUT.
        operator_id: Identificador do operador (hash).
        justification: Justificativa da decisão.
        timestamp: ISO 8601 timestamp da decisão.
    """
    request_id: str
    decision: HITLDecision
    operator_id: str = "unknown"
    justification: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = now_iso()

    @property
    def operator_hash(self) -> str:
        """Hash SHA-256 do operador para audit trail (não armazena identidade real)."""
        return hashlib.sha256(self.operator_id.encode("utf-8")).hexdigest()[:16]

    def to_frame(self) -> Dict[str, Any]:
        """Serializa como frame `governance.hitl_decision` para o Nexus WS."""
        return {
            "type": "governance.hitl_decision",
            "request_id": self.request_id,
            "decision": self.decision.value,
            "operator_hash": self.operator_hash,
            "justification": self.justification,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_frame(cls, frame: Dict[str, Any]) -> "HITLResponse":
        """Deserializa de frame do Nexus WS."""
        return cls(
            request_id=frame.get("request_id", ""),
            decision=HITLDecision(frame.get("decision", "REJECT")),
            operator_id=frame.get("operator_id", frame.get("operator_hash", "unknown")),
            justification=frame.get("justification", ""),
            timestamp=frame.get("timestamp", ""),
        )


class HITLPendingStore:
    """Armazena requisições HITL pendentes de decisão.

    Thread-safe. O Orchestrator registra pendências aqui e consulta
    quando uma decisão chega do frontend.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: Dict[str, HITLRequest] = {}
        self._decisions: Dict[str, HITLResponse] = {}

    def register(self, request: HITLRequest) -> None:
        """Registra uma requisição HITL pendente."""
        with self._lock:
            self._pending[request.request_id] = request

    def resolve(self, response: HITLResponse) -> Optional[HITLRequest]:
        """Resolve uma requisição pendente com a decisão do operador.

        Returns:
            A HITLRequest original se encontrada, ou None.
        """
        with self._lock:
            request = self._pending.pop(response.request_id, None)
            if request is not None:
                self._decisions[response.request_id] = response
            return request

    def timeout_expired(self, request_id: str) -> Optional[HITLRequest]:
        """Remove uma requisição expirada e registra TIMEOUT."""
        with self._lock:
            request = self._pending.pop(request_id, None)
            if request is not None:
                self._decisions[request_id] = HITLResponse(
                    request_id=request_id,
                    decision=HITLDecision.TIMEOUT,
                    operator_id="system",
                    justification="Timeout de aprovação expirado",
                )
            return request

    def get_pending(self) -> List[HITLRequest]:
        """Lista todas as requisições pendentes."""
        with self._lock:
            return list(self._pending.values())

    def get_decision(self, request_id: str) -> Optional[HITLResponse]:
        """Consulta a decisão para uma requisição."""
        with self._lock:
            return self._decisions.get(request_id)

    def is_pending(self, request_id: str) -> bool:
        """Verifica se uma requisição está pendente."""
        with self._lock:
            return request_id in self._pending

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    @property
    def decision_count(self) -> int:
        with self._lock:
            return len(self._decisions)

    def clear(self) -> None:
        """Limpa todas as pendências e decisões."""
        with self._lock:
            self._pending.clear()
            self._decisions.clear()

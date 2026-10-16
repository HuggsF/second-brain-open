"""Memória efêmera de sessão (Short-Term Memory).

Isolada estritamente por mission_id ou task_id para evitar contaminação
cruzada entre execuções ou agentes concorrentes.

Sprint 2 (Gap G6): Adicionado get_scoped_view() com políticas de isolamento
de contexto por persona MoE. Cada agente recebe apenas os campos da sessão
autorizados pela sua scope_policy, eliminando context bleed.
"""
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set
import datetime


class ScopePolicy(str, Enum):
    """Políticas de isolamento de contexto por persona (MoE zero-trust)."""
    FULL_ACCESS = "FULL_ACCESS"                         # Orquestradora (Maia): acesso completo
    SCOPED_SUMMARY = "SCOPED_SUMMARY"                   # Resumo seguro: sem payloads, sem PII
    FINANCIAL_ISOLATED_VIEW = "FINANCIAL_ISOLATED_VIEW"  # FinOps: dados financeiros isolados
    TECHNICAL_METRICS_ONLY = "TECHNICAL_METRICS_ONLY"    # SRE/DevOps: apenas métricas técnicas
    SECURITY_AUDIT_VIEW = "SECURITY_AUDIT_VIEW"          # SecOps: view de auditoria e segurança


# Campos permitidos por política de escopo
_SCOPE_ALLOWED_FIELDS: Dict[ScopePolicy, Optional[FrozenSet[str]]] = {
    ScopePolicy.FULL_ACCESS: None,  # None = todos os campos (sem filtro)
    ScopePolicy.SCOPED_SUMMARY: frozenset({
        "agent", "role", "event", "status", "summary", "bubble",
        "recorded_at", "type", "step_index",
    }),
    ScopePolicy.FINANCIAL_ISOLATED_VIEW: frozenset({
        "agent", "role", "event", "status", "summary", "recorded_at",
        "amount", "currency", "invoice_id", "nfe_key", "payment_status",
        "financial_details", "type",
    }),
    ScopePolicy.TECHNICAL_METRICS_ONLY: frozenset({
        "agent", "role", "event", "status", "summary", "recorded_at",
        "duration_ms", "cpu_percent", "memory_mb", "error_type",
        "service_name", "endpoint", "response_code", "type",
    }),
    ScopePolicy.SECURITY_AUDIT_VIEW: frozenset({
        "agent", "role", "event", "status", "summary", "recorded_at",
        "gate_results", "semaphore", "violations", "pii_detected",
        "injection_score", "trace_id", "type",
    }),
}

# Mapeamento padrão persona → scope_policy
PERSONA_SCOPE_POLICIES: Dict[str, ScopePolicy] = {
    "manager":    ScopePolicy.FULL_ACCESS,
    "researcher": ScopePolicy.SCOPED_SUMMARY,
    "coder":      ScopePolicy.TECHNICAL_METRICS_ONLY,
    "writer":     ScopePolicy.SCOPED_SUMMARY,
    "reviewer":   ScopePolicy.SECURITY_AUDIT_VIEW,
}

_CROSS_PERSONA_SAFE_FIELDS: FrozenSet[str] = frozenset({
    "agent", "role", "event", "status", "summary", "bubble",
    "recorded_at", "type", "step_index",
    # Exclui: tool_args, tool_result, raw_input, raw_output (podem conter PII)
})


class SessionMemoryStore:
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    def append(self, session_id: str, record: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        entry = {
            **record,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._sessions[session_id].append(entry)

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._sessions.get(session_id, []))

    def get_scoped_view(
        self,
        session_id: str,
        persona_id: str,
        scope_policy: Optional[ScopePolicy] = None,
    ) -> List[Dict[str, Any]]:
        """Retorna o histórico filtrado por política de escopo da persona.

        Sprint 2 (Gap G6 — Scoped Context View):
        Cada persona recebe apenas os campos autorizados pela sua scope_policy,
        eliminando context bleed entre agentes.

        Args:
            session_id: ID da sessão.
            persona_id: Role do agente (manager, researcher, coder, etc.).
            scope_policy: Política de escopo explícita. Se None, usa o mapeamento
                padrão PERSONA_SCOPE_POLICIES.

        Returns:
            Lista de registros filtrados contendo apenas os campos permitidos.
        """
        history = self._sessions.get(session_id, [])
        if not history:
            return []

        # Resolve a política de escopo
        policy = scope_policy or PERSONA_SCOPE_POLICIES.get(persona_id, ScopePolicy.SCOPED_SUMMARY)
        allowed_fields = _SCOPE_ALLOWED_FIELDS.get(policy)

        # FULL_ACCESS com verificação cross-persona (INV-N13)
        if allowed_fields is None:
            # H-04: Filtrar records que têm info de ownership
            owned_records = [
                r for r in history if r.get("persona_id") or r.get("agent")
            ]
            # H-04: Se nenhum record tem ownership info, tratar como cross-persona
            # (all([]) == True era bug: concedia acesso total a sessões anônimas)
            if owned_records and all(
                r.get("persona_id") == persona_id or r.get("agent") == persona_id
                for r in owned_records
            ):
                own_records = True
            else:
                own_records = False

            if own_records or persona_id in ("maia-orchestrator", "manager"):
                return list(history)  # própria sessão ou supervisor: acesso total
            # Cross-persona: filtrar campos sensíveis
            return [
                {k: v for k, v in record.items() if k in _CROSS_PERSONA_SAFE_FIELDS}
                for record in history
            ]

        # Filtra campos para o escopo permitido
        scoped = []
        for record in history:
            filtered = {k: v for k, v in record.items() if k in allowed_fields}
            filtered["_scope_policy"] = policy.value
            filtered["_persona_id"] = persona_id
            scoped.append(filtered)
        return scoped

    def purge_session(self, session_id: str) -> int:
        """Purga a memória de uma sessão específica sem afetar outras."""
        count = len(self._sessions.get(session_id, []))
        if session_id in self._sessions:
            del self._sessions[session_id]
        return count

    def purge_all(self) -> int:
        """Purga todas as memórias efêmeras em execução."""
        total = sum(len(v) for v in self._sessions.values())
        self._sessions.clear()
        return total

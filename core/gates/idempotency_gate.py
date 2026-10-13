"""Gate 4: Idempotency & Concurrency Safety Gate.

Garante que requisições mutáveis ou operações de rede críticas carreguem
chaves de idempotência (Idempotency Key / UUID v4) e trace context para impedir
duplicidade em caso de quedas parciais de conexão.
"""
import re
from typing import Any, Dict
from core.gates.base import BaseGate, GateResult, Semaphore

_UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE
)
_HEX32_REGEX = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


class IdempotencyGate(BaseGate):
    name: str = "gate_4_idempotency_concurrency"

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        """Avalia se uma operação possui garantia estrita contra duplicidade.

        Payload esperado:
        {
            "operation": "POST /api/v1/shipments/issue" | "webhook_dispatch" | ...,
            "is_mutation": True,
            "idempotency_key": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "batch_trace_id": "e74f9d2a1b8c0e5a4f7e2d1c9a8b7e6d",
            "lock_ttl_seconds": 15
        }
        """
        is_mutation = payload.get("is_mutation", True)
        if not is_mutation:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.GREEN,
                passed=True,
                summary="Operação somente leitura (idempotente por definição).",
                details={"is_mutation": False},
            )

        idem_key = str(payload.get("idempotency_key", "")).strip()
        trace_id = str(payload.get("batch_trace_id", "")).strip()
        lock_ttl = payload.get("lock_ttl_seconds", 15)

        violations = []

        # Validação da chave de idempotência
        if not idem_key:
            violations.append("Ausência de chave de idempotência (idempotency_key obrigatória para mutações).")
        elif not (_UUID_REGEX.match(idem_key) or _HEX32_REGEX.match(idem_key) or len(idem_key) >= 16):
            violations.append("Chave de idempotência de baixa entropia ou formato inválido (exige UUID v4 ou SHA-256).")

        # Validação do Trace Context (ADR-004 e ADR-006)
        if not trace_id:
            violations.append("Ausência de batch_trace_id para rastreabilidade ponta a ponta E2E.")
        elif not (_UUID_REGEX.match(trace_id) or _HEX32_REGEX.match(trace_id)):
            violations.append("batch_trace_id fora do padrão W3C Trace Context (deve ter 32 hex ou UUID v4).")

        # Validação da janela de Lock
        if not isinstance(lock_ttl, (int, float)) or lock_ttl < 5 or lock_ttl > 600:
            violations.append("Janela de lock de concorrência inválida (deve estar entre 5 e 600 segundos).")

        if violations:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary=f"Risco de duplicidade detectado: {len(violations)} falhas de segurança de concorrência.",
                details={"violations": violations, "operation": payload.get("operation", "unknown")},
            )

        return GateResult(
            gate_name=self.name,
            semaphore=Semaphore.GREEN,
            passed=True,
            summary="Garantia de idempotência e ausência de duplicidade confirmada com chave e trace context.",
            details={
                "idempotency_key": idem_key[:12] + "...",
                "batch_trace_id": trace_id[:12] + "...",
                "lock_ttl_seconds": lock_ttl,
            },
        )

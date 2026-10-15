"""Gate 5: DLP & Anti-Injection Input Gate.

Sprint 1 (Gap G1 — Plano de Convergência KIOSK AI-OS + MoE):
Atua ANTES do LLM como guardrail de entrada, mascarando PII e detectando
tentativas de prompt injection. Integra com a Quarantine Store existente
para isolar payloads maliciosos.

Payload esperado:
{
    "input_text": "texto do usuário ou agente...",
    "pii_policy": "REDACT_ALL" | "REDACT_CPF_AND_CARDS" | "ALLOW_ALL",
    "injection_threshold": 0.80  (opcional, default 0.80)
}
"""
from typing import Any, Dict

from core.gates.base import BaseGate, GateResult, Semaphore
from core.security.dlp_guardrail import DLPGuardrailEngine


class DLPInputGate(BaseGate):
    name: str = "gate_5_dlp_input"

    def __init__(self, injection_threshold: float = 0.80):
        self.default_threshold = injection_threshold

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        """Avalia o texto de entrada contra PII e Prompt Injection.

        Returns:
            RED se prompt injection detectado (score >= threshold)
            YELLOW se PII encontrado e mascarado
            GREEN se limpo
        """
        input_text = payload.get("input_text", "")
        threshold = payload.get("injection_threshold", self.default_threshold)

        if not isinstance(input_text, str) or not input_text.strip():
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.GREEN,
                passed=True,
                summary="Sem texto de entrada para inspecionar.",
                details={"input_length": 0},
            )

        engine = DLPGuardrailEngine(
            injection_threshold=threshold,
            mask_pii=True,
        )
        result = engine.inspect(input_text)

        if result.is_blocked:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary=f"Prompt Injection detectado (score={result.injection_score:.2f}). Payload isolado.",
                details={
                    **result.to_dict(),
                    "redacted_text": result.redacted_text[:200] + "..." if len(result.redacted_text) > 200 else result.redacted_text,
                },
            )

        if result.has_pii:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.YELLOW,
                passed=True,
                summary=f"PII detectado e mascarado: {result.pii_count} ocorrências ({', '.join(set(m.pii_type for m in result.pii_matches))}).",
                details={
                    **result.to_dict(),
                    "redacted_text": result.redacted_text[:200] + "..." if len(result.redacted_text) > 200 else result.redacted_text,
                },
            )

        return GateResult(
            gate_name=self.name,
            semaphore=Semaphore.GREEN,
            passed=True,
            summary="Texto de entrada limpo: sem PII e sem indicadores de injection.",
            details=result.to_dict(),
        )

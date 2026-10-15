"""Gate 6: Forbidden Topics — Tópicos proibidos por persona.

Sprint 5 (Gap G9 — Plano de Convergência KIOSK AI-OS + MoE):
Verifica se o input de texto contém tópicos proibidos declarados
no contrato da persona. Os tópicos são definidos como keywords ou
frases no campo `forbidden_topics` do PersonaContract.

Funciona como um gate adicional do CompoundGatePipeline:
  - RED: Input contém tópico proibido → bloqueia execução
  - GREEN: Nenhum tópico proibido detectado

O gate é case-insensitive e normaliza acentos para matching robusto.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional

from core.gates.base import BaseGate, GateResult, Semaphore


def _normalize(text: str) -> str:
    """Normaliza texto: lowercase, remove acentos, espaços extras."""
    text = text.lower().strip()
    # Remove acentos (NFD + strip combining marks)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class ForbiddenTopicsGate(BaseGate):
    """Gate que verifica tópicos proibidos por persona.

    Args:
        forbidden_topics: Lista de tópicos proibidos (keywords ou frases).
                         Pode ser configurado por persona via PersonaContract.
    """
    name: str = "gate_6_forbidden_topics"

    def __init__(self, forbidden_topics: Optional[List[str]] = None):
        self.forbidden_topics = forbidden_topics or []
        # Pré-compila padrões normalizados para matching eficiente
        self._patterns = [
            _normalize(topic)
            for topic in self.forbidden_topics
            if topic.strip()
        ]

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        """Avalia se o input contém tópicos proibidos.

        Payload esperado:
        {
            "input_text": "texto a ser avaliado",
            "forbidden_topics": ["tópico1", "tópico2"]  # opcional, sobrescreve __init__
        }
        """
        input_text = payload.get("input_text", "")
        if not isinstance(input_text, str) or not input_text.strip():
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.GREEN,
                passed=True,
                summary="Sem texto para avaliar.",
                details={"topics_checked": 0},
            )

        # Permite sobrescrever tópicos via payload (para testes ou dinâmico)
        topics_raw = payload.get("forbidden_topics", None)
        if topics_raw is not None and isinstance(topics_raw, list):
            patterns = [_normalize(t) for t in topics_raw if isinstance(t, str) and t.strip()]
        else:
            patterns = self._patterns

        if not patterns:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.GREEN,
                passed=True,
                summary="Nenhum tópico proibido configurado.",
                details={"topics_checked": 0},
            )

        normalized_input = _normalize(input_text)
        violations: List[str] = []

        for pattern in patterns:
            if pattern in normalized_input:
                # Encontra o tópico original para o report
                original = next(
                    (t for t in (topics_raw or self.forbidden_topics)
                     if _normalize(t) == pattern),
                    pattern,
                )
                violations.append(original)

        if violations:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary=f"Bloqueado: {len(violations)} tópico(s) proibido(s) detectado(s).",
                details={
                    "violations": violations,
                    "topics_checked": len(patterns),
                },
            )

        return GateResult(
            gate_name=self.name,
            semaphore=Semaphore.GREEN,
            passed=True,
            summary=f"Aprovado: {len(patterns)} tópico(s) proibido(s) verificados, nenhum encontrado.",
            details={"topics_checked": len(patterns)},
        )

"""Gate 6: Forbidden Topics — Tópicos proibidos por persona.

Sprint 5 (Gap G9 — Plano de Convergência AI-OS + MoE):
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
    # F-03: Colapsar qualquer sequência de whitespace (espaço, tab, newline)
    # para prevenir bypass de multi-word patterns via espaços extras
    text = re.sub(r'\s+', ' ', text)
    # Remove acentos (NFD + strip combining marks)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


SYSTEM_BASE_FORBIDDEN_TOPICS = [
    "senhas de produção",
    "chaves de api",
    "credenciais de deploy",
    "tokens de acesso",
    "injection de prompt",
]


class ForbiddenTopicsGate(BaseGate):
    """Gate que verifica tópicos proibidos por persona.

    Args:
        forbidden_topics: Lista de tópicos proibidos (keywords ou frases).
                         Pode ser configurado por persona via PersonaContract.
    """
    name: str = "gate_6_forbidden_topics"

    def __init__(self, forbidden_topics: Optional[List[str]] = None):
        base = list(SYSTEM_BASE_FORBIDDEN_TOPICS)
        extra = forbidden_topics or []
        self.forbidden_topics = list(set(base + extra))
        self._patterns = [_normalize(t) for t in self.forbidden_topics if isinstance(t, str) and t.strip()]

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

        # PD-OVR-005: payload adiciona, nunca substitui a base
        supplemental = payload.get("forbidden_topics", None)
        if supplemental and isinstance(supplemental, list):
            extra_patterns = [_normalize(t) for t in supplemental if isinstance(t, str) and t.strip()]
            patterns = list(set(self._patterns + extra_patterns))
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
            if re.search(r'\b' + re.escape(pattern) + r'\b', normalized_input, re.UNICODE):
                # Encontra o tópico original para o report
                all_topics = self.forbidden_topics + (supplemental if supplemental else [])
                original = next(
                    (t for t in all_topics if _normalize(t) == pattern),
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

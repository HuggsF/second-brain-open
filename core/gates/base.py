"""Quality Gates determinísticos para o Compound AI System.

Cada Gate atua como um guardrail determinístico que intercepta saídas de agentes
e modelos antes de permitir a progressão para a próxima etapa da esteira.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import datetime


class Semaphore(str, Enum):
    GREEN = "GREEN"    # 🟢 Operação íntegra, aprovada e validada
    YELLOW = "YELLOW"  # 🟡 Alerta / Gaps parciais / Em andamento
    RED = "RED"        # 🔴 Falha de validação, alucinação ou quebra de contrato


@dataclass
class GateResult:
    gate_name: str
    semaphore: Semaphore
    passed: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "semaphore": self.semaphore.value,
            "passed": self.passed,
            "summary": self.summary,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class BaseGate:
    """Interface base para todos os Quality Gates do sistema."""

    name: str = "base_gate"

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        raise NotImplementedError("Subclasses devem implementar evaluate()")

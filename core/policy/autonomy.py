"""Avaliação de autonomia baseada em PersonaContract.

Sprint 5 (Gap G11 — Plano de Convergência AI-OS + MoE):
Mapeia os 3 níveis de autonomia declarativos do PersonaContract para
os vereditos nativos do AI-OS (APPROVE, ESCALATE, DENY).

Níveis:
  auto_execute         → APPROVE imediato para tools na allowlist da role
  supervisor_approval  → ESCALATE para tools de escrita/prod (requer humano)
  conditional_hitl     → APPROVE se args estão dentro do limiar financeiro,
                         senão ESCALATE (Human-In-The-Loop condicional)

A função `evaluate_autonomy()` é consultiva: retorna um Verdict que o
Broker pode usar para sobrescrever ou refinar a decisão do decide().
Não altera o fluxo existente — é chamada adicionalmente.
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Dict, Optional

from core.policy.verdict import Decision, Reason, Verdict

UNPARSEABLE = object()


class AutonomyLevel(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    SUPERVISOR_APPROVAL = "supervisor_approval"
    CONDITIONAL_HITL = "conditional_hitl"


# Reasons adicionais para autonomia
class AutonomyReason(str, Enum):
    auto_within_contract = "auto_within_contract"
    supervisor_required_by_contract = "supervisor_required_by_contract"
    hitl_above_threshold = "hitl_above_threshold"
    hitl_below_threshold = "hitl_below_threshold"
    hitl_no_amount = "hitl_no_amount"


@dataclass(frozen=True)
class AutonomyVerdict:
    """Resultado da avaliação de autonomia.

    Attributes:
        decision: APPROVE, ESCALATE ou DENY.
        level: Nível de autonomia avaliado.
        reason: Motivo do veredito.
        detail: Detalhes adicionais.
        requires_hitl: Se True, requer aprovação humana.
    """
    decision: Decision
    level: AutonomyLevel
    reason: AutonomyReason
    detail: str = ""
    requires_hitl: bool = False


def evaluate_autonomy(
    autonomy_level: str,
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
    auto_approve_up_to_brl: Optional[float] = None,
) -> AutonomyVerdict:
    """Avalia o nível de autonomia para uma chamada de tool.

    Args:
        autonomy_level: Um dos 3 níveis ("auto_execute", "supervisor_approval",
                        "conditional_hitl").
        tool_name: Nome da ferramenta sendo chamada.
        args: Argumentos da chamada (para avaliação financeira em conditional_hitl).
        auto_approve_up_to_brl: Limite financeiro para auto-aprovação (BRL).

    Returns:
        AutonomyVerdict com decisão, razão e se requer HITL.
    """
    try:
        level = AutonomyLevel(autonomy_level)
    except ValueError:
        # Nível desconhecido → ESCALATE por segurança
        return AutonomyVerdict(
            decision=Decision.ESCALATE,
            level=AutonomyLevel.SUPERVISOR_APPROVAL,
            reason=AutonomyReason.supervisor_required_by_contract,
            detail=f"Nível de autonomia desconhecido: {autonomy_level}",
            requires_hitl=True,
        )

    if level == AutonomyLevel.AUTO_EXECUTE:
        return AutonomyVerdict(
            decision=Decision.APPROVE,
            level=level,
            reason=AutonomyReason.auto_within_contract,
            detail=f"auto_execute: {tool_name} aprovado pelo contrato",
        )

    if level == AutonomyLevel.SUPERVISOR_APPROVAL:
        return AutonomyVerdict(
            decision=Decision.ESCALATE,
            level=level,
            reason=AutonomyReason.supervisor_required_by_contract,
            detail=f"supervisor_approval: {tool_name} requer aprovação",
            requires_hitl=True,
        )

    # CONDITIONAL_HITL: avalia limiar financeiro
    if args is None:
        args = {}

    # Busca valor financeiro nos args (suporta vários nomes de campo)
    amount = _extract_amount(args)

    if amount is UNPARSEABLE:
        return AutonomyVerdict(
            decision=Decision.ESCALATE,
            level=level,
            reason=AutonomyReason.hitl_above_threshold,
            detail="campo financeiro inválido — requer aprovação humana",
            requires_hitl=True,
        )

    if amount is None:
        # Sem valor financeiro → aprova se tem limite definido e > 0,
        # senão escalona
        if auto_approve_up_to_brl is not None and auto_approve_up_to_brl >= 0:
            return AutonomyVerdict(
                decision=Decision.APPROVE,
                level=level,
                reason=AutonomyReason.hitl_no_amount,
                detail=f"conditional_hitl: sem valor financeiro, aprovado dentro do contrato",
            )
        return AutonomyVerdict(
            decision=Decision.ESCALATE,
            level=level,
            reason=AutonomyReason.hitl_no_amount,
            detail=f"conditional_hitl: sem valor financeiro e sem limite definido",
            requires_hitl=True,
        )

    if auto_approve_up_to_brl is not None and amount <= auto_approve_up_to_brl:
        return AutonomyVerdict(
            decision=Decision.APPROVE,
            level=level,
            reason=AutonomyReason.hitl_below_threshold,
            detail=f"conditional_hitl: R${amount:.2f} <= R${auto_approve_up_to_brl:.2f}",
        )

    return AutonomyVerdict(
        decision=Decision.ESCALATE,
        level=level,
        reason=AutonomyReason.hitl_above_threshold,
        detail=f"conditional_hitl: R${amount:.2f} > R${auto_approve_up_to_brl or 0:.2f}",
        requires_hitl=True,
    )


def _parse_brl(val):
    """Parseia formato BR: 'R$ 50.000,00' → 50000.00. Retorna None se inválido."""
    if isinstance(val, bool):  # bool herda de int no Python
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace("R$", "").replace(" ", "").strip()
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            result = float(cleaned)
            return result if math.isfinite(result) else None
        except (ValueError, TypeError):
            return None
    return None


def _extract_amount(args: Dict[str, Any]):
    """Extrai valor financeiro dos argumentos.

    Retorna:
        float — valor válido parseado.
        None — nenhum campo financeiro presente.
        UNPARSEABLE — campo presente mas inválido (formato, negativo, NaN, shadowing).
    """
    amount_fields = ("amount", "valor", "value", "total", "amount_brl")
    found_values = []
    for field_name in amount_fields:
        val = args.get(field_name)
        if val is not None:
            parsed = _parse_brl(val)
            if parsed is None or parsed < 0 or not math.isfinite(parsed):
                return UNPARSEABLE
            found_values.append(parsed)
    if not found_values:
        return None
    # GAP-03: shadowing — valores conflitantes → UNPARSEABLE
    if len(set(found_values)) > 1:
        return UNPARSEABLE
    return found_values[0]

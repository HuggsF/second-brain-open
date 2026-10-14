"""Portões no início da missão: monta o plano dos passos e decide proceed/approval/block."""
from typing import Any, Dict, List, Optional

from core import broker
from core.gates import CompoundGatePipeline

_BUDGET_SECONDS = 30
_ACTIONS = {"GREEN": "proceed", "YELLOW": "approval"}
_STATUS = {"proceed": "ok", "approval": "escalated", "block": "refused"}


def build_plan(steps: List[dict]) -> dict:
    """Plano linear (cada passo depende do anterior). Nunca levanta: o que estiver malformado segue como está e o DagGate reprova."""
    plan_steps = []
    for i, step in enumerate(steps if isinstance(steps, (list, tuple)) else [], start=1):
        step = step if isinstance(step, dict) else {}
        plan_steps.append({
            "id": f"s{i}",
            "role": step.get("agent"),
            "dependsOn": [f"s{i - 1}"] if i > 1 else [],
            "tools": [step.get("tool")],
            "budgetSeconds": _BUDGET_SECONDS,
        })
    return {"version": 1, "steps": plan_steps}


def check_mission(steps: List[dict], mission_id: int,
                  pipeline: Optional[CompoundGatePipeline] = None) -> Dict[str, Any]:
    """Roda os portões sobre o plano. RED ou qualquer falha bloqueia; YELLOW pede aprovação."""
    semaphore, gate_results = "RED", []
    try:
        report = (pipeline or CompoundGatePipeline()).run_all({"plan": build_plan(steps)})
        semaphore = str(report["global_semaphore"])
        gate_results = list(report.get("gate_results", []))
    except Exception:
        semaphore, gate_results = "RED", []
    if semaphore not in ("GREEN", "YELLOW"):
        semaphore = "RED"
    action = _ACTIONS.get(semaphore, "block")
    broker.record_event("agent:manager", "gate.pipeline", _STATUS[action],
                        {"semaphore": semaphore, "action": action}, task_id=f"M{mission_id}")
    return {"action": action, "semaphore": semaphore, "gate_results": gate_results}

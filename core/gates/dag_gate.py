"""Gate 2: DAG & Cycle Validation Gate.

Valida planos de execução de múltiplos agentes garantindo que o fluxo seja um
Grafo Acíclico Direcionado (DAG) sem loops infinitos, com papéis e ferramentas autorizados.
"""
from typing import Any, Dict, List, Set
from core.gates.base import BaseGate, GateResult, Semaphore

ALLOWED_ROLES = {"researcher", "architect", "dev", "qa", "devops", "writer", "reviewer"}
ALLOWED_TOOLS = {
    "search", "read_graph", "read_sources", "search_knowledge_base",
    "get_adr", "get_system_architecture", "validate_plan", "validate_adr_schema",
    "run_concurrency_test", "run_preflight_checklist", "generate_patch",
    "inspect_api_contract", "compare_hml_prod_payloads"
}


class DagGate(BaseGate):
    name: str = "gate_2_dag_cycle_validation"

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        """Avalia um plano de execução multiagente.

        Payload esperado:
        {
            "version": 1,
            "steps": [
                {"id": "step_1", "role": "researcher", "dependsOn": [], "tools": ["search"], "budgetSeconds": 30},
                ...
            ]
        }
        """
        plan = payload.get("plan") or payload
        errors: List[str] = []

        if not isinstance(plan, dict):
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary="Formato de plano inválido (deve ser um dicionário/objeto).",
                details={"errors": ["Plano não é um objeto"]},
            )

        if plan.get("version") != 1:
            errors.append("Versão do plano deve ser 1.")

        steps = plan.get("steps")
        if not isinstance(steps, list) or not (1 <= len(steps) <= 100):
            errors.append("O plano deve conter entre 1 e 100 etapas.")
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary="Quantidade de etapas inválida no DAG.",
                details={"errors": errors},
            )

        by_id: Dict[str, Dict[str, Any]] = {}
        for idx, step in enumerate(steps):
            prefix = f"Etapa {idx + 1}: "
            if not isinstance(step, dict):
                errors.append(f"{prefix}formato inválido.")
                continue

            step_id = step.get("id")
            if not step_id or not isinstance(step_id, str):
                errors.append(f"{prefix}ID ausente ou inválido.")
            elif step_id in by_id:
                errors.append(f"{prefix}ID duplicado '{step_id}'.")
            else:
                by_id[step_id] = step

            role = step.get("role")
            if role not in ALLOWED_ROLES:
                errors.append(f"{prefix}papel '{role}' não autorizado.")

            tools = step.get("tools", [])
            if not isinstance(tools, list) or any(t not in ALLOWED_TOOLS for t in tools):
                errors.append(f"{prefix}contém ferramentas não autorizadas.")

            deps = step.get("dependsOn", [])
            if not isinstance(deps, list):
                errors.append(f"{prefix}dependsOn deve ser uma lista de IDs.")

            budget = step.get("budgetSeconds", 30)
            if not isinstance(budget, (int, float)) or budget <= 0 or budget > 86400:
                errors.append(f"{prefix}budgetSeconds deve estar entre 1 e 86400.")

        # Validação de integridade referencial das dependências
        for step_id, step in by_id.items():
            for dep in step.get("dependsOn", []):
                if dep not in by_id:
                    errors.append(f"Etapa '{step_id}': dependência desconhecida '{dep}'.")
                if dep == step_id:
                    errors.append(f"Etapa '{step_id}': autorreferência cíclica.")

        # Detecção de ciclos via ordenação topológica (DFS com 2 conjuntos)
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def has_cycle(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited or node_id not in by_id:
                return False

            visiting.add(node_id)
            for dep in by_id[node_id].get("dependsOn", []):
                if has_cycle(dep):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        for node_id in by_id:
            if has_cycle(node_id):
                errors.append("Ciclo de dependência infinito detectado no plano de execução.")
                break

        if errors:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary=f"Plano reprovado com {len(errors)} inconsistências estruturais.",
                details={"errors": errors, "total_steps": len(steps)},
            )

        return GateResult(
            gate_name=self.name,
            semaphore=Semaphore.GREEN,
            passed=True,
            summary=f"DAG válido: {len(steps)} etapas acíclicas orquestradas com sucesso.",
            details={"total_steps": len(steps), "roles": list(set(s.get("role") for s in steps))},
        )

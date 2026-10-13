"""Gate 3: Policy & Rule Compliance Gate.

Valida se decisões técnicas, parâmetros ou patches de código estão em conformidade
com as regras de negócio ativas registradas em vault/rules/ (ex: RULE-001).
"""
from typing import Any, Dict, List
from core.gates.base import BaseGate, GateResult, Semaphore
from core import evidence


class RuleComplianceGate(BaseGate):
    name: str = "gate_3_rule_compliance"

    def __init__(self):
        try:
            self.definitions = evidence.load_definitions()
        except Exception:
            self.definitions = None

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        """Avalia conformidade contra regras de negócio.

        Payload esperado:
        {
            "action": "shipment_emission" | "database_mutation" | ...,
            "parameters": {"nfe_key": "3523...", ...},
            "rules_checked": ["RULE-001"]
        }
        """
        if not self.definitions or self.definitions.errors:
            # Fallback se não conseguir carregar o diretório de regras
            errs = self.definitions.errors if self.definitions else ["Definições indisponíveis"]
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.YELLOW,
                passed=False,
                summary="Aviso: Definições de regras de negócio com advertências de carga.",
                details={"errors": errs},
            )

        rules_checked = payload.get("rules_checked", [])
        params = payload.get("parameters", {})
        violations: List[str] = []

        # Verificação específica de regras conhecidas da holding
        if "RULE-001" in rules_checked or payload.get("action") == "shipment_emission":
            # RULE-001: Emissão exige chave NF-e real de 44 dígitos
            nfe_key = str(params.get("nfe_key", "")).strip()
            env = str(params.get("environment", "production")).lower()

            if env in ("production", "prod"):
                if not nfe_key or len(nfe_key) != 44 or not nfe_key.isdigit():
                    violations.append(
                        "Violação da RULE-001: Emissão logística em produção exige chave NF-e válida de 44 dígitos numéricos."
                    )

        # Checa se as regras citadas existem no catálogo oficial
        unknown_rules = [r for r in rules_checked if r not in self.definitions.rules]
        if unknown_rules:
            violations.append(f"Regras desconhecidas no catálogo formal: {', '.join(unknown_rules)}.")

        if violations:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary=f"Reprovado: {len(violations)} violações de regras de negócio identificadas.",
                details={"violations": violations},
            )

        return GateResult(
            gate_name=self.name,
            semaphore=Semaphore.GREEN,
            passed=True,
            summary=f"Conformidade atestada com as regras de negócio ativas ({len(rules_checked)} regras validadas).",
            details={"rules": rules_checked},
        )

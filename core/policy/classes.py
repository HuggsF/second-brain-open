"""Classe de risco de cada ferramenta."""
from enum import Enum
from typing import Dict


class ToolClass(str, Enum):
    READ = "READ"
    WRITE_LOCAL = "WRITE_LOCAL"
    PROD_READ = "PROD_READ"
    PROD_MUTATING = "PROD_MUTATING"


TOOL_CLASSES: Dict[str, ToolClass] = {
    "search_knowledge_base": ToolClass.READ,
    "get_adr": ToolClass.READ,
    "get_brain_status": ToolClass.READ,
    "list_rules": ToolClass.READ,
    "get_rule_evidence": ToolClass.READ,
    "get_system_architecture": ToolClass.READ,
    "read_vault_file": ToolClass.READ,
    "record_test_execution": ToolClass.WRITE_LOCAL,
    "run_safe_command": ToolClass.PROD_READ,
}

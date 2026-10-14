"""
Tool Executor — adaptador fino entre o Orquestrador e o corretor.

A política (core.policy), as implementações (core.tools) e o rastro ficam no
corretor (core.broker); aqui só se repassa a chamada com a identidade do agente.
"""
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import broker


async def execute(tool_name: str, *, identity: str = "agent:manager", task_id: Optional[str] = None,
                  approved: bool = False, **kwargs) -> dict:
    """Executa uma ferramenta pelo nome, via corretor."""
    return await broker.call(identity, tool_name, kwargs, task_id, approved=approved)

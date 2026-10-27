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


async def run_tool(tool: object, args: object, *, identity: str, task_id: Optional[str] = None,
                   approved: bool = False, persona_id: Optional[str] = None,
                   task_text: str = "") -> dict:
    """Repassa ao corretor sem espalhar args: tipos inválidos viram DENY lá, não TypeError aqui."""
    return await broker.call(identity, tool, args, task_id, approved=approved,
                             persona_id=persona_id, task_text=task_text)

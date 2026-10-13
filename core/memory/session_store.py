"""Memória efêmera de sessão (Short-Term Memory).

Isolada estritamente por mission_id ou task_id para evitar contaminação
cruzada entre execuções ou agentes concorrentes.
"""
from typing import Any, Dict, List, Optional
import datetime


class SessionMemoryStore:
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}

    def append(self, session_id: str, record: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        entry = {
            **record,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._sessions[session_id].append(entry)

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._sessions.get(session_id, []))

    def purge_session(self, session_id: str) -> int:
        """Purga a memória de uma sessão específica sem afetar outras."""
        count = len(self._sessions.get(session_id, []))
        if session_id in self._sessions:
            del self._sessions[session_id]
        return count

    def purge_all(self) -> int:
        """Purga todas as memórias efêmeras em execução."""
        total = sum(len(v) for v in self._sessions.values())
        self._sessions.clear()
        return total

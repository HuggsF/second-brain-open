"""Utilitário de purga e sanitização de memória.

Garante limpeza de memórias temporárias e quarentena sem risco de afetar
a base de conhecimento permanente em vault/.
"""
from pathlib import Path
from typing import Dict, Any

from config import settings
from core.memory.session_store import SessionMemoryStore
from core.memory.quarantine_store import QuarantineStore


class MemoryPurger:
    def __init__(self, session_store: SessionMemoryStore = None, quarantine_store: QuarantineStore = None):
        self.session_store = session_store or SessionMemoryStore()
        self.quarantine_store = quarantine_store or QuarantineStore()

    def purge_all_transient(self) -> Dict[str, int]:
        """Purga todas as memórias efêmeras e quarentena com segurança absoluta."""
        sessions_purged = self.session_store.purge_all()
        quarantine_purged = self.quarantine_store.purge_quarantine()

        return {
            "sessions_purged": sessions_purged,
            "quarantine_purged": quarantine_purged,
            "vault_preserved": True,
        }

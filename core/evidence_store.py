"""Local store of playbook executions (the dynamic half of the evidence tree).

SQLite in WAL mode with a 5 s busy timeout, so several MCP processes can record at once.
It keeps references and short summaries only, never request or response payloads.
"""
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from config import settings
from core import tracing

EVIDENCE_DB: Path = settings.base_dir / ".runtime" / "evidence.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions(
    id INTEGER PRIMARY KEY,
    playbook_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    result TEXT NOT NULL,
    environment TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    summary TEXT NOT NULL,
    trace_id TEXT,
    task_label TEXT,
    source TEXT NOT NULL,
    recorded_by TEXT NOT NULL,
    import_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS executions_playbook_ts ON executions(playbook_id, ts);
"""

_COLUMNS = ("playbook_id", "ts", "result", "environment", "evidence_ref", "summary",
            "trace_id", "task_label", "source", "recorded_by", "import_key")


class EvidenceStoreError(Exception):
    """The evidence database could not be opened or used. The message is safe to show."""


class EvidenceStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else EVIDENCE_DB  # EVIDENCE_DB is read now, so tests can patch it
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
        except sqlite3.DatabaseError as exc:
            raise self._error(exc) from exc
        finally:
            conn.close()

    def _error(self, exc: Exception) -> EvidenceStoreError:
        return EvidenceStoreError(f"evidence database unavailable ({self.path.name}): {exc}")

    def _connect(self) -> sqlite3.Connection:
        conn: Optional[sqlite3.Connection] = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except (sqlite3.DatabaseError, OSError) as exc:
            if conn is not None:
                conn.close()  # do not leak the handle on the error path (it locks the file on Windows)
            raise self._error(exc) from exc

    def record(
        self,
        *,
        playbook_id: str,
        result: str,
        environment: str,
        evidence_ref: str,
        summary: str,
        source: str,
        recorded_by: str,
        trace_id: Optional[str] = None,
        task_label: Optional[str] = None,
        ts: Optional[str] = None,
        import_key: Optional[str] = None,
    ) -> Optional[int]:
        """Insert one execution. Returns its id, or None when `import_key` was already imported."""
        values = dict(playbook_id=playbook_id, ts=ts or tracing.now_iso(), result=result,
                      environment=environment, evidence_ref=evidence_ref, summary=summary,
                      trace_id=trace_id, task_label=task_label, source=source,
                      recorded_by=recorded_by, import_key=import_key)
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    f"INSERT INTO executions({', '.join(_COLUMNS)}) VALUES({', '.join('?' for _ in _COLUMNS)})",
                    [values[c] for c in _COLUMNS],
                )
            return cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "import_key" in str(exc):
                return None
            raise self._error(exc) from exc
        except sqlite3.DatabaseError as exc:
            raise self._error(exc) from exc
        finally:
            conn.close()

    def latest(self, playbook_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM executions WHERE playbook_id = ? ORDER BY ts DESC, id DESC LIMIT ?",
                (playbook_id, max(1, int(limit))),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.DatabaseError as exc:
            raise self._error(exc) from exc
        finally:
            conn.close()

    def all_playbook_ids(self) -> Set[str]:
        conn = self._connect()
        try:
            return {r[0] for r in conn.execute("SELECT DISTINCT playbook_id FROM executions")}
        except sqlite3.DatabaseError as exc:
            raise self._error(exc) from exc
        finally:
            conn.close()

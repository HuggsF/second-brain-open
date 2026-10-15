# Em tests/test_worm_fsync.py (novo)
from unittest import mock
from pathlib import Path
import tempfile
from core.audit.worm_audit import WORMAuditLog

def test_fsync_called_after_write():
    with tempfile.TemporaryDirectory() as tmp:
        log = WORMAuditLog(Path(tmp) / "audit.jsonl")
        with mock.patch("os.fsync") as mock_fsync:
            log.append(
                event_type="test.event",
                actor="test-actor",
                trace_id="trace-123",
                payload={"key": "value"},
            )
            assert mock_fsync.called
            # Verificar que foi chamado com um file descriptor (int)
            assert isinstance(mock_fsync.call_args[0][0], int)

def test_hash_chain_still_valid_after_fsync():
    with tempfile.TemporaryDirectory() as tmp:
        log = WORMAuditLog(Path(tmp) / "audit.jsonl")
        log.append("ev1", "actor", "t1", {"a": 1})
        log.append("ev2", "actor", "t2", {"b": 2})
        from core.audit.worm_audit import verify_chain
        records = log.read_all()
        result = verify_chain(records)
        assert result.valid is True

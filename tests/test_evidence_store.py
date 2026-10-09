import contextlib
import multiprocessing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import evidence_store
from core.evidence_store import EvidenceStore, EvidenceStoreError

FIELDS = dict(playbook_id="PB-001", result="pass", environment="local",
              evidence_ref="vault/systems/x.md:47", summary="26 scenarios approved",
              source="reported", recorded_by="mcp")


def _worker(path, tag, count):
    store = EvidenceStore(Path(path))
    for i in range(count):
        store.record(**{**FIELDS, "summary": f"{tag}-{i}"})


class TestEvidenceStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ".runtime" / "evidence.db"

    def rows(self):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            return db.execute("SELECT COUNT(*) FROM executions").fetchone()[0]

    def test_record_and_read_back_all_fields(self):
        store = EvidenceStore(self.path)
        new_id = store.record(**FIELDS, trace_id="a" * 32, task_label="DEM-12", ts="2026-10-09T12:00:00.000-03:00")
        (row,) = store.latest("PB-001")
        self.assertEqual(row["id"], new_id)
        for key, value in FIELDS.items():
            self.assertEqual(row[key], value)
        self.assertEqual((row["trace_id"], row["task_label"], row["ts"]), ("a" * 32, "DEM-12", "2026-10-09T12:00:00.000-03:00"))
        self.assertIsNone(row["import_key"])

    def test_ts_defaults_to_now_and_trace_is_optional(self):
        store = EvidenceStore(self.path)
        store.record(**FIELDS)
        (row,) = store.latest("PB-001")
        self.assertRegex(row["ts"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertIsNone(row["trace_id"])

    def test_latest_is_newest_first_and_honours_limit(self):
        store = EvidenceStore(self.path)
        for n in range(4):
            store.record(**{**FIELDS, "summary": f"run {n}"}, ts=f"2026-10-09T12:00:0{n}.000-03:00")
        store.record(**{**FIELDS, "playbook_id": "PB-002"})
        got = store.latest("PB-001", limit=2)
        self.assertEqual([r["summary"] for r in got], ["run 3", "run 2"])
        self.assertEqual(len(store.latest("PB-002")), 1)
        self.assertEqual(store.latest("PB-404"), [])

    def test_import_key_makes_import_idempotent(self):
        store = EvidenceStore(self.path)
        first = store.record(**{**FIELDS, "source": "imported"}, import_key="k1")
        second = store.record(**{**FIELDS, "source": "imported"}, import_key="k1")
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.rows(), 1)

    def test_all_playbook_ids(self):
        store = EvidenceStore(self.path)
        self.assertEqual(store.all_playbook_ids(), set())
        store.record(**FIELDS)
        store.record(**{**FIELDS, "playbook_id": "PB-002"})
        self.assertEqual(store.all_playbook_ids(), {"PB-001", "PB-002"})

    def test_wal_and_busy_timeout_are_set(self):
        store = EvidenceStore(self.path)
        store.record(**FIELDS)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        conn = store._connect()
        try:
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
        finally:
            conn.close()

    def test_path_is_resolved_at_call_time(self):
        with mock.patch.object(evidence_store, "EVIDENCE_DB", self.path):
            EvidenceStore().record(**FIELDS)
        self.assertTrue(self.path.exists())

    def test_two_processes_recording_at_once(self):
        EvidenceStore(self.path)  # create the schema once, as the servers do on first use
        ctx = multiprocessing.get_context("spawn")
        workers = [ctx.Process(target=_worker, args=(str(self.path), tag, 25)) for tag in ("a", "b")]
        for w in workers:
            w.start()
        for w in workers:
            w.join(120)
        self.assertEqual([w.exitcode for w in workers], [0, 0])
        self.assertEqual(self.rows(), 50)

    def test_corrupt_file_raises_a_clear_error(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("this is not a sqlite database " * 20, encoding="utf-8")
        with self.assertRaises(EvidenceStoreError) as ctx:
            EvidenceStore(self.path).latest("PB-001")
        self.assertNotIsInstance(ctx.exception, sqlite3.DatabaseError)
        self.assertIn("evidence", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()

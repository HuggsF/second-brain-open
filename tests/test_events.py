import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import events, tracing


def _lines(path):
    return path.read_bytes().decode("utf-8").splitlines()


class EventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "events.jsonl"

    def test_record_never_contains_payload(self):
        env = {"id": "1", "task": "summarize", "payload": {"text": "segredo-123"}}
        self.assertTrue(events.record(env, self.path))
        raw = self.path.read_bytes().decode("utf-8")
        self.assertNotIn("segredo-123", raw)
        row = json.loads(raw.splitlines()[0])
        self.assertNotIn("payload", row)
        self.assertEqual(
            row["payload_bytes"],
            len(json.dumps(env["payload"], ensure_ascii=False).encode("utf-8")),
        )
        self.assertIn("payload", env)

    def test_classify_keeps_labels_and_validate_keeps_valid(self):
        labels = {"type": "adr", "team": "ops", "tags": ["tag-do-texto-secreta"]}
        c = events.redact({"task": "classify", "payload": {"labels": labels, "text": "x"}})
        self.assertEqual(c["labels"], {"type": "adr", "team": "ops"})
        self.assertNotIn("tag-do-texto-secreta", json.dumps(c))
        self.assertNotIn("payload", c)
        self.assertNotIn("labels", events.redact({"task": "classify", "payload": {"labels": ["a"]}}))
        v = events.redact({"task": "validate", "payload": {"valid": False, "text": "x"}})
        self.assertIs(v["valid"], False)
        other = events.redact({"task": "summarize"})
        self.assertEqual(other["payload_bytes"], 0)

    def test_rotation_at_max_bytes(self):
        with mock.patch.object(tracing, "MAX_BYTES", 200):
            for i in range(10):
                events.record({"id": str(i), "task": "t", "payload": {"a": "x" * 50}}, self.path)
        self.assertTrue(self.path.with_name("events.1.jsonl").exists())

    def test_unwritable_target_returns_false_and_counts(self):
        with mock.patch.object(events, "FAILURES", 0):
            self.assertFalse(events.record({"task": "t"}, Path(self.tmp.name)))
            self.assertEqual(events.failures(), 1)


if __name__ == "__main__":
    unittest.main()

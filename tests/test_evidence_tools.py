import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastmcp import Client

from core import evidence, evidence_store, tracing
from core.evidence_store import EvidenceStore
from mcp_servers import brain_mcp
from tests.test_evidence import PLAYBOOK, RULE, write_note

TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
GOOD = dict(playbook_id="PB-001", result="pass", summary="26 scenarios approved",
            evidence_ref="vault/x.md:47", environment="local")


class TestEvidenceTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.vault = root / "vault"
        write_note(self.vault, "rules", "RULE-001-x.md", RULE)
        write_note(self.vault, "playbooks", "PB-001-x.md", PLAYBOOK)
        self.db = root / ".runtime" / "evidence.db"
        self.log = root / ".runtime" / "trace-log.jsonl"
        for patcher in (
            mock.patch.object(evidence, "_vault_dir", return_value=self.vault),
            mock.patch.object(evidence_store, "EVIDENCE_DB", self.db),
            mock.patch.object(tracing, "TRACE_LOG", self.log),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, tool, args=None):
        async def run():
            async with Client(brain_mcp.mcp) as client:
                return await client.call_tool(tool, args or {})

        return asyncio.run(run()).data

    def test_record_test_execution_links_the_trace(self):
        out = self.call("record_test_execution", GOOD)
        self.assertEqual(set(out), {"recorded", "trace_id"})
        call_record = next(r for r in tracing.read_recent(10, self.log) if r["tool"] == "record_test_execution")
        self.assertEqual(out["trace_id"], call_record["trace_id"])
        (row,) = EvidenceStore().latest("PB-001")
        self.assertEqual((row["id"], row["trace_id"]), (out["recorded"], out["trace_id"]))
        self.assertEqual((row["recorded_by"], row["source"]), ("mcp", "reported"))

    def test_task_id_groups_two_recordings_in_one_trace(self):
        self.call("record_test_execution", {**GOOD, "task_id": "DEM-12"})
        self.call("record_test_execution", {**GOOD, "summary": "second run", "task_id": "DEM-12"})
        first, second = EvidenceStore().latest("PB-001", 2)
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertEqual((first["task_label"], second["task_label"]), ("DEM-12", "DEM-12"))

    def test_each_validation_error_is_returned_not_raised(self):
        for over, needle in (({"result": "maybe"}, "result"), ({"playbook_id": "PB-404"}, "PB-404"),
                             ({"environment": "prod"}, "environment")):
            out = self.call("record_test_execution", {**GOOD, **over})
            self.assertIn(needle, out["error"])
        self.assertEqual(EvidenceStore().latest("PB-001"), [])

    def test_sensitive_value_is_refused_and_never_reaches_the_response_or_the_logs(self):
        out = self.call("record_test_execution", {**GOOD, "summary": f"token {TOKEN} and cpf 123.456.789-09"})
        self.assertIn("sensitive", out["error"])
        self.assertNotIn(TOKEN, str(out))
        self.assertEqual(EvidenceStore().latest("PB-001"), [])
        raw = self.log.read_text(encoding="utf-8")
        self.assertNotIn(TOKEN, raw)
        self.assertNotIn("123.456.789-09", raw)

    def test_get_rule_evidence_and_list_rules_shapes(self):
        self.call("record_test_execution", GOOD)
        out = self.call("get_rule_evidence", {"rule_id": "RULE-001"})
        self.assertEqual(out["rule"]["id"], "RULE-001")
        (playbook,) = out["playbooks"]
        self.assertEqual((playbook["id"], len(playbook["executions"])), ("PB-001", 1))
        rows = self.call("list_rules")
        self.assertEqual((rows[0]["id"], rows[0]["playbooks"], rows[0]["latest"]["result"]), ("RULE-001", ["PB-001"], "pass"))
        self.assertIn("RULE-001", self.call("get_rule_evidence", {"rule_id": "RULE-404"})["error"])

    def test_rule_without_executions_says_no_evidence_yet(self):
        out = self.call("get_rule_evidence", {"rule_id": "RULE-001"})
        self.assertEqual(out["playbooks"][0]["note"], "sem evidência ainda")
        self.assertEqual(out["playbooks"][0]["executions"], [])

    def test_corrupt_evidence_db_returns_error_dict_and_server_keeps_working(self):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.db.write_text("this is not a sqlite database " * 20, encoding="utf-8")
        for tool, args in (("record_test_execution", GOOD), ("get_rule_evidence", {"rule_id": "RULE-001"})):
            out = self.call(tool, args)
            self.assertIn("evidence", out["error"].lower())
        self.assertEqual(self.call("list_rules")[0]["error"][:8], "evidence")
        self.assertIsInstance(self.call("get_system_architecture", {"system_name": "does-not-exist"}), str)

    def test_record_does_not_write_to_the_vault(self):
        def snapshot():
            return {p.relative_to(self.vault).as_posix(): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}

        before = snapshot()
        self.call("record_test_execution", GOOD)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()

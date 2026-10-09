import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

import cli as cli_module
from core.evidence import Playbook
from core.evidence_store import EvidenceStore
from tests.test_evidence import make_defs


class TestEvidenceCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = EvidenceStore(root / "evidence.db")
        self.defs = make_defs()
        self.defs.playbooks["PB-002"] = Playbook("PB-002", "Sem execucoes", "active", ["RULE-001"], "hml", [], "playbooks/q.md")
        self.seed = root / "seed.json"
        self.runner = CliRunner()
        patcher = mock.patch.object(cli_module, "_evidence_context", side_effect=lambda: (self.defs, self.store, self.seed))
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args):
        return self.runner.invoke(cli_module.cli, ["evidence", *args])

    def record(self, summary="ok", result="pass", pb="PB-001"):
        self.store.record(playbook_id=pb, result=result, environment="local", evidence_ref="vault/x.md:1", summary=summary,
                          source="reported", recorded_by="mcp", trace_id="a" * 32, ts="2026-10-09T12:00:00.000-03:00")

    def test_evidence_without_argument_lists_rules(self):
        result = self.run_cli()
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("RULE-001", result.output)
        self.assertIn("sem evidência ainda", result.output)
        self.record()
        self.assertIn("pass", self.run_cli().output)

    def test_evidence_with_rule_prints_playbooks_and_latest_executions(self):
        self.record("x" * 200)
        result = self.run_cli("RULE-001")
        self.assertEqual(result.exit_code, 0, result.output)
        for needle in ("RULE-001", "PB-001", "PB-002", "pass", "reported", "aaaaaaaa"):
            self.assertIn(needle, result.output)
        self.assertIn("x" * 120, result.output)
        self.assertNotIn("x" * 121, result.output)

    def test_rule_without_executions_prints_sem_evidencia_ainda_and_no_pass(self):
        result = self.run_cli("RULE-001")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("sem evidência ainda", result.output)
        self.assertNotIn("pass", result.output)

    def test_unknown_rule_exits_1_with_known_ids(self):
        result = self.run_cli("RULE-404")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("RULE-001", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_lint_exit_codes(self):
        clean = self.run_cli("--lint")
        self.assertEqual(clean.exit_code, 0, clean.output)
        self.assertIn("sem problemas", clean.output)
        self.defs.errors.append("rules/a.md: invalid id 'RULE-1'")
        broken = self.run_cli("--lint")
        self.assertEqual(broken.exit_code, 1)
        self.assertIn("rules/a.md: invalid id 'RULE-1'", broken.output)

    def test_import_seed_twice_adds_one_row(self):
        self.seed.write_text(json.dumps([{
            "import_key": "k1", "playbook_id": "PB-001", "ts": "2026-10-08T00:00:00-03:00", "result": "pass",
            "environment": "local", "evidence_ref": "vault/x.md:47", "summary": "26 scenarios approved"}]), encoding="utf-8")
        first = self.run_cli("--import-seed")
        second = self.run_cli("--import-seed")
        self.assertEqual((first.exit_code, second.exit_code), (0, 0), first.output + second.output)
        self.assertIn("1", first.output)
        self.assertEqual(len(self.store.latest("PB-001", 10)), 1)

    def test_import_seed_with_a_bad_file_exits_1_without_traceback(self):
        self.seed.write_text("{not json", encoding="utf-8")
        result = self.run_cli("--import-seed")
        self.assertEqual(result.exit_code, 1)
        self.assertNotIn("Traceback", result.output)

    def test_id_together_with_lint_is_a_usage_error(self):
        self.assertNotEqual(self.run_cli("RULE-001", "--lint").exit_code, 0)
        self.assertNotEqual(self.run_cli("--lint", "--import-seed").exit_code, 0)


if __name__ == "__main__":
    unittest.main()

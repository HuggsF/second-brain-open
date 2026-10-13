import json
import re
import tempfile
import unittest
from pathlib import Path

from config import settings
from core import evidence
from core.evidence_store import EvidenceStore

SEED = settings.base_dir / "evidence" / "seed-executions.json"
HUB_NOTE = "vault/systems/protecoes-processamento-emissao-hub.md"


class TestRealSeed(unittest.TestCase):
    def test_real_definitions_load_without_errors_and_lint_clean(self):
        defs = evidence.load_definitions(settings.vault_dir)
        self.assertEqual(defs.errors, [])
        self.assertEqual(sorted(defs.rules), ["RULE-001", "RULE-002"])
        self.assertEqual(sorted(defs.playbooks), ["PB-001", "PB-002", "PB-003", "PB-004", "PB-005", "PB-006", "PB-007"])
        self.assertEqual(evidence.lint(defs), [])
        self.assertEqual(defs.playbooks["PB-001"].validates, ["RULE-001", "RULE-002"])
        self.assertEqual(defs.playbooks["PB-002"].environment, "hml")

    def test_every_rule_source_line_exists(self):
        defs = evidence.load_definitions(settings.vault_dir)
        for rule in defs.rules.values():
            path, line = re.fullmatch(r"(.+):(\d+)", rule.source).groups()
            lines = (settings.base_dir / path).read_text(encoding="utf-8-sig").splitlines()
            self.assertGreaterEqual(len(lines), int(line), rule.id)

    def test_rule_sources_point_at_the_sentences_they_summarise(self):
        defs = evidence.load_definitions(settings.vault_dir)
        note = (settings.base_dir / HUB_NOTE).read_text(encoding="utf-8-sig").splitlines()
        self.assertIn("chave de 44 dígitos", note[int(defs.rules["RULE-001"].source.rsplit(":", 1)[1]) - 1])
        self.assertIn("sem chamar ERP, J&T ou WMS", note[int(defs.rules["RULE-002"].source.rsplit(":", 1)[1]) - 1])

    def test_seed_imports_once_and_only_pb001_has_an_execution(self):
        defs = evidence.load_definitions(settings.vault_dir)
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp) / "evidence.db")
            self.assertEqual(evidence.import_seed(defs, store, SEED), (1, 0))
            self.assertEqual(evidence.import_seed(defs, store, SEED), (0, 1))
            (row,) = store.latest("PB-001")
            self.assertEqual((row["result"], row["source"], row["recorded_by"]), ("pass", "imported", "cli"))
            self.assertEqual((store.latest("PB-002"), store.latest("PB-003")), ([], []))
            out = evidence.rule_evidence(defs, store, "RULE-001")
            by_id = {p["id"]: p for p in out["playbooks"]}
            self.assertEqual(by_id["PB-002"]["note"], "sem evidência ainda")
            self.assertNotIn("note", by_id["PB-001"])

    def test_seed_reference_points_at_the_documented_result(self):
        (entry,) = json.loads(SEED.read_text(encoding="utf-8"))
        path, line = entry["evidence_ref"].rsplit(":", 1)
        text = (settings.base_dir / path).read_text(encoding="utf-8-sig").splitlines()[int(line) - 1]
        self.assertIn("36 cenários JavaScript", text)
        self.assertIn("3 testes Python", text)
        self.assertIn(":57", entry["evidence_ref"])
        self.assertIn("36", entry["summary"])
        note = (settings.base_dir / path).read_text(encoding="utf-8-sig").splitlines()
        self.assertIn("PR #13", note[int(line) - 2] + note[int(line) - 3])  # the cited line sits under the PR #13 update heading

    def test_all_new_notes_use_crlf(self):
        notes = sorted((settings.vault_dir / "rules").glob("*.md")) + sorted((settings.vault_dir / "playbooks").glob("*.md"))
        self.assertEqual(len(notes), 9)
        for note in notes:
            data = note.read_bytes()
            self.assertTrue(data.count(b"\r\n") > 0, note.name)
            self.assertEqual(data.replace(b"\r\n", b"").count(b"\n"), 0, note.name)


if __name__ == "__main__":
    unittest.main()

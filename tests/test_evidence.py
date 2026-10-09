import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from core import evidence

RULE = {"id": "RULE-001", "title": "Emissao exige NF real", "status": "active",
        "source": "vault/systems/x.md:45", "domain": "logistica"}
PLAYBOOK = {"id": "PB-001", "title": "Suite do Hub", "status": "active", "validates": ["RULE-001"],
            "environment": "local", "targets": ["hub"]}


def write_note(root, folder, name, front, body="# Titulo\n\nTexto.\n", raw=None):
    path = Path(root) / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    else:
        path.write_text("---\n" + yaml.safe_dump(front, allow_unicode=True) + "---\n" + body, encoding="utf-8")
    return path


class TestLoadDefinitions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_valid_rule_and_playbook_load(self):
        write_note(self.root, "rules", "RULE-001-x.md", RULE)
        write_note(self.root, "playbooks", "PB-001-x.md", PLAYBOOK)
        defs = evidence.load_definitions(self.root)
        self.assertEqual(defs.errors, [])
        rule, playbook = defs.rules["RULE-001"], defs.playbooks["PB-001"]
        self.assertEqual((rule.title, rule.status, rule.source, rule.domain), ("Emissao exige NF real", "active", "vault/systems/x.md:45", "logistica"))
        self.assertEqual(rule.path, "rules/RULE-001-x.md")
        self.assertEqual(playbook.validates, ["RULE-001"])
        self.assertEqual((playbook.environment, playbook.targets, playbook.path), ("local", ["hub"], "playbooks/PB-001-x.md"))

    def test_note_without_front_matter_is_an_error_and_skipped(self):
        write_note(self.root, "rules", "RULE-001-x.md", None, raw="# So titulo\n\nSem cabecalho.\n")
        defs = evidence.load_definitions(self.root)
        self.assertEqual(defs.rules, {})
        self.assertEqual(len(defs.errors), 1)
        self.assertIn("rules/RULE-001-x.md", defs.errors[0])

    def test_missing_required_field_is_an_error(self):
        front = {k: v for k, v in RULE.items() if k != "source"}
        write_note(self.root, "rules", "RULE-001-x.md", front)
        defs = evidence.load_definitions(self.root)
        self.assertEqual(defs.rules, {})
        self.assertTrue(any("source" in e and "rules/RULE-001-x.md" in e for e in defs.errors))

    def test_invalid_id_status_or_environment_is_an_error(self):
        write_note(self.root, "rules", "a.md", {**RULE, "id": "RULE-1"})
        write_note(self.root, "rules", "b.md", {**RULE, "id": "RULE-002", "status": "done"})
        write_note(self.root, "playbooks", "c.md", {**PLAYBOOK, "environment": "prod"})
        defs = evidence.load_definitions(self.root)
        self.assertEqual((defs.rules, defs.playbooks), ({}, {}))
        text = "\n".join(defs.errors)
        for needle in ("RULE-1", "status", "environment"):
            self.assertIn(needle, text)

    def test_duplicate_id_is_an_error(self):
        write_note(self.root, "rules", "RULE-001-a.md", RULE)
        write_note(self.root, "rules", "RULE-001-b.md", {**RULE, "title": "Outra"})
        defs = evidence.load_definitions(self.root)
        self.assertEqual(len(defs.rules), 1)
        self.assertEqual(defs.rules["RULE-001"].title, "Emissao exige NF real")  # first note in name order wins
        self.assertTrue(any("duplicate" in e.lower() and "RULE-001-b.md" in e for e in defs.errors))

    def test_playbook_validates_must_be_a_non_empty_list(self):
        write_note(self.root, "playbooks", "a.md", {**PLAYBOOK, "validates": []})
        write_note(self.root, "playbooks", "b.md", {**PLAYBOOK, "id": "PB-002", "validates": "RULE-001"})
        defs = evidence.load_definitions(self.root)
        self.assertEqual(defs.playbooks, {})
        self.assertEqual(len(defs.errors), 2)

    def test_malformed_yaml_does_not_raise(self):
        write_note(self.root, "rules", "RULE-001-x.md", None, raw="---\nid: [unclosed\n  : :\n---\n# T\n")
        defs = evidence.load_definitions(self.root)
        self.assertEqual(defs.rules, {})
        self.assertEqual(len(defs.errors), 1)

    def test_front_matter_that_is_not_a_mapping_is_an_error(self):
        write_note(self.root, "rules", "RULE-001-x.md", None, raw="---\n- just\n- a list\n---\n# T\n")
        defs = evidence.load_definitions(self.root)
        self.assertEqual((defs.rules, len(defs.errors)), ({}, 1))

    def test_missing_folders_give_empty_definitions(self):
        defs = evidence.load_definitions(self.root)
        self.assertEqual((defs.rules, defs.playbooks, defs.errors), ({}, {}, []))

    def test_default_vault_dir_is_resolved_at_call_time(self):
        write_note(self.root, "rules", "RULE-001-x.md", RULE)
        with mock.patch.object(evidence, "_vault_dir", return_value=self.root):
            self.assertIn("RULE-001", evidence.load_definitions().rules)

    def test_bom_and_crlf_notes_load(self):
        text = "---\r\n" + yaml.safe_dump(RULE, allow_unicode=True).replace("\n", "\r\n") + "---\r\n# T\r\n"
        path = self.root / "rules" / "RULE-001-x.md"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
        self.assertEqual(evidence.load_definitions(self.root).errors, [])


if __name__ == "__main__":
    unittest.main()

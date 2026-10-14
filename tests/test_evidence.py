import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from core import evidence
from core.evidence import Definitions, Playbook, Rule
from core.evidence_store import EvidenceStore

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

    def test_playbook_kind_defaults_to_runbook_and_ttl_168(self):
        write_note(self.root, "playbooks", "PB-001-x.md", PLAYBOOK)
        playbook = evidence.load_definitions(self.root).playbooks["PB-001"]
        self.assertEqual((playbook.kind, playbook.ttl_hours), ("runbook", 168))

    def test_playbook_kind_test_and_ttl_parsed(self):
        write_note(self.root, "playbooks", "PB-001-x.md", {**PLAYBOOK, "kind": "test", "ttl_hours": 24})
        defs = evidence.load_definitions(self.root)
        self.assertEqual(defs.errors, [])
        self.assertEqual((defs.playbooks["PB-001"].kind, defs.playbooks["PB-001"].ttl_hours), ("test", 24))

    def test_invalid_kind_and_ttl_are_lint_errors_not_exceptions(self):
        for over in ({"kind": "smoke"}, {"ttl_hours": 0}, {"ttl_hours": -1}, {"ttl_hours": True},
                     {"ttl_hours": "x"}, {"ttl_hours": 9000}, {"ttl_hours": 1.5}):
            with self.subTest(over=over):
                write_note(self.root, "playbooks", "PB-001-x.md", {**PLAYBOOK, **over})
                defs = evidence.load_definitions(self.root)
                self.assertEqual(defs.playbooks, {})
                self.assertEqual(len(defs.errors), 1)
                self.assertIn("playbooks/PB-001-x.md", defs.errors[0])
                self.assertRegex(defs.errors[0], "kind|ttl_hours")

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


def make_defs(rule_status="active", playbook_status="active", validates=("RULE-001",)):
    rules = {"RULE-001": Rule("RULE-001", "Emissao exige NF", rule_status, "vault/x.md:1", "hub", "rules/r.md")}
    playbooks = {"PB-001": Playbook("PB-001", "Suite do Hub", playbook_status, list(validates), "local", ["hub"], "playbooks/p.md")}
    return Definitions(rules, playbooks, [])


OK_ARGS = dict(playbook_id="PB-001", result="pass", summary="26 scenarios approved", evidence_ref="vault/x.md:47", environment="local")
TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


class TestValidate(unittest.TestCase):
    def check(self, **over):
        return evidence.validate_execution(make_defs(), **{**OK_ARGS, **over})

    def test_happy_path_returns_clean_fields(self):
        clean, error = self.check()
        self.assertIsNone(error)
        self.assertEqual((clean["summary"], clean["evidence_ref"]), ("26 scenarios approved", "vault/x.md:47"))

    def test_validate_execution_commit_sha_and_run_id(self):
        clean, error = self.check()
        self.assertEqual((clean["commit_sha"], clean["run_id"]), (None, None))
        for sha, run in (("abc1234", "run-123"), ("a" * 40, "gha:98765"), ("", "")):
            clean, error = self.check(commit_sha=sha, run_id=run)
            self.assertIsNone(error)
            self.assertEqual((clean["commit_sha"], clean["run_id"]), (sha or None, run or None))
        for over in ({"commit_sha": "xyz"}, {"commit_sha": "a" * 41}, {"commit_sha": "ABC1234"},
                     {"run_id": "run id com espaço"}, {"run_id": "r" * 81},
                     {"run_id": "123.456.789-09"}, {"commit_sha": "123.456.789-09"}):
            clean, error = self.check(**over)
            self.assertIsNone(clean, over)
            self.assertTrue(error)
            self.assertNotIn("123.456.789-09", error)

    def test_unknown_and_retired_playbook(self):
        self.assertIn("PB-404", self.check(playbook_id="PB-404")[1])
        clean, error = evidence.validate_execution(make_defs(playbook_status="retired"), **OK_ARGS)
        self.assertIsNone(clean)
        self.assertIn("retired", error)

    def test_bad_result_and_environment(self):
        self.assertIn("result", self.check(result="maybe")[1])
        self.assertIn("environment", self.check(environment="prod")[1])
        self.assertIn("environment", self.check(environment="hml")[1])  # the playbook is local, hml does not match
        defs = make_defs()
        defs.playbooks["PB-001"].environment = "hml"
        self.assertIsNone(evidence.validate_execution(defs, **{**OK_ARGS, "environment": "local"})[1])  # local is always allowed

    def test_summary_length_limits(self):
        self.assertIn("summary", self.check(summary="")[1])
        self.assertIn("summary", self.check(summary="x" * 501)[1])
        self.assertIsNone(self.check(summary="x" * 500)[1])

    def test_evidence_ref_shapes(self):
        for good in ("vault/x.md:47", "vault/x.md:45-61", "https://github.com/o/r/pull/1", "DEM-12"):
            self.assertIsNone(self.check(evidence_ref=good)[1], good)
        for bad in ("", "just words", "C:\\x.md:3", "x" * 301):
            self.assertIn("evidence_ref", self.check(evidence_ref=bad)[1], bad)

    def test_control_characters_are_removed(self):
        clean, error = self.check(summary="a\x00b\x07c\nd\te", evidence_ref="vault/x\x00.md:3")
        self.assertIsNone(error)
        self.assertEqual(clean["summary"], "abc d e")
        self.assertEqual(clean["evidence_ref"], "vault/x.md:3")

    def test_sensitive_data_is_refused_without_echoing_it(self):
        cases = [("token", TOKEN), ("cpf", "123.456.789-09"), ("cpf", "12345678909"), ("nf-key", "3" * 44)]
        for name, value in cases:
            for field in ("summary", "evidence_ref"):
                over = {field: f"x {value} y" if field == "summary" else f"https://h.example/{value}"}
                clean, error = self.check(**over)
                self.assertIsNone(clean, (name, field))
                self.assertIn(name, error)
                self.assertIn(field, error)
                self.assertNotIn(value, error)

    def test_printed_formats_and_hidden_characters_are_refused(self):
        groups = " ".join(["3333"] * 11)
        for name, value in (("cpf", "123 456 789 09"), ("cpf", "123-456-789-09"), ("cpf", "123\x00456\x00789\x0009"),
                            ("cpf", "123.4​56.789-09"), ("nf-key", groups), ("nf-key", ".".join(["3333"] * 11))):
            clean, error = self.check(summary=f"x {value} y")
            self.assertIsNone(clean, value)
            self.assertIn(name, error)
            self.assertNotRegex(error, r"456|3333")

    def test_ordinary_summaries_are_not_refused(self):
        for text in ("npm test: 36 JavaScript scenarios and 3 Python tests approved (PR #13, 2026-10-08)",
                     "26 scenarios approved, CI Node 18/20", "ran 2026-10-09 12:00, 5 jobs pending"):
            self.assertIsNone(self.check(summary=text)[1], text)

    def test_private_key_header_is_refused(self):
        self.assertIn("token", self.check(summary="-----BEGIN PRIVATE KEY-----")[1])


class TestQueries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = EvidenceStore(Path(self.tmp.name) / "evidence.db")
        self.defs = make_defs()
        self.defs.playbooks["PB-002"] = Playbook("PB-002", "Sem execucoes", "active", ["RULE-001"], "hml", [], "playbooks/q.md")

    def record(self, n=1, pb="PB-001", result="pass"):
        for i in range(n):
            self.store.record(playbook_id=pb, result=result, environment="local", evidence_ref="vault/x.md:1",
                              summary=f"run {i}", source="reported", recorded_by="mcp", ts=f"2026-10-09T12:00:{i:02d}.000-03:00")

    def test_rule_evidence_with_and_without_executions(self):
        self.record(2)
        out = evidence.rule_evidence(self.defs, self.store, "RULE-001")
        self.assertEqual(out["rule"]["id"], "RULE-001")
        by_id = {p["id"]: p for p in out["playbooks"]}
        self.assertEqual([e["summary"] for e in by_id["PB-001"]["executions"]], ["run 1", "run 0"])
        self.assertNotIn("note", by_id["PB-001"])
        self.assertEqual(by_id["PB-002"]["executions"], [])
        self.assertEqual(by_id["PB-002"]["note"], "sem evidência ainda")

    def test_unknown_rule_lists_known_ids(self):
        out = evidence.rule_evidence(self.defs, self.store, "RULE-404")
        self.assertIn("RULE-001", out["error"])

    def test_limit_is_clamped(self):
        self.record(25)
        out = evidence.rule_evidence(self.defs, self.store, "RULE-001", limit=999)
        self.assertEqual(len(next(p for p in out["playbooks"] if p["id"] == "PB-001")["executions"]), 20)
        out = evidence.rule_evidence(self.defs, self.store, "RULE-001", limit=0)
        self.assertEqual(len(next(p for p in out["playbooks"] if p["id"] == "PB-001")["executions"]), 1)

    def test_list_rules_shape_and_per_playbook_latest(self):
        (row,) = evidence.list_rules(self.defs, self.store)
        self.assertEqual((row["id"], row["status"], row["playbooks"]), ("RULE-001", "active", ["PB-001", "PB-002"]))
        self.assertEqual(row["playbook_latest"], {"PB-001": None, "PB-002": None})
        self.assertEqual(row["state"], "sem evidência ainda")
        self.record(2, result="fail")
        (row,) = evidence.list_rules(self.defs, self.store)
        latest = row["playbook_latest"]["PB-001"]
        self.assertEqual((latest["result"], latest["environment"], latest["source"]), ("fail", "local", "reported"))
        self.assertIsNone(row["playbook_latest"]["PB-002"])

    def test_state_shows_a_failing_playbook_even_if_another_passed_later(self):
        self.record(1, pb="PB-002", result="fail")
        self.store.record(playbook_id="PB-001", result="pass", environment="local", evidence_ref="vault/x.md:1", summary="later pass",
                          source="reported", recorded_by="mcp", ts="2026-10-09T13:00:00.000-03:00")
        self.assertEqual(evidence.list_rules(self.defs, self.store)[0]["state"], "falha")

    def test_state_is_partial_until_every_active_playbook_passes(self):
        self.record(1, pb="PB-001", result="pass")
        self.assertEqual(evidence.list_rules(self.defs, self.store)[0]["state"], "parcial")
        self.record(1, pb="PB-002", result="pass")
        self.assertEqual(evidence.list_rules(self.defs, self.store)[0]["state"], "ok")

    def test_state_ignores_playbooks_that_are_not_active(self):
        self.defs.playbooks["PB-002"].status = "draft"
        self.record(1, pb="PB-001", result="pass")
        self.assertEqual(evidence.list_rules(self.defs, self.store)[0]["state"], "ok")

    def test_rule_without_playbooks_says_no_evidence_yet(self):
        self.defs.playbooks.clear()
        (row,) = evidence.list_rules(self.defs, self.store)
        self.assertEqual((row["playbooks"], row["state"]), ([], "sem evidência ainda"))


class TestLint(unittest.TestCase):
    def test_clean_definitions_have_no_problems(self):
        self.assertEqual(evidence.lint(make_defs()), [])

    def test_loader_errors_are_reported(self):
        defs = make_defs()
        defs.errors.append("rules/a.md: invalid id 'RULE-1'")
        self.assertEqual(evidence.lint(defs), ["rules/a.md: invalid id 'RULE-1'"])

    def test_playbook_validating_an_unknown_rule(self):
        problems = evidence.lint(make_defs(validates=("RULE-001", "RULE-009")))
        self.assertTrue(any("PB-001" in p and "RULE-009" in p for p in problems))

    def test_active_rule_without_active_playbook(self):
        problems = evidence.lint(make_defs(playbook_status="draft"))
        self.assertTrue(any("RULE-001" in p and "active playbook" in p for p in problems))

    def test_active_playbook_validating_a_retired_rule(self):
        problems = evidence.lint(make_defs(rule_status="retired"))
        self.assertTrue(any("PB-001" in p and "retired" in p and "RULE-001" in p for p in problems))

    def test_execution_for_an_unknown_playbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(Path(tmp) / "evidence.db")
            store.record(playbook_id="PB-404", result="pass", environment="local", evidence_ref="vault/x.md:1",
                         summary="s", source="reported", recorded_by="mcp")
            problems = evidence.lint(make_defs(), store)
        self.assertTrue(any("PB-404" in p for p in problems))


class TestImportSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = EvidenceStore(self.root / "evidence.db")
        self.defs = make_defs()
        self.seed = self.root / "seed.json"

    def row(self, key="k1", pb="PB-001", **over):
        return {"import_key": key, "playbook_id": pb, "ts": "2026-10-08T00:00:00-03:00", "result": "pass",
                "environment": "local", "evidence_ref": "vault/x.md:47", "summary": "26 scenarios approved", **over}

    def test_twice_adds_once_then_skips(self):
        self.seed.write_text(json.dumps([self.row()]), encoding="utf-8")
        self.assertEqual(evidence.import_seed(self.defs, self.store, self.seed), (1, 0))
        self.assertEqual(evidence.import_seed(self.defs, self.store, self.seed), (0, 1))
        (stored,) = self.store.latest("PB-001")
        self.assertEqual((stored["source"], stored["recorded_by"], stored["import_key"]), ("imported", "cli", "k1"))

    def test_unknown_playbook_or_invalid_row_is_skipped_without_raising(self):
        rows = [self.row("k1", pb="PB-404"), self.row("k2", result="maybe"), self.row("k3")]
        self.seed.write_text(json.dumps(rows), encoding="utf-8")
        self.assertEqual(evidence.import_seed(self.defs, self.store, self.seed), (1, 2))

    def test_malformed_seed_file_raises_a_clear_error(self):
        self.seed.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            evidence.import_seed(self.defs, self.store, self.seed)
        self.seed.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            evidence.import_seed(self.defs, self.store, self.seed)


if __name__ == "__main__":
    unittest.main()

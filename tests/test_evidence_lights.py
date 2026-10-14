import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import evidence
from core.evidence import Definitions, Playbook, Rule
from core.evidence_store import EvidenceStore

NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


def pb(pid, environment="local", kind="test", status="active", ttl=168, validates=("RULE-001",)):
    return Playbook(pid, f"Playbook {pid}", status, list(validates), environment, [], f"playbooks/{pid}.md",
                    kind=kind, ttl_hours=ttl)


def make_defs(*playbooks):
    rules = {"RULE-001": Rule("RULE-001", "Emissao exige NF", "active", "vault/x.md:1", "hub", "rules/r.md")}
    return Definitions(rules, {p.id: p for p in playbooks}, [])


class LightBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = EvidenceStore(Path(self.tmp.name) / "evidence.db")

    def record(self, pid, result="pass", environment="local", hours_ago=1, ts=None, store=None, summary="resumo"):
        stamp = ts if ts is not None else (NOW - timedelta(hours=hours_ago)).isoformat()
        (store or self.store).record(
            playbook_id=pid, result=result, environment=environment, evidence_ref="vault/x.md:1",
            summary=summary, source="reported", recorded_by="mcp", ts=stamp)

    def light(self, *playbooks):
        return evidence.rule_light(list(playbooks), self.store, now=NOW)


class TestRuleLight(LightBase):
    def test_grey_without_any_test_execution(self):
        result = self.light(pb("PB-001"))
        self.assertEqual(result["light"], "grey")
        self.assertEqual(result["test_playbooks"], ["PB-001"])

    def test_grey_when_rule_has_no_test_playbook(self):
        result = self.light(pb("PB-001", kind="runbook"))
        self.assertEqual((result["light"], result["test_playbooks"], result["test_environments"]), ("grey", [], []))
        self.assertIn("playbook de teste", result["reason"])

    def test_green_requires_every_counted_playbook(self):
        a, b = pb("PB-001", "local"), pb("PB-002", "hml")
        self.record("PB-001", "pass", "local")
        partial = self.light(a, b)
        self.assertEqual(partial["light"], "yellow")
        self.assertIn("PB-002", partial["reason"])
        self.assertIn("hml", partial["reason"])
        self.record("PB-002", "pass", "hml")
        full = self.light(a, b)
        self.assertEqual(full["light"], "green")
        self.assertEqual((full["test_playbooks"], full["test_environments"]), (["PB-001", "PB-002"], ["hml", "local"]))

    def test_fail_or_error_in_any_counted_playbook_is_red(self):
        a, b = pb("PB-001", "local"), pb("PB-002", "hml")
        self.record("PB-002", "pass", "hml", hours_ago=5)
        self.record("PB-001", "fail", "local", hours_ago=1)
        result = self.light(a, b)
        self.assertEqual(result["light"], "red")
        self.assertIn("PB-001", result["reason"])
        self.assertIn("2026-10-14", result["reason"])
        self.record("PB-001", "error", "local", hours_ago=0)
        self.assertEqual(self.light(a, b)["light"], "red")

    def test_red_beats_grey_and_yellow(self):
        a, b, c = pb("PB-001", "local"), pb("PB-002", "hml"), pb("PB-003", "hml")
        self.record("PB-001", "pass", "local")
        self.record("PB-002", "fail", "hml")
        result = self.light(a, b, c)  # PB-003 has no execution (yellow), PB-001 is fine
        self.assertEqual(result["light"], "red")
        self.assertIn("PB-002", result["reason"])

    def test_latest_pass_after_older_fail_is_not_red(self):
        self.record("PB-001", "fail", hours_ago=10)
        self.record("PB-001", "pass", hours_ago=2)
        self.assertEqual(self.light(pb("PB-001"))["light"], "green")

    def test_runbook_and_retired_playbooks_never_count(self):
        for other in ("PB-002", "PB-003", "PB-004"):
            self.record(other, "fail")
        self.record("PB-001", "pass")
        result = self.light(pb("PB-001"), pb("PB-002", kind="runbook"), pb("PB-003", status="retired"),
                            pb("PB-004", status="draft"))
        self.assertEqual((result["light"], result["test_playbooks"]), ("green", ["PB-001"]))

    def test_expired_pass_is_yellow(self):
        self.record("PB-001", "pass", hours_ago=169)
        result = self.light(pb("PB-001"))
        self.assertEqual(result["light"], "yellow")
        self.assertIn("PB-001", result["reason"])
        self.assertIn("168", result["reason"])

    def test_pass_inside_ttl_is_green(self):
        self.record("PB-001", "pass", hours_ago=167)
        self.assertEqual(self.light(pb("PB-001"))["light"], "green")

    def test_own_ttl_is_respected(self):
        self.record("PB-001", "pass", hours_ago=30)
        result = self.light(pb("PB-001", ttl=24))
        self.assertEqual(result["light"], "yellow")
        self.assertIn("24", result["reason"])

    def test_local_run_does_not_satisfy_hml_playbook(self):
        self.record("PB-002", "pass", "local")
        for env in ("hml", "production"):
            with self.subTest(env=env):
                result = self.light(pb("PB-002", env))
                self.assertEqual(result["light"], "yellow")
                self.assertIn(env, result["reason"])
                self.assertIn("PB-002", result["reason"])

    def test_recent_local_fail_still_makes_hml_playbook_red(self):
        self.record("PB-002", "pass", "hml", hours_ago=5)
        self.record("PB-002", "fail", "local", hours_ago=1)
        self.assertEqual(self.light(pb("PB-002", "hml"))["light"], "red")

    def test_newer_local_pass_does_not_replace_own_environment_pass(self):
        self.record("PB-002", "pass", "hml", hours_ago=200)
        self.record("PB-002", "pass", "local", hours_ago=1)
        self.assertEqual(self.light(pb("PB-002", "hml"))["light"], "yellow")

    def test_skipped_after_old_pass_is_yellow(self):
        self.record("PB-001", "pass", hours_ago=10)
        self.record("PB-001", "skipped", hours_ago=1)
        result = self.light(pb("PB-001"))
        self.assertEqual(result["light"], "yellow")
        self.assertIn("PB-001", result["reason"])

    def test_unparseable_or_future_ts_is_never_a_fresh_pass(self):
        for index, bad in enumerate(("not-a-date", (NOW + timedelta(minutes=10)).isoformat())):
            with self.subTest(ts=bad):
                store = EvidenceStore(Path(self.tmp.name) / f"bad{index}.db")
                self.record("PB-001", "pass", ts=bad, store=store)
                result = evidence.rule_light([pb("PB-001")], store, now=NOW)
                self.assertEqual(result["light"], "yellow")
                self.assertIn("PB-001", result["reason"])

    def test_zulu_and_naive_timestamps_are_accepted(self):
        self.record("PB-001", "pass", ts="2026-10-14T10:00:00Z")
        self.assertEqual(self.light(pb("PB-001"))["light"], "green")
        self.record("PB-002", "pass", ts="2026-10-14T10:00:00")
        self.assertEqual(self.light(pb("PB-002"))["light"], "green")

    def test_ts_within_five_minutes_in_the_future_is_tolerated(self):
        self.record("PB-001", "pass", ts=(NOW + timedelta(minutes=4)).isoformat())
        self.assertEqual(self.light(pb("PB-001"))["light"], "green")

    def test_reason_never_contains_the_summary(self):
        self.record("PB-001", "fail", ts=NOW.isoformat(), summary="segredo-no-resumo")
        self.assertNotIn("segredo", self.light(pb("PB-001"))["reason"])


class TestOwnEnvironmentRules(LightBase):
    def test_newer_local_pass_does_not_hide_hml_failure(self):
        self.record("PB-002", "fail", "hml", hours_ago=5)
        self.record("PB-002", "pass", "local", hours_ago=1)
        result = self.light(pb("PB-002", "hml"))
        self.assertEqual(result["light"], "red")
        self.assertIn("PB-002", result["reason"])
        self.assertIn("hml", result["reason"])
        self.assertIn("2026-10-14", result["reason"])

    def test_own_environment_error_is_red_with_environment_in_reason(self):
        self.record("PB-002", "error", "hml", hours_ago=5)
        self.record("PB-002", "pass", "local", hours_ago=1)
        result = self.light(pb("PB-002", "hml"))
        self.assertEqual(result["light"], "red")
        self.assertIn("hml", result["reason"])

    def test_many_newer_local_runs_do_not_hide_a_fresh_hml_pass(self):
        self.record("PB-002", "pass", "hml", hours_ago=10)
        for minutes in range(60):
            self.record("PB-002", "pass", "local", ts=(NOW - timedelta(minutes=minutes)).isoformat())
        self.assertEqual(self.light(pb("PB-002", "hml"))["light"], "green")

    def test_many_newer_local_passes_do_not_hide_an_hml_failure(self):
        self.record("PB-002", "fail", "hml", hours_ago=10)
        for minutes in range(60):
            self.record("PB-002", "pass", "local", ts=(NOW - timedelta(minutes=minutes)).isoformat())
        result = self.light(pb("PB-002", "hml"))
        self.assertEqual(result["light"], "red")
        self.assertIn("hml", result["reason"])

    def test_skipped_run_in_another_environment_does_not_decide(self):
        self.record("PB-002", "pass", "hml", hours_ago=1)
        self.record("PB-002", "skipped", "local", ts=(NOW - timedelta(minutes=10)).isoformat())
        self.assertEqual(self.light(pb("PB-002", "hml"))["light"], "green")

    def test_own_environment_skipped_after_older_own_pass_is_yellow(self):
        self.record("PB-002", "pass", "hml", hours_ago=10)
        self.record("PB-002", "skipped", "hml", hours_ago=1)
        result = self.light(pb("PB-002", "hml"))
        self.assertEqual(result["light"], "yellow")
        self.assertIn("PB-002", result["reason"])

    def test_invalid_ts_row_among_fetched_rows_keeps_playbook_yellow(self):
        # Conservative choice: one unusable row makes the playbook yellow even with a fresh valid pass.
        self.record("PB-001", "pass", hours_ago=1)
        self.record("PB-001", "pass", ts="not-a-date")
        result = self.light(pb("PB-001"))
        self.assertEqual(result["light"], "yellow")
        self.assertIn("PB-001", result["reason"])


class TestStoreEnvironmentFilter(LightBase):
    def test_latest_filters_by_environment_and_default_is_unchanged(self):
        self.record("PB-001", "pass", "hml", hours_ago=3)
        self.record("PB-001", "pass", "local", hours_ago=1)
        self.assertEqual(len(self.store.latest("PB-001", 10)), 2)
        rows = self.store.latest("PB-001", 10, environment="hml")
        self.assertEqual([r["environment"] for r in rows], ["hml"])


class TestListRulesLights(LightBase):
    def test_existing_state_field_unchanged_and_light_fields_added(self):
        defs = make_defs(pb("PB-001", "local"), pb("PB-002", "hml"))
        rows = evidence.list_rules(defs, self.store, now=NOW)
        self.assertEqual(rows[0]["state"], "sem evidência ainda")
        self.assertEqual((rows[0]["light"], rows[0]["test_playbooks"]), ("grey", ["PB-001", "PB-002"]))
        self.assertIn("light_reason", rows[0])
        self.assertEqual(rows[0]["test_environments"], ["hml", "local"])
        self.record("PB-001", "pass")
        self.assertEqual(evidence.list_rules(defs, self.store, now=NOW)[0]["state"], "parcial")
        self.record("PB-002", "pass", "hml")
        row = evidence.list_rules(defs, self.store, now=NOW)[0]
        self.assertEqual((row["state"], row["light"]), ("ok", "green"))
        self.record("PB-002", "fail", "hml", hours_ago=0)
        row = evidence.list_rules(defs, self.store, now=NOW)[0]
        self.assertEqual((row["state"], row["light"]), ("falha", "red"))
        for key in ("id", "title", "status", "playbooks", "playbook_latest"):
            self.assertIn(key, row)

    def test_acceptance_rule_is_not_green_until_pb002_passes(self):
        defs = make_defs(pb("PB-001", "local"), pb("PB-002", "hml"))
        self.record("PB-001", "pass")
        self.assertNotEqual(evidence.list_rules(defs, self.store, now=NOW)[0]["light"], "green")
        self.record("PB-002", "pass", "hml")
        self.assertEqual(evidence.list_rules(defs, self.store, now=NOW)[0]["light"], "green")

    def test_rule_evidence_exposes_the_same_light(self):
        defs = make_defs(pb("PB-001", "local"))
        data = evidence.rule_evidence(defs, self.store, "RULE-001")
        self.assertEqual(data["light"], "grey")
        self.assertIn("light_reason", data)


class TestRealVaultSeed(LightBase):
    def test_seed_lights_for_rule_001_and_rule_002(self):
        defs = evidence.load_definitions()
        self.assertEqual(defs.errors, [])
        seed = Path(__file__).resolve().parent.parent / "evidence" / "seed-executions.json"
        evidence.import_seed(defs, self.store, seed)
        now = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        rows = {r["id"]: r for r in evidence.list_rules(defs, self.store, now=now)}
        # RULE-002 is validated only by PB-001 (kind test): the imported local pass is inside the 168 h TTL.
        self.assertEqual(rows["RULE-002"]["test_playbooks"], ["PB-001"])
        self.assertEqual(rows["RULE-002"]["light"], "green")
        # RULE-001 also needs PB-002 (hml), which has no execution yet.
        self.assertEqual(rows["RULE-001"]["test_playbooks"], ["PB-001", "PB-002"])
        self.assertEqual(rows["RULE-001"]["light"], "yellow")
        self.assertIn("PB-002", rows["RULE-001"]["light_reason"])
        # Past the TTL the seed pass no longer counts.
        later = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = {r["id"]: r for r in evidence.list_rules(defs, self.store, now=later)}
        self.assertEqual(rows["RULE-002"]["light"], "yellow")


if __name__ == "__main__":
    unittest.main()

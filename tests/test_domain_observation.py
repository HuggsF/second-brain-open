"""Testes do dominio de observacao (core/domain/observation).

- Paridade: project() em Python precisa reproduzir, caso a caso, o project() de
  dashboard/hub-topology.js (tests/fixtures/observation_golden.json, gerado por
  scripts/generate_observation_golden.js).
- Robustez: observacao ausente, parcial ou malformada nunca vira verde e nunca levanta excecao.
- detect_contradictions: luz verde de teste contra saude vermelha do ambiente observado.
- O dominio nao importa nada fora da biblioteca padrao e de core.domain.
"""
import ast
import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.domain.observation.entities import Contradiction, ObservationSnapshot, ServiceHealth
from core.domain.observation.projection import detect_contradictions, project

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "fixtures" / "observation_golden.json"
NOW = 1791540000.0
NODE_IDS = ("process", "internal", "external", "database")


def _golden_cases():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _sample(environment="production"):
    enabled = environment == "production"
    health = {"status": "ok", "environment": environment, "revision": "a" * 40,
              "emissionEnabled": enabled, "workerEnabled": enabled, "version": "1.0.0"}
    return {
        "at": datetime.fromtimestamp(NOW - 5, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "ok": True, "failure_count": 0, "failure_reasons": [],
        "warning_count": 0,
        "process": {"status": "online", "restarts": 2, "uptime": 1000, "memoryBytes": 100000},
        "internal": dict(health), "external": dict(health),
        "database": {"ok": True, "pending": 3, "processing": 0, "failed": 2, "errorsSinceDeploy": 0,
                     "automaticShops": 0, "rateLimitsSinceDeploy": 0, "terminalErrorsSinceDeploy": 0,
                     "logisticsReviewJobs": 0, "multipleVolumeReviewJobs": 0},
    }


def _snapshot(status, environment="production"):
    nodes = tuple(ServiceHealth(i, status, "x") for i in NODE_IDS)
    return ObservationSnapshot(environment, nodes, status, "x", False)


class ProjectionParityTest(unittest.TestCase):
    def test_golden_has_enough_cases(self):
        self.assertGreaterEqual(len(_golden_cases()), 14)

    def test_projection_matches_javascript_golden(self):
        for case in _golden_cases():
            with self.subTest(case=case["name"]):
                latest = copy.deepcopy(case["latest"])
                snapshot = project(case["environment"], latest, case["now"])
                expected = case["expected"]
                self.assertEqual(latest, case["latest"], "project() must not mutate its input")
                self.assertEqual(snapshot.environment, case["environment"])
                self.assertEqual(snapshot.status, expected["status"])
                self.assertEqual(snapshot.reason, expected["reason"])
                self.assertEqual(snapshot.stale, expected["stale"])
                self.assertEqual(
                    [(n.id, n.status, n.reason) for n in snapshot.nodes],
                    [(n["id"], n["status"], n["reason"]) for n in expected["nodes"]])

    def test_invalid_environment_is_a_caller_error(self):
        with self.assertRaises(ValueError):
            project("staging", None, NOW)


class ProjectionRobustnessTest(unittest.TestCase):
    def _assert_degraded(self, latest, environment="production", now=NOW):
        snapshot = project(environment, latest, now)
        self.assertEqual([n.id for n in snapshot.nodes], list(NODE_IDS))
        self.assertNotEqual(snapshot.status, "green")
        self.assertIn(snapshot.status, ("unknown", "yellow"))
        # A damaged aspect degrades only itself (as in the JS); the summary is never green.
        self.assertTrue(any(n.status in ("unknown", "yellow") for n in snapshot.nodes))
        for node in snapshot.nodes:
            self.assertIn(node.status, ("green", "unknown", "yellow"))
        return snapshot

    def test_missing_partial_or_malformed_observation_is_never_green_and_never_raises(self):
        def with_report(**changes):
            latest = {"environment": "production", "stale": False, "collection_failed": False,
                      "observation": {"id": 1, "collected_at": NOW - 5,
                                      "report": {"environment": "production", "ok": True,
                                                 "expected_sha": "a" * 40,
                                                 "snapshots": [_sample(), _sample()]}}}
            latest["observation"]["report"].update(changes)
            return latest

        table = [
            ("None", None),
            ("empty dict", {}),
            ("list", []),
            ("string", "oops"),
            ("number", 42),
            ("empty snapshots", {"observation": {"report": {"snapshots": []}}}),
            ("snapshots without environment", {"environment": "production",
                                               "observation": {"collected_at": NOW - 5,
                                                               "report": {"snapshots": []}}}),
            ("snapshots of size 1", with_report(snapshots=[_sample()])),
            ("snapshots of size 3", with_report(snapshots=[_sample(), _sample(), _sample()])),
            ("snapshots as dict", with_report(snapshots={"a": 1})),
            ("snapshots as string", with_report(snapshots="invalid")),
            ("snapshots with None", with_report(snapshots=[_sample(), None])),
            ("snapshots with ints", with_report(snapshots=[1, 2])),
            ("snapshot ok as string", with_report(snapshots=[dict(_sample(), ok="true"), _sample()])),
            ("report not a dict", {"environment": "production", "observation": {"report": [1]}}),
            ("observation not a dict", {"environment": "production", "observation": "x"}),
            ("report ok as string", with_report(ok="true")),
            ("process as string", with_report(snapshots=[dict(_sample(), process="online"), _sample()])),
            ("internal as list", with_report(snapshots=[dict(_sample(), internal=[1]), _sample()])),
            ("database as int", with_report(snapshots=[dict(_sample(), database=7), _sample()])),
            ("at as dict", with_report(snapshots=[dict(_sample(), at={}), _sample()])),
            ("at as bool", with_report(snapshots=[dict(_sample(), at=True), _sample()])),
            ("collected_at as bool", {**with_report(), "observation": {
                "collected_at": True, "report": with_report()["observation"]["report"]}}),
            ("collected_at as string", {**with_report(), "observation": {
                "collected_at": "1791540000", "report": with_report()["observation"]["report"]}}),
            ("expected_sha as int", with_report(expected_sha=5)),
        ]
        for name, latest in table:
            with self.subTest(case=name):
                self._assert_degraded(latest)

    def test_stale_flag_with_wrong_type_is_unknown(self):
        latest = {"environment": "production", "stale": "yes", "collection_failed": False,
                  "observation": {"collected_at": NOW - 5,
                                  "report": {"environment": "production", "ok": True,
                                             "expected_sha": "a" * 40,
                                             "snapshots": [_sample(), _sample()]}}}
        snapshot = self._assert_degraded(latest)
        self.assertEqual(snapshot.status, "unknown")
        latest["stale"] = False
        latest["collection_failed"] = "no"
        self.assertEqual(self._assert_degraded(latest).status, "unknown")

    def test_bad_now_seconds_never_raises_nor_greens(self):
        latest = {"environment": "production", "observation": {
            "collected_at": NOW - 5, "report": {"environment": "production", "ok": True,
                                                "expected_sha": "a" * 40,
                                                "snapshots": [_sample(), _sample()]}}}
        for now in (None, "x", float("nan"), float("inf"), -1, True):
            with self.subTest(now=now):
                self.assertEqual(self._assert_degraded(latest, now=now).status, "unknown")

    def test_deeply_odd_values_degrade_instead_of_raising(self):
        class Weird:
            def __eq__(self, other):
                raise RuntimeError("boom")

        latest = {"environment": "production", "observation": {
            "collected_at": NOW - 5, "report": {"environment": "production", "ok": True,
                                                "expected_sha": "a" * 40,
                                                "snapshots": [_sample(), dict(_sample(), process=Weird())]}}}
        self._assert_degraded(latest)


class DetectContradictionsTest(unittest.TestCase):
    def test_detect_contradictions_only_when_light_green_and_health_red(self):
        rule = {"id": "r1", "light": "green", "test_environments": ["production"]}
        snapshots = {"production": _snapshot("red"), "hml": _snapshot("green", "hml")}
        found = detect_contradictions([rule], snapshots)
        self.assertEqual(len(found), 1)
        item = found[0]
        self.assertIsInstance(item, Contradiction)
        self.assertEqual((item.rule_id, item.environment, item.light, item.health),
                         ("r1", "production", "green", "red"))
        self.assertIn("produção", item.reason)
        self.assertIn("vermelha", item.reason)

        no_match = [
            ({"id": "r2", "light": "green", "test_environments": ["production"]},
             {"production": _snapshot("green")}),
            ({"id": "r3", "light": "yellow", "test_environments": ["production"]},
             {"production": _snapshot("red")}),
            ({"id": "r4", "light": "green", "test_environments": ["production"]},
             {"production": _snapshot("yellow")}),
            ({"id": "r5", "light": "green", "test_environments": ["production"]},
             {"production": _snapshot("unknown")}),
            ({"id": "r6", "light": "green", "test_environments": ["local"]},
             {"production": _snapshot("red"), "hml": _snapshot("red", "hml")}),
            ({"id": "r7", "light": "green", "test_environments": ["hml"]},
             {"production": _snapshot("red")}),
            ({"id": "r8", "light": "red", "test_environments": ["production", "hml"]},
             {"production": _snapshot("red"), "hml": _snapshot("red", "hml")}),
            ({"id": "r9", "light": "grey", "test_environments": ["production"]},
             {"production": _snapshot("red")}),
        ]
        for rule_row, snaps in no_match:
            with self.subTest(rule=rule_row["id"]):
                self.assertEqual(detect_contradictions([rule_row], snaps), [])

    def test_one_per_rule_and_environment_in_deterministic_order(self):
        snapshots = {"hml": _snapshot("red", "hml"), "production": _snapshot("red")}
        rules = [
            {"id": "b", "light": "green", "test_environments": ["production", "hml"]},
            {"id": "a", "light": "green", "test_environments": ["hml", "production"]},
        ]
        found = detect_contradictions(rules, snapshots)
        self.assertEqual([(c.rule_id, c.environment) for c in found],
                         [("a", "hml"), ("a", "production"), ("b", "hml"), ("b", "production")])
        self.assertEqual(found, detect_contradictions(list(reversed(rules)), snapshots))

    def test_odd_rule_rows_and_snapshots_never_raise_nor_contradict(self):
        snapshots = {"production": _snapshot("red"), "hml": "not a snapshot"}
        rules = [
            None, "x", 5, [], {},
            {"id": "a"},
            {"id": "b", "light": "green"},
            {"id": "c", "light": "green", "test_environments": "production"},
            {"id": "d", "light": "green", "test_environments": None},
            {"id": "e", "light": "green", "test_environments": [None, 3, ["production"]]},
            {"id": 7, "light": "green", "test_environments": ["production"]},
            {"light": "green", "test_environments": ["production"]},
            {"id": "f", "light": ["green"], "test_environments": ["production"]},
            {"id": "g", "light": "green", "test_environments": ["hml"]},
        ]
        self.assertEqual(detect_contradictions(rules, snapshots), [])
        self.assertEqual(detect_contradictions(None, snapshots), [])
        self.assertEqual(detect_contradictions(rules, None), [])
        self.assertEqual(detect_contradictions([], {}), [])


class DomainPurityTest(unittest.TestCase):
    def test_domain_has_no_io_imports(self):
        import sys
        stdlib = set(sys.stdlib_module_names)
        files = sorted((ROOT / "core" / "domain" / "observation").glob("*.py"))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    top = module.split(".")[0]
                    allowed = top in stdlib or module == "core.domain" or module.startswith("core.domain.")
                    self.assertTrue(allowed, f"{path.name} imports {module}")


if __name__ == "__main__":
    unittest.main()

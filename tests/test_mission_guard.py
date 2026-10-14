"""Testes de core/mission_guard: portões rodam antes da missão."""
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.orchestrator import DEFAULT_STEPS, MISSION_PATTERNS
from core import tracing
from core.mission_guard import build_plan, check_mission


def _step(agent="researcher", tool="search_knowledge_base"):
    return {"agent": agent, "tool": tool, "input": {}, "bubble": "x"}


class _FakePipeline:
    def __init__(self, semaphore=None, exc=None):
        self.semaphore, self.exc = semaphore, exc

    def run_all(self, payload):
        if self.exc:
            raise self.exc
        return {"all_passed": self.semaphore == "GREEN", "global_semaphore": self.semaphore, "gate_results": []}


class TestMissionGuard(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        tmp = stack.enter_context(tempfile.TemporaryDirectory())
        self.log = Path(tmp) / "trace.jsonl"
        stack.enter_context(mock.patch.object(tracing, "TRACE_LOG", self.log))

    def rows(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_valid_pattern_is_green_and_proceeds(self):
        steps = next(p["steps"] for p in MISSION_PATTERNS if "diagnosticar" in p["keywords"])
        result = check_mission(steps, 1)
        self.assertEqual(result["action"], "proceed")
        self.assertEqual(result["semaphore"], "GREEN")

    def test_every_builtin_pattern_proceeds(self):
        for steps in [p["steps"] for p in MISSION_PATTERNS] + [DEFAULT_STEPS]:
            self.assertEqual(check_mission(steps, 1)["action"], "proceed", steps)

    def test_unknown_tool_is_red_and_blocks(self):
        result = check_mission([_step(tool="drop_table")], 1)
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["semaphore"], "RED")

    def test_unknown_role_is_red(self):
        result = check_mission([_step(agent="hacker")], 1)
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["semaphore"], "RED")

    def test_malformed_steps_block_without_raising(self):
        for bad in ([{}], ["x"], [None], [{"agent": 1, "tool": []}], [{"agent": {}, "tool": {}}], []):
            with self.subTest(steps=bad):
                self.assertEqual(check_mission(bad, 1)["action"], "block")
        self.assertEqual(check_mission(None, 1)["action"], "block")

    def test_build_plan_chains_steps(self):
        plan = build_plan([_step(), _step("coder", "get_brain_status")])
        self.assertEqual(plan["version"], 1)
        self.assertEqual([s["id"] for s in plan["steps"]], ["s1", "s2"])
        self.assertEqual(plan["steps"][0]["dependsOn"], [])
        self.assertEqual(plan["steps"][1]["dependsOn"], ["s1"])
        self.assertEqual(plan["steps"][1]["role"], "coder")
        self.assertEqual(plan["steps"][1]["tools"], ["get_brain_status"])
        self.assertEqual(plan["steps"][1]["budgetSeconds"], 30)

    def test_yellow_requires_approval(self):
        result = check_mission([_step()], 1, pipeline=_FakePipeline("YELLOW"))
        self.assertEqual(result["action"], "approval")
        self.assertEqual(result["semaphore"], "YELLOW")

    def test_pipeline_exception_blocks(self):
        result = check_mission([_step()], 1, pipeline=_FakePipeline(exc=RuntimeError("boom")))
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["semaphore"], "RED")

    def test_gate_result_is_recorded_in_trace(self):
        check_mission([_step()], 9)
        row = next(r for r in self.rows() if r["event"] == "gate.pipeline")
        self.assertEqual(row["task_label"], "M9")
        self.assertEqual(row["caller"], "agent:manager")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["args"]["action"], "proceed")

    def test_record_status_per_action(self):
        for sem, status in (("YELLOW", "escalated"), ("RED", "refused")):
            self.log.unlink(missing_ok=True)
            check_mission([_step()], 3, pipeline=_FakePipeline(sem))
            self.assertEqual(self.rows()[0]["status"], status)


if __name__ == "__main__":
    unittest.main()

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


class _SpyPipeline:
    """Registra o payload recebido para inspeção nos testes."""

    def __init__(self):
        self.last_payload = None

    def run_all(self, payload):
        self.last_payload = payload
        return {"all_passed": True, "global_semaphore": "GREEN", "gate_results": []}


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


class TestBuiltinStepsPassPolicy(unittest.TestCase):
    def test_every_builtin_step_is_approved_by_policy(self):
        from core.policy import Decision, decide, make_identity
        groups = [p["steps"] for p in MISSION_PATTERNS] + [DEFAULT_STEPS]
        denied = []
        for steps in groups:
            for step in steps:
                verdict = decide(make_identity(step["agent"]), step["tool"], step["input"])
                if verdict.decision is not Decision.APPROVE:
                    denied.append((step["agent"], step["tool"], verdict.decision.value, verdict.reason.value))
        self.assertEqual(denied, [])


if __name__ == "__main__":
    unittest.main()


class TestReconnectedQualityGates(unittest.TestCase):
    """Sprint 0 — reconexão dos 4 Quality Gates (ADR-022).

    Verifica que check_mission() propaga corretamente os payloads opcionais
    (grounding_payload, rule_payload, idempotency_payload) para o pipeline,
    ativando os Gates 1, 3 e 4 além do DAG Gate (Gate 2).
    """

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        tmp = stack.enter_context(tempfile.TemporaryDirectory())
        self.log = Path(tmp) / "trace.jsonl"
        stack.enter_context(mock.patch.object(tracing, "TRACE_LOG", self.log))

    # ── Testes de propagação de payload ──

    def test_grounding_payload_is_merged_into_pipeline(self):
        """Gate 1: chaves 'citations' e 'claims' devem chegar ao pipeline."""
        spy = _SpyPipeline()
        grounding = {"citations": [{"document": "test.md", "sha256": "abc"}], "claims": "teste"}
        check_mission([_step()], 1, pipeline=spy, grounding_payload=grounding)
        self.assertIn("citations", spy.last_payload)
        self.assertIn("claims", spy.last_payload)
        self.assertEqual(spy.last_payload["citations"], grounding["citations"])

    def test_rule_payload_is_merged_into_pipeline(self):
        """Gate 3: chaves 'action', 'parameters', 'rules_checked' devem chegar ao pipeline."""
        spy = _SpyPipeline()
        rule = {"action": "shipment_emission", "parameters": {"nfe_key": "1234"}, "rules_checked": ["RULE-001"]}
        check_mission([_step()], 1, pipeline=spy, rule_payload=rule)
        self.assertIn("rules_checked", spy.last_payload)
        self.assertIn("parameters", spy.last_payload)
        self.assertEqual(spy.last_payload["action"], "shipment_emission")

    def test_idempotency_payload_is_merged_into_pipeline(self):
        """Gate 4: chaves 'is_mutation', 'idempotency_key', etc. devem chegar ao pipeline."""
        spy = _SpyPipeline()
        idem = {
            "is_mutation": True,
            "idempotency_key": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "batch_trace_id": "e74f9d2a1b8c0e5a4f7e2d1c9a8b7e6d",
            "lock_ttl_seconds": 15,
        }
        check_mission([_step()], 1, pipeline=spy, idempotency_payload=idem)
        self.assertIn("is_mutation", spy.last_payload)
        self.assertIn("idempotency_key", spy.last_payload)

    # ── Testes de retrocompatibilidade ──

    def test_backward_compat_no_extra_payloads(self):
        """Sem payloads extras, apenas a chave 'plan' deve estar no payload (DAG Gate)."""
        spy = _SpyPipeline()
        check_mission([_step()], 1, pipeline=spy)
        self.assertIn("plan", spy.last_payload)
        self.assertNotIn("citations", spy.last_payload)
        self.assertNotIn("rules_checked", spy.last_payload)
        self.assertNotIn("is_mutation", spy.last_payload)

    # ── Testes de composição parcial ──

    def test_all_four_payloads_merged_together(self):
        """Todos os 4 gates alimentados simultaneamente."""
        spy = _SpyPipeline()
        check_mission(
            [_step()], 1, pipeline=spy,
            grounding_payload={"citations": [{"document": "x.md"}]},
            rule_payload={"rules_checked": ["RULE-001"], "parameters": {}},
            idempotency_payload={"is_mutation": True, "idempotency_key": "test-key-1234567890ab"},
        )
        payload = spy.last_payload
        # Todas as chaves dos 4 gates presentes
        self.assertIn("plan", payload)        # Gate 2 (DAG)
        self.assertIn("citations", payload)   # Gate 1 (Grounding)
        self.assertIn("rules_checked", payload)  # Gate 3 (Rule)
        self.assertIn("is_mutation", payload)    # Gate 4 (Idempotency)

    def test_none_payloads_are_ignored(self):
        """Payloads None devem ser ignorados sem erro."""
        spy = _SpyPipeline()
        check_mission(
            [_step()], 1, pipeline=spy,
            grounding_payload=None,
            rule_payload=None,
            idempotency_payload=None,
        )
        self.assertIn("plan", spy.last_payload)
        self.assertNotIn("citations", spy.last_payload)


class TestReconnectedGatesIntegration(unittest.TestCase):
    """Testes de integração: executa os gates reais (não mocks)."""

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        tmp = stack.enter_context(tempfile.TemporaryDirectory())
        self.log = Path(tmp) / "trace.jsonl"
        stack.enter_context(mock.patch.object(tracing, "TRACE_LOG", self.log))

    def test_idempotency_gate_blocks_mission_without_key(self):
        """Gate 4: mutação sem chave de idempotência deve bloquear a missão (RED)."""
        result = check_mission(
            [_step()], 1,
            idempotency_payload={"is_mutation": True, "operation": "POST /test"},
        )
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["semaphore"], "RED")
        # Verifica que o gate de idempotência aparece nos resultados
        gate_names = [g["gate_name"] for g in result["gate_results"]]
        self.assertIn("gate_4_idempotency_concurrency", gate_names)

    def test_idempotency_gate_read_only_passes(self):
        """Gate 4: operação somente leitura passa automaticamente (GREEN)."""
        result = check_mission(
            [_step()], 1,
            idempotency_payload={"is_mutation": False},
        )
        self.assertEqual(result["action"], "proceed")
        self.assertEqual(result["semaphore"], "GREEN")

    def test_grounding_gate_no_citations_is_yellow(self):
        """Gate 1: sem citações, GroundingGate retorna YELLOW → approval."""
        result = check_mission(
            [_step()], 1,
            grounding_payload={"citations": []},
        )
        self.assertEqual(result["action"], "approval")
        self.assertEqual(result["semaphore"], "YELLOW")


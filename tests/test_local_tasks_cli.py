import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

import cli as cli_module
from core import events, tracing
from core.local_tasks import router
from tests.test_local_tasks import GOOD, FakeClient, _profile


class AlwaysClient(FakeClient):
    """Responde sempre a mesma coisa, sem esgotar a fila."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def chat(self, model, system, user, schema):
        self.answers = [self.answer]
        return super().chat(model, system, user, schema)


class LocalTasksCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for target, attr, value in (
            (events, "EVENTS_LOG", self.dir / "events.jsonl"),
            (tracing, "TRACE_LOG", self.dir / "trace-log.jsonl"),
        ):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(router, "load_profile", return_value=_profile())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = CliRunner()

    def invoke(self, args, client):
        with mock.patch.object(router, "OllamaClient", return_value=client):
            return self.runner.invoke(cli_module.cli, args)

    def test_classify_prints_envelope_and_exit_0(self):
        result = self.invoke(["task", "classify", "algum texto"], FakeClient(GOOD))
        self.assertEqual(result.exit_code, 0, result.output)
        env = json.loads(result.output)
        self.assertEqual(env["kind"], "task.result")
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["payload"]["labels"]["type"], "adr")
        first = json.loads((self.dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(first["from"], "cli")

    def test_escalate_exit_code_2(self):
        result = self.invoke(["task", "classify", "x"], FakeClient("nao json", "ainda nao"))
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertEqual(json.loads(result.output)["status"], "escalate")

    def test_invalid_exit_code_1(self):
        result = self.invoke(["task", "extract", "--template", "nao-existe@1", "x"], FakeClient())
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertEqual(json.loads(result.output)["status"], "invalid")

    def test_file_option_reads_utf8_with_bom(self):
        path = self.dir / "in.txt"
        path.write_bytes("\ufeffconteúdo ação".encode("utf-8"))
        fake = FakeClient(GOOD)
        result = self.invoke(["task", "classify", "--file", str(path)], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(fake.users[0], "conteúdo ação")

    def test_needs_exactly_one_text_input_and_never_calls_router(self):
        path = self.dir / "in.txt"
        path.write_text("t", encoding="utf-8")
        fake = FakeClient(GOOD)
        for args in (["task", "classify"], ["task", "classify", "t", "--file", str(path)]):
            result = self.invoke(args, fake)
            self.assertEqual(result.exit_code, 2, result.output)
        self.assertEqual(fake.calls, 0)
        self.assertFalse((self.dir / "events.jsonl").exists())

    def test_validate_reads_source_file(self):
        src = self.dir / "src.txt"
        src.write_bytes("\ufefffonte".encode("utf-8"))
        fake = FakeClient({"review": []})
        doc = "---\ntype: adr\nstatus: x\ndate: 2026-01-01\n---\n# T\n"
        result = self.invoke(["task", "validate", "--template", "adr@1", "--source", str(src), "--", doc], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("fonte", fake.users[0])
        self.assertTrue(json.loads(result.output)["payload"]["valid"])

    def test_non_utf8_file_or_source_is_a_clean_error(self):
        bad = self.dir / "latin1.txt"
        bad.write_bytes("ação".encode("latin-1"))
        good = self.dir / "ok.txt"
        good.write_bytes(b"---\ntype: adr\n---\n")
        fake = FakeClient()
        for args in (["task", "classify", "--file", str(bad)],
                     ["task", "validate", "--template", "adr@1", "--file", str(good), "--source", str(bad)]):
            result = self.invoke(args, fake)
            self.assertEqual(result.exit_code, 1, result.output)
            self.assertIsInstance(result.exception, SystemExit)
            self.assertIn(f"arquivo não está em UTF-8: {bad}", result.output)
            self.assertNotIn("Traceback", result.output)
        self.assertEqual(fake.calls, 0)

    def test_summarize_passes_words(self):
        fake = FakeClient({"summary": "s", "key_points": ["a"]})
        result = self.invoke(["task", "summarize", "--words", "33", "texto curto"], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.output)["payload"]["summary"], "s")

    def test_status_uses_router_status(self):
        fake = mock.Mock()
        fake.available.return_value = True
        result = self.invoke(["task", "status"], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        out = json.loads(result.output)
        self.assertEqual(out["profile"], "t")
        self.assertTrue(out["model_available"])

    def test_task_eval_exits_1_below_min_accuracy(self):
        fake = AlwaysClient({"nope": 1})
        fake.available = lambda model: True
        result = self.invoke(["task-eval"], fake)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("classify", result.output)
        self.assertIn("Acerto geral", result.output)

    def test_task_eval_passes_with_min_accuracy_zero(self):
        fake = AlwaysClient({"nope": 1})
        fake.available = lambda model: True
        result = self.invoke(["task-eval", "--min-accuracy", "0"], fake)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("validate", result.output)

    def test_task_eval_exits_1_when_ollama_unavailable(self):
        fake = mock.Mock()
        fake.available.return_value = False
        with mock.patch.object(router, "OllamaClient", return_value=fake), \
                mock.patch.object(router, "run_task") as run_task:
            result = self.runner.invoke(cli_module.cli, ["task-eval"])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("indisponível", result.output)
        run_task.assert_not_called()


class GoldenDatasetTests(unittest.TestCase):
    def test_dataset_has_three_cases_per_task(self):
        path = Path(__file__).parent / "golden_dataset_local_tasks.json"
        cases = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 12)
        for task in ("classify", "extract", "summarize", "validate"):
            self.assertEqual(sum(c["task"] == task for c in cases), 3)


if __name__ == "__main__":
    unittest.main()

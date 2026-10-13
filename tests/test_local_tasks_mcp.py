import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastmcp import Client

from core import events, tracing
from core.local_tasks import router
from tests.test_local_tasks import GOOD, FakeClient, _profile


class LocalTasksMcpTests(unittest.TestCase):
    def setUp(self):
        import mcp_servers.local_tasks_mcp as module
        self.module = module
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events_log = Path(self.tmp.name) / "events.jsonl"
        self.trace_log = Path(self.tmp.name) / "trace-log.jsonl"
        for target, attr, value in (
            (events, "EVENTS_LOG", self.events_log),
            (tracing, "TRACE_LOG", self.trace_log),
        ):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(router, "load_profile", return_value=_profile())
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, tool, args, *answers):
        fake = FakeClient(*answers)
        with mock.patch.object(router, "OllamaClient", return_value=fake):
            async def run():
                async with Client(self.module.mcp) as client:
                    return await client.call_tool(tool, args)
            return asyncio.run(run()).data

    def test_classify_returns_result_envelope(self):
        env = self.call("classify", {"text": "algum texto"}, GOOD)
        self.assertEqual(env["kind"], "task.result")
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["payload"]["labels"]["type"], "adr")
        lines = [json.loads(l) for l in self.events_log.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(lines[0]["from"])

    def test_task_id_sets_trace_id_like_the_trace_log(self):
        env = self.call("classify", {"text": "t", "task_id": "DEM-7"}, GOOD)
        records = tracing.read_recent(10, self.trace_log)
        self.assertEqual(len(records), 1)
        self.assertEqual(env["trace_id"], records[0]["trace_id"])
        self.assertEqual(env["trace_id"], tracing.derive_trace_id("DEM-7")[0])

    def test_task_content_never_reaches_trace_or_events_log(self):
        sentinel = "SENTINELA-DO-CONTEUDO-0451"
        self.call("classify", {"text": f"abc {sentinel} def"}, GOOD)
        self.call("validate", {"document": sentinel, "template": "adr@1", "source": sentinel},
                  {"review": []})
        (rec, _) = tracing.read_recent(10, self.trace_log)
        self.assertEqual(rec["args"]["text"], {"chars": len(f"abc {sentinel} def")})
        self.assertNotIn(sentinel, self.trace_log.read_text(encoding="utf-8"))
        self.assertNotIn(sentinel, self.events_log.read_text(encoding="utf-8"))

    def test_without_task_id_envelope_shares_the_call_trace_id(self):
        env = self.call("classify", {"text": "t"}, GOOD)
        (rec,) = tracing.read_recent(10, self.trace_log)
        self.assertEqual(env["trace_id"], rec["trace_id"])
        lines = [json.loads(l) for l in self.events_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({l["trace_id"] for l in lines}, {rec["trace_id"]})

    def test_docstrings_point_to_status_and_per_process_counter(self):
        async def run():
            async with Client(self.module.mcp) as client:
                return {t.name: t.description for t in await client.list_tools()}
        tools = asyncio.run(run())
        self.assertIn("local_tasks_status", tools["extract"])
        self.assertIn("templates", tools["extract"])
        self.assertIn("processo", tools["local_tasks_status"])

    def test_unknown_template_is_refused_with_invalid(self):
        env = self.call("extract", {"text": "t", "template": "nao-existe@1"})
        self.assertEqual(env["status"], "invalid")
        self.assertEqual(env["reason"], "unknown_template")

    def test_status_reports_failures_and_profile(self):
        fake = mock.Mock()
        fake.available.return_value = True
        with mock.patch.object(router, "OllamaClient", return_value=fake), \
                mock.patch.object(events, "failures", return_value=3):
            async def run():
                async with Client(self.module.mcp) as client:
                    return await client.call_tool("local_tasks_status", {})
            out = asyncio.run(run()).data
        self.assertEqual(out["profile"], "t")
        self.assertEqual(out["local_model"], "m")
        self.assertTrue(out["model_available"])
        self.assertEqual(out["event_write_failures"], 3)
        self.assertIsInstance(out["templates"], list)


if __name__ == "__main__":
    unittest.main()

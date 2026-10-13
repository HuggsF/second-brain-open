import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from fastmcp import Client, FastMCP

from core import tracing
from core.trace_middleware import TraceMiddleware


def build_server(path: Optional[Path] = None, traced: bool = True, content_args=frozenset()) -> FastMCP:
    server = FastMCP("test")

    @server.tool()
    def ok(a: str, api_key: Optional[str] = None, task_id: Optional[str] = None) -> dict:
        return {"a": a}

    @server.tool()
    def boom() -> str:
        raise ValueError("secret detail")

    @server.tool()
    def refuse() -> dict:
        tracing.emit_child("ssh.refused", "refused", {"command": "x"})
        return {"success": False}

    if traced:
        server.add_middleware(TraceMiddleware("test", path=path, content_args=content_args))
    return server


def call(server: FastMCP, tool: str, args: Optional[dict] = None):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, args or {})

    return asyncio.run(run())


class TestTraceMiddleware(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ".runtime" / "trace-log.jsonl"

    def records(self):
        return tracing.read_recent(50, self.path)

    def test_ok_call_writes_one_record(self):
        call(build_server(self.path), "ok", {"a": "x"})
        (rec,) = self.records()
        self.assertEqual(rec["event"], "call")
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["tool"], "ok")
        self.assertEqual(rec["server"], "test")
        self.assertGreaterEqual(rec["duration_ms"], 0)
        self.assertRegex(rec["trace_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(rec["span_id"], r"^[0-9a-f]{16}$")
        self.assertIsNone(rec["parent_span_id"])
        self.assertEqual(rec["schema_version"], 1)
        self.assertEqual(rec["args"], {"a": "x"})

    def test_same_task_id_shares_trace_id_and_label(self):
        server = build_server(self.path)
        call(server, "ok", {"a": "1", "task_id": "DEM-12"})
        call(server, "ok", {"a": "2", "task_id": "DEM-12"})
        call(server, "ok", {"a": "3"})
        first, second, third = self.records()
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertEqual(first["task_label"], "DEM-12")
        self.assertNotEqual(first["trace_id"], third["trace_id"])
        self.assertIsNone(third["task_label"])
        self.assertNotIn("task_id", first["args"])

    def test_blank_task_id_is_treated_as_absent(self):
        server = build_server(self.path)
        call(server, "ok", {"a": "1", "task_id": "   "})
        call(server, "ok", {"a": "2", "task_id": "   "})
        first, second = self.records()
        self.assertIsNone(first["task_label"])
        self.assertNotEqual(first["trace_id"], second["trace_id"])

    def test_exception_is_recorded_and_reraised_unchanged(self):
        with self.assertRaises(Exception):
            call(build_server(self.path), "boom")
        (rec,) = self.records()
        self.assertEqual(rec["status"], "error")
        self.assertEqual(rec["error_type"], "ValueError")
        self.assertNotIn("secret detail", self.path.read_text(encoding="utf-8"))

    def test_refused_child_event_marks_call_refused(self):
        call(build_server(self.path), "refuse")
        recs = self.records()
        self.assertEqual(len(recs), 2)
        child = next(r for r in recs if r["event"] == "ssh.refused")
        parent = next(r for r in recs if r["event"] == "call")
        self.assertEqual(child["parent_span_id"], parent["span_id"])
        self.assertEqual(child["trace_id"], parent["trace_id"])
        self.assertNotEqual(child["span_id"], parent["span_id"])
        self.assertEqual(parent["status"], "refused")
        self.assertLessEqual(parent["ts"], child["ts"])  # a call's ts is when it started

    def test_secret_arguments_are_redacted_in_log(self):
        call(build_server(self.path), "ok", {"a": "x", "api_key": "super-secret-value"})
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("super-secret-value", text)
        self.assertIn("[redacted]", text)

    def test_content_args_are_logged_as_char_counts(self):
        call(build_server(self.path, content_args=frozenset({"a"})), "ok", {"a": "SENTINELA-CONTEUDO"})
        (rec,) = self.records()
        self.assertEqual(rec["args"], {"a": {"chars": 18}})
        self.assertNotIn("SENTINELA", self.path.read_text(encoding="utf-8"))

    def test_result_is_identical_with_and_without_middleware(self):
        traced = call(build_server(self.path), "ok", {"a": "x"})
        plain = call(build_server(traced=False), "ok", {"a": "x"})
        self.assertEqual(traced.data, plain.data)

    def test_unwritable_log_does_not_break_call(self):
        result = call(build_server(Path(self.tmp.name)), "ok", {"a": "x"})
        self.assertEqual(result.data, {"a": "x"})

    def test_caller_comes_from_client_info(self):
        call(build_server(self.path), "ok", {"a": "x"})
        (rec,) = self.records()
        self.assertEqual(rec["caller"], "mcp")

    def test_child_event_outside_a_call_is_a_no_op(self):
        self.assertIsNone(tracing.emit_child("ssh.exec", "ok", path=self.path))
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()

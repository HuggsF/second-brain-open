"""Testes do corretor único: decide, executa e grava rastro com a identidade do agente."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import broker, tracing
from core.tools import IMPLEMENTATIONS


def _fake(result=None, calls=None):
    async def impl(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return result if result is not None else {"ok": True}
    return impl


class TestBroker(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.trace = Path(self.dir.name) / "trace.jsonl"

    def records(self):
        if not self.trace.exists():
            return []
        return [json.loads(line) for line in self.trace.read_text(encoding="utf-8").splitlines()]

    async def test_approve_executes_and_traces_identity(self):
        calls = []
        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": _fake({"adr": "x"}, calls)}):
            result = await broker.call("agent:researcher", "get_adr", {"identifier": "ADR-003"}, "M7",
                                       trace_path=self.trace)
        self.assertEqual(result["verdict"], "APPROVE")
        self.assertEqual(result["adr"], "x")
        self.assertEqual(calls, [{"identifier": "ADR-003"}])
        (rec,) = self.records()
        self.assertEqual(rec["caller"], "agent:researcher")
        self.assertEqual(rec["tool"], "get_adr")
        self.assertEqual(rec["task_label"], "M7")
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["server"], "broker")
        self.assertEqual(rec["event"], "call")

    async def test_deny_does_not_execute(self):
        calls = []
        with mock.patch.dict(IMPLEMENTATIONS, {"read_vault_file": _fake(calls=calls)}):
            result = await broker.call("agent:researcher", "read_vault_file", {}, trace_path=self.trace)
        self.assertEqual(calls, [])
        self.assertEqual(result["verdict"], "DENY")
        self.assertTrue(result["refused"])
        self.assertEqual(self.records()[0]["status"], "refused")

    async def test_escalate_without_approval_does_not_execute(self):
        calls = []
        with mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": _fake(calls=calls)}):
            result = await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"},
                                       trace_path=self.trace)
        self.assertEqual(calls, [])
        self.assertEqual(result["verdict"], "ESCALATE")
        self.assertTrue(result["approval_required"])
        self.assertTrue(result["refused"])
        self.assertEqual(self.records()[0]["status"], "escalated")

    async def test_escalate_with_approval_executes(self):
        calls = []
        with mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": _fake({"stdout": "ok"}, calls)}):
            result = await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"},
                                       approved=True, trace_path=self.trace)
        self.assertEqual(calls, [{"command": "docker ps"}])
        self.assertEqual(result["verdict"], "ESCALATE")
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(self.records()[0]["status"], "ok")

    async def test_denied_command_never_executes_even_if_approved(self):
        calls = []
        with mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": _fake(calls=calls)}):
            result = await broker.call("agent:coder", "run_safe_command", {"command": "rm -rf /"},
                                       approved=True, trace_path=self.trace)
        self.assertEqual(calls, [])
        self.assertEqual(result["verdict"], "DENY")

    async def test_tool_error_keeps_only_class_name(self):
        async def boom(**kwargs):
            raise RuntimeError("token=abc123 CPF 123.456.789-09")

        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": boom}):
            result = await broker.call("agent:researcher", "get_adr", {"identifier": "A"}, trace_path=self.trace)
        self.assertEqual(result["error"], "RuntimeError")
        blob = json.dumps(result) + self.trace.read_text(encoding="utf-8")
        self.assertNotIn("abc123", blob)
        self.assertNotIn("123.456.789-09", blob)
        rec = self.records()[0]
        self.assertEqual(rec["status"], "error")
        self.assertEqual(rec["error_type"], "RuntimeError")

    async def test_wrong_kwargs_is_tool_error(self):
        async def strict(identifier):
            return {}

        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": strict}):
            result = await broker.call("agent:researcher", "get_adr", {"nope": 1}, trace_path=self.trace)
        self.assertEqual(result["error"], "TypeError")

    async def test_malformed_input_never_raises(self):
        result = await broker.call("agent:coder", 42, "x", None, trace_path=self.trace)
        self.assertEqual(result["verdict"], "DENY")
        self.assertEqual(result["reason"], "malformed_args")
        result = await broker.call(["x"], "get_adr", {}, trace_path=self.trace)
        self.assertEqual(result["verdict"], "DENY")
        self.assertEqual(result["reason"], "bad_identity")
        result = await broker.call("agent:researcher", 42, {}, trace_path=self.trace)
        self.assertEqual(result["reason"], "unknown_tool")
        result = await broker.call("agent:researcher", "get_adr", "x", trace_path=self.trace)
        self.assertEqual(result["verdict"], "DENY")
        self.assertEqual(result["reason"], "malformed_args")

    async def test_unwritable_trace_does_not_change_verdict(self):
        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": _fake({"adr": "x"})}):
            result = await broker.call("agent:researcher", "get_adr", {"identifier": "A"},
                                       trace_path=Path(self.dir.name))
        self.assertEqual(result["verdict"], "APPROVE")
        self.assertEqual(result["adr"], "x")

    async def test_unwritable_trace_deny_and_escalate(self):
        bad = Path(self.dir.name)
        denied = await broker.call("agent:researcher", "read_vault_file", {}, trace_path=bad)
        self.assertEqual(denied["verdict"], "DENY")
        esc = await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"}, trace_path=bad)
        self.assertEqual(esc["verdict"], "ESCALATE")
        self.assertTrue(esc["approval_required"])

    async def test_default_trace_path_read_at_call_time(self):
        with mock.patch.object(tracing, "TRACE_LOG", self.trace), \
                mock.patch.dict(IMPLEMENTATIONS, {"get_adr": _fake()}):
            await broker.call("agent:researcher", "get_adr", {"identifier": "A"})
        self.assertEqual(len(self.records()), 1)

    async def test_child_events_attach_to_call(self):
        async def with_child(**kwargs):
            tracing.emit_child("ssh.exec", "ok", {"command": "docker ps", "exit_code": 0})
            return {"ok": True}

        with mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": with_child}):
            await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"},
                              approved=True, trace_path=self.trace)
        self.assertIsNone(tracing.current_call.get())
        child = next(r for r in self.records() if r["event"] == "ssh.exec")
        parent = next(r for r in self.records() if r["event"] == "call")
        self.assertEqual(child["parent_span_id"], parent["span_id"])
        self.assertEqual(child["trace_id"], parent["trace_id"])

    async def test_child_events_cross_executor_thread(self):
        import types
        from core import tools

        def fake_exec(command):
            tracing.emit_child("ssh.exec", "ok", {"command": command, "exit_code": 0})
            return {"success": True, "exit_code": 0, "stdout": "", "stderr": ""}

        module = types.ModuleType("mcp_servers.srv_api_gateway_mcp")
        module._exec_command = fake_exec
        with mock.patch.dict("sys.modules", {"mcp_servers.srv_api_gateway_mcp": module}),                 mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": tools.run_safe_command}):
            await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"},
                              approved=True, trace_path=self.trace)
        parent = next(r for r in self.records() if r["event"] == "call")
        child = next(r for r in self.records() if r["event"] == "ssh.exec")
        self.assertEqual(child["parent_span_id"], parent["span_id"])

    async def test_tool_returned_error_text_is_masked_and_trace_uses_fixed_token(self):
        impl = _fake({"error": "falhou token=ghp_abcdefghij123456 CPF 123.456.789-09"})
        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": impl}):
            result = await broker.call("agent:researcher", "get_adr", {"identifier": "A"}, trace_path=self.trace)
        self.assertNotIn("ghp_abcdefghij123456", json.dumps(result))
        self.assertNotIn("123.456.789-09", json.dumps(result))
        rec = self.records()[0]
        self.assertEqual(rec["status"], "error")
        self.assertEqual(rec["error_type"], "ToolError")
        self.assertNotIn("falhou", self.trace.read_text(encoding="utf-8"))

    async def test_approved_must_be_exactly_true(self):
        for value in ("false", 1, "yes"):
            calls = []
            with mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": _fake(calls=calls)}):
                result = await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"},
                                           approved=value, trace_path=self.trace)
            self.assertEqual(calls, [])
            self.assertTrue(result["approval_required"])

    async def test_child_refusal_marks_call_refused(self):
        async def refuses(**kwargs):
            tracing.emit_child("ssh.refused", "refused", {"command": "x"})
            return {"success": False}

        with mock.patch.dict(IMPLEMENTATIONS, {"run_safe_command": refuses}):
            await broker.call("agent:coder", "run_safe_command", {"command": "docker ps"},
                              approved=True, trace_path=self.trace)
        call = next(r for r in self.records() if r["event"] == "call")
        self.assertEqual(call["status"], "refused")

    async def test_tool_cannot_overwrite_verdict_fields(self):
        impl = _fake({"verdict": "X", "reason": "Y", "refused": True})
        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": impl}):
            result = await broker.call("agent:researcher", "get_adr", {"identifier": "A"}, trace_path=self.trace)
        self.assertEqual(result["verdict"], "APPROVE")
        self.assertEqual(result["reason"], "read_auto")
        self.assertNotIn("refused", result)

    async def test_malformed_identity_never_in_trace(self):
        await broker.call("agent:x 123.456.789-09", "get_adr", {"identifier": "A"}, trace_path=self.trace)
        text = self.trace.read_text(encoding="utf-8")
        self.assertNotIn("123.456.789-09", text)
        self.assertEqual(self.records()[0]["caller"], "unknown")

    async def test_record_event_writes_and_never_raises(self):
        broker.record_event("agent:coder", "gate.refused", "refused", {"x": 1}, "M7", trace_path=self.trace)
        rec = self.records()[0]
        self.assertEqual(rec["event"], "gate.refused")
        self.assertEqual(rec["caller"], "agent:coder")
        broker.record_event(None, None, None, "bad", trace_path=Path(self.dir.name))

    def test_record_event_malformed_identity_is_unknown(self):
        broker.record_event("agent:x 123.456.789-09", "gate.pipeline", "ok", trace_path=self.trace)
        self.assertNotIn("123.456.789-09", self.trace.read_text(encoding="utf-8"))
        self.assertEqual(self.records()[0]["caller"], "unknown")


if __name__ == "__main__":
    unittest.main()

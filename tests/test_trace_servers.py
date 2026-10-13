import asyncio
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastmcp import Client

from core import tracing
from core.trace_middleware import TraceMiddleware

SERVERS = [
    "mcp_servers.brain_mcp",
    "mcp_servers.github_gateway_mcp",
    "mcp_servers.srv_api_gateway_mcp",
    "mcp_servers.local_tasks_mcp",
    "mcp_servers.hub_observability_mcp",
]


def tools_of(module_name):
    module = importlib.import_module(module_name)
    return module, asyncio.run(module.mcp.list_tools())


class TestServersAreTraced(unittest.TestCase):
    def test_total_tool_count_is_25(self):
        total = sum(len(tools_of(name)[1]) for name in SERVERS)
        self.assertEqual(total, 25)

    def test_every_tool_has_optional_task_id(self):
        for name in SERVERS:
            _, tools = tools_of(name)
            self.assertGreater(len(tools), 0, name)
            for tool in tools:
                schema = tool.parameters
                self.assertIn("task_id", schema.get("properties", {}), f"{name}:{tool.name}")
                self.assertNotIn("task_id", schema.get("required", []), f"{name}:{tool.name}")

    def test_middleware_registered(self):
        for name in SERVERS:
            module, _ = tools_of(name)
            self.assertTrue(
                any(isinstance(m, TraceMiddleware) for m in module.mcp.middleware),
                f"{name} has no TraceMiddleware",
            )

    def test_task_id_does_not_change_behaviour_and_is_logged(self):
        module = importlib.import_module("mcp_servers.brain_mcp")

        async def run(args):
            async with Client(module.mcp) as client:
                return await client.call_tool("get_system_architecture", args)

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / ".runtime" / "trace-log.jsonl"
            with mock.patch.object(tracing, "TRACE_LOG", log):
                plain = asyncio.run(run({"system_name": "sap"}))
                tagged = asyncio.run(run({"system_name": "sap", "task_id": "DEM-1"}))
            self.assertEqual(plain.data, tagged.data)
            records = tracing.read_recent(10, log)
            self.assertEqual(len(records), 2)
            self.assertIsNone(records[0]["task_label"])
            self.assertEqual(records[1]["task_label"], "DEM-1")
            self.assertEqual(records[1]["tool"], "get_system_architecture")
            self.assertEqual(records[1]["server"], "KIOSK Second Brain")


class TestGatewayChildEvents(unittest.TestCase):
    def setUp(self):
        import mcp_servers.srv_api_gateway_mcp as gw
        self.gw = gw
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / ".runtime" / "trace-log.jsonl"
        patcher = mock.patch.object(tracing, "TRACE_LOG", self.log)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, tool, args):
        async def run():
            async with Client(self.gw.mcp) as client:
                return await client.call_tool(tool, args)

        return asyncio.run(run())

    def fake_ssh(self, exit_code=0):
        client = mock.MagicMock()
        out, err = mock.MagicMock(), mock.MagicMock()
        out.read.return_value, err.read.return_value = b"ok", b""
        out.channel.recv_exit_status.return_value = exit_code
        client.exec_command.return_value = (mock.MagicMock(), out, err)
        return client

    def records(self):
        return tracing.read_recent(20, self.log)

    def test_refused_command_logs_ssh_refused_and_call_is_refused(self):
        with mock.patch.object(self.gw, "ALLOW_ARBITRARY", False),                 mock.patch.object(self.gw, "_get_ssh_client") as ssh:
            self.call("srv_api_run_safe_command", {"command": "ls; id"})
            ssh.assert_not_called()
        child = next(r for r in self.records() if r["event"] == "ssh.refused")
        parent = next(r for r in self.records() if r["event"] == "call")
        self.assertEqual(child["status"], "refused")
        self.assertEqual(child["args"]["command"], "ls; id")
        self.assertTrue(child["args"]["reason"])
        self.assertEqual(child["parent_span_id"], parent["span_id"])
        self.assertEqual(parent["status"], "refused")

    def test_blocklisted_command_is_also_refused(self):
        with mock.patch.object(self.gw, "_get_ssh_client") as ssh:
            self.call("srv_api_run_safe_command", {"command": "rm -rf /tmp/x"})
            ssh.assert_not_called()
        self.assertTrue(any(r["event"] == "ssh.refused" for r in self.records()))

    def test_executed_command_logs_ssh_exec_with_exit_code(self):
        with mock.patch.object(self.gw, "_get_ssh_client", return_value=self.fake_ssh(0)):
            self.call("srv_api_run_safe_command", {"command": "ls -la"})
        child = next(r for r in self.records() if r["event"] == "ssh.exec")
        parent = next(r for r in self.records() if r["event"] == "call")
        self.assertEqual(child["status"], "ok")
        self.assertEqual(child["args"]["exit_code"], 0)
        self.assertEqual(child["args"]["command"], "ls -la")
        self.assertEqual(parent["status"], "ok")

    def test_nonzero_exit_code_is_an_error_event(self):
        with mock.patch.object(self.gw, "_get_ssh_client", return_value=self.fake_ssh(2)):
            self.call("srv_api_run_safe_command", {"command": "ls /nope"})
        child = next(r for r in self.records() if r["event"] == "ssh.exec")
        self.assertEqual(child["status"], "error")
        self.assertEqual(child["args"]["exit_code"], 2)

    def test_connection_error_logs_ssh_exec_error(self):
        with mock.patch.object(self.gw, "_get_ssh_client", side_effect=ConnectionError("unreachable")):
            self.call("srv_api_health_check", {})
        child = next(r for r in self.records() if r["event"] == "ssh.exec")
        self.assertEqual(child["status"], "error")
        self.assertEqual(child["error_type"], "ConnectionError")
        self.assertNotIn("unreachable", self.log.read_text(encoding="utf-8"))

    def test_gateway_audit_file_is_no_longer_written(self):
        with mock.patch.object(self.gw, "_get_ssh_client", return_value=self.fake_ssh(0)):
            self.call("srv_api_run_safe_command", {"command": "ls"})
        self.assertFalse(hasattr(self.gw, "_audit"))
        self.assertFalse(hasattr(self.gw, "AUDIT_LOG"))
        self.assertNotIn("gateway-audit.jsonl", [p.name for p in self.log.parent.iterdir()])


if __name__ == "__main__":
    unittest.main()

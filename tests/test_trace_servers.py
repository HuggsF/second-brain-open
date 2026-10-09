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
    "mcp_servers.hub_observability_mcp",
]


def tools_of(module_name):
    module = importlib.import_module(module_name)
    return module, asyncio.run(module.mcp.list_tools())


class TestServersAreTraced(unittest.TestCase):
    def test_total_tool_count_is_15(self):
        total = sum(len(tools_of(name)[1]) for name in SERVERS)
        self.assertEqual(total, 15)

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


if __name__ == "__main__":
    unittest.main()

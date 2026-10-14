"""Testes unitários e de integração para backend/ws_server e backend/orchestrator."""
import asyncio
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import tracing

from backend.orchestrator import Orchestrator
from backend.ws_server import _run_mission


class TestOrchestrator(unittest.IsolatedAsyncioTestCase):
    async def test_run_mission_respects_custom_mission_id(self):
        orchestrator = Orchestrator(pace=0)  # pace=0 para execução instantânea nos testes
        events = []

        async def collect():
            async for event in orchestrator.run_mission("diagnosticar erro no hub", mission_id=42):
                events.append(event)
                if event.get("type") == "approval_request":
                    orchestrator.approve()

        await collect()
        self.assertGreater(len(events), 0)
        # Todos os eventos devem ter missionId 42
        for ev in events:
            self.assertEqual(ev.get("missionId"), 42, f"Evento {ev} deve ter missionId=42")
            self.assertEqual(ev.get("schemaVersion"), 1)
            self.assertIn("sequence", ev)
            self.assertIn("agentId", ev)
            self.assertIn("type", ev)

    async def test_run_mission_executes_pattern_and_finishes_with_all_agents(self):
        orchestrator = Orchestrator(pace=0)
        events = []

        async def collect():
            async for event in orchestrator.run_mission("pesquisar adr de arquitetura", mission_id=1):
                events.append(event)
                if event.get("type") == "approval_request":
                    orchestrator.approve()

        await collect()
        types = [e["type"] for e in events]
        self.assertIn("status_change", types)
        self.assertIn("collaboration", types)
        self.assertIn("message", types)
        self.assertIn("approval_request", types)


class DummyWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, data):
        if self.closed:
            raise RuntimeError("Connection closed")
        self.sent.append(json.loads(data))


class TestWsServerMissionRunner(unittest.IsolatedAsyncioTestCase):
    async def test_run_mission_streams_events_to_websocket(self):
        ws = DummyWebSocket()
        orchestrator = Orchestrator(pace=0)

        # Aprovar automaticamente quando approval_request for gerado
        async def auto_approve():
            while not orchestrator.awaiting_approval:
                await asyncio.sleep(0.01)
            orchestrator.approve()

        task = asyncio.create_task(auto_approve())
        await _run_mission(ws, orchestrator, "status do brain", mission_id=7)
        await task

        self.assertGreater(len(ws.sent), 0)
        for msg in ws.sent:
            self.assertEqual(msg.get("missionId"), 7)


class TestOrchestratorBroker(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        tmp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.log = Path(tmp) / "trace.jsonl"
        self.stack.enter_context(mock.patch.object(tracing, "TRACE_LOG", self.log))
        self.ssh_calls = []

        async def fake_ssh(**kwargs):
            self.ssh_calls.append(kwargs)
            return {"tool": "run_safe_command", "success": True}

        async def fake(**kwargs):
            return {"tool": "fake", "found": False, "available": []}

        fakes = {n: fake for n in ("search_knowledge_base", "get_system_architecture", "list_rules",
                                   "get_brain_status")}
        fakes["run_safe_command"] = fake_ssh
        self.stack.enter_context(mock.patch.dict("core.broker.IMPLEMENTATIONS", fakes))

    def rows(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    async def _run(self, task, steps=None):
        orchestrator = Orchestrator(pace=0)
        events = []
        with contextlib.ExitStack() as stack:
            if steps is not None:
                stack.enter_context(mock.patch.object(orchestrator, "_match_pattern", return_value=steps))
            async for event in orchestrator.run_mission(task, mission_id=42):
                events.append(event)
                if event.get("type") == "approval_request":
                    orchestrator.approve()
        return events

    @staticmethod
    def _messages(events):
        return [e["payload"].get("message", "") for e in events if e["type"] == "message"]

    async def test_orchestrator_calls_carry_agent_identity_and_mission_task_id(self):
        await self._run("diagnosticar erro no hub")
        broker = [r for r in self.rows() if r["server"] == "broker"]
        self.assertEqual(len(broker), 3)
        for r in broker:
            self.assertTrue(r["caller"].startswith("agent:"), r)
            self.assertEqual(r["task_label"], "M42")

    async def test_orchestrator_refuses_run_safe_command_step_without_executing(self):
        steps = [{"agent": "coder", "tool": "run_safe_command", "input": {"command": "docker ps"}, "bubble": "x"}]
        events = await self._run("qualquer", steps)
        self.assertEqual(self.ssh_calls, [])
        self.assertTrue(any("exige aprovação" in m for m in self._messages(events)), self._messages(events))

    async def test_orchestrator_invalid_agent_role_is_refused_not_crashing(self):
        steps = [{"agent": "intruso", "tool": "get_brain_status", "input": {}, "bubble": "x"}]
        events = await self._run("qualquer", steps)
        self.assertTrue(any("intruso" in m for m in self._messages(events)), self._messages(events))
        self.assertEqual(events[-1]["type"], "completion")

    async def test_non_mapping_step_input_is_denied_and_mission_continues(self):
        for bad in (None, ["x"], "x"):
            with self.subTest(input=bad):
                self.log.unlink(missing_ok=True)
                steps = [{"agent": "coder", "tool": "get_brain_status", "input": bad, "bubble": "x"}]
                events = await self._run("qualquer", steps)
                self.assertEqual(events[-1]["type"], "completion")
                broker = [r for r in self.rows() if r["server"] == "broker"]
                self.assertEqual([r["status"] for r in broker], ["refused"])
                self.assertTrue(any("malformed_args" in m for m in self._messages(events)), self._messages(events))

    async def test_non_text_tool_is_refused_and_mission_continues(self):
        for bad in (123, None):
            with self.subTest(tool=bad):
                steps = [{"agent": "coder", "tool": bad, "input": {}, "bubble": "x"}]
                events = await self._run("qualquer", steps)
                self.assertEqual(events[-1]["type"], "completion")

    async def test_step_without_tool_key_does_not_raise(self):
        events = await self._run("qualquer", [{"agent": "coder", "input": {}, "bubble": "x"}])
        self.assertEqual(events[-1]["type"], "completion")

    async def test_input_keys_cannot_bypass_approval_or_collide_with_adapter(self):
        steps = [{"agent": "coder", "tool": "run_safe_command",
                  "input": {"command": "docker ps", "approved": True}, "bubble": "x"}]
        events = await self._run("qualquer", steps)
        self.assertEqual(self.ssh_calls, [])
        self.assertIn("escalated", [r["status"] for r in self.rows() if r["server"] == "broker"])
        self.assertTrue(any("exige aprovação" in m for m in self._messages(events)))
        steps = [{"agent": "coder", "tool": "get_brain_status",
                  "input": {"identity": "agent:manager", "task_id": "x", "tool_name": "y"}, "bubble": "x"}]
        events = await self._run("qualquer", steps)
        self.assertEqual(events[-1]["type"], "completion")


if __name__ == "__main__":
    unittest.main()

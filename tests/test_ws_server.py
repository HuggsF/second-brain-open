"""Testes unitários e de integração para backend/ws_server e backend/orchestrator."""
import asyncio
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
    async def _run(self, task, steps=None):
        orchestrator = Orchestrator(pace=0)
        events = []
        patches = [mock.patch.object(orchestrator, "_match_pattern", return_value=steps)] if steps else []
        for p in patches:
            p.start()
        try:
            async for event in orchestrator.run_mission(task, mission_id=42):
                events.append(event)
                if event.get("type") == "approval_request":
                    orchestrator.approve()
        finally:
            for p in patches:
                p.stop()
        return events

    async def test_orchestrator_calls_carry_agent_identity_and_mission_task_id(self):
        async def fake(**kwargs):
            return {"tool": "fake", "found": False, "available": []}

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "trace.jsonl"
            fakes = {n: fake for n in ("search_knowledge_base", "get_system_architecture", "list_rules")}
            with mock.patch.object(tracing, "TRACE_LOG", log),                     mock.patch.dict("core.broker.IMPLEMENTATIONS", fakes):
                await self._run("diagnosticar erro no hub")
            rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        broker = [r for r in rows if r["server"] == "broker"]
        self.assertEqual(len(broker), 3)
        for r in broker:
            self.assertTrue(r["caller"].startswith("agent:"), r)
            self.assertEqual(r["task_label"], "M42")

    async def test_orchestrator_refuses_run_safe_command_step_without_executing(self):
        calls = []

        async def fake_ssh(**kwargs):
            calls.append(kwargs)
            return {"tool": "run_safe_command", "success": True}

        steps = [{"agent": "coder", "tool": "run_safe_command", "input": {"command": "docker ps"}, "bubble": "x"}]
        with tempfile.TemporaryDirectory() as tmp,                 mock.patch.object(tracing, "TRACE_LOG", Path(tmp) / "trace.jsonl"),                 mock.patch.dict("core.broker.IMPLEMENTATIONS", {"run_safe_command": fake_ssh}):
            events = await self._run("qualquer", steps)
        self.assertEqual(calls, [])
        messages = [e["payload"].get("message", "") for e in events if e["type"] == "message"]
        self.assertTrue(any("exige aprovação" in m for m in messages), messages)

    async def test_orchestrator_invalid_agent_role_is_refused_not_crashing(self):
        steps = [{"agent": "intruso", "tool": "get_brain_status", "input": {}, "bubble": "x"}]
        events = await self._run("qualquer", steps)
        messages = [e["payload"].get("message", "") for e in events if e["type"] == "message"]
        self.assertTrue(any("intruso" in m for m in messages), messages)
        self.assertEqual(events[-1]["type"], "completion")


if __name__ == "__main__":
    unittest.main()

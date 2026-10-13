"""Testes unitários e de integração para backend/ws_server e backend/orchestrator."""
import asyncio
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()

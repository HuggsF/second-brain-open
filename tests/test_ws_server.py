"""Testes unitários e de integração para backend/ws_server e backend/orchestrator."""
import asyncio
import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import tracing

from backend import ws_server
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


class FakeWebSocket(DummyWebSocket):
    """Websocket de teste iterável: entrega as mensagens e encerra."""

    remote_address = ("127.0.0.1", 0)

    def __init__(self, messages):
        super().__init__()
        # Itens callable rodam entre mensagens (inspeção do estado intermediário)
        self._messages = [m if callable(m) else json.dumps(m) for m in messages]

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for raw in self._messages:
            await asyncio.sleep(0)
            if callable(raw):
                raw()
                continue
            yield raw
        await asyncio.sleep(0)  # deixa a missão agendada começar


class TestWsServerNewTaskValidation(unittest.IsolatedAsyncioTestCase):
    async def _drive(self, message):
        ws = FakeWebSocket([message])
        started = []

        async def fake_run_mission(websocket, orchestrator, task_text, mission_id=None):
            started.append((task_text, mission_id))

        with mock.patch.object(ws_server, "_run_mission", fake_run_mission):
            await ws_server.handler(ws)
        self.assertNotIn(ws, ws_server.CONNECTIONS)
        return ws.sent, started

    @staticmethod
    def _new_task(task="status do brain", **extra):
        return {
            "commandId": "c1",
            "action": {"type": "NEW_TASK", "payload": task},
            **extra,
        }

    async def _assert_rejected(self, message, expected_mission_id):
        sent, started = await self._drive(message)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["type"], "REJECT")
        self.assertEqual(sent[0]["commandId"], "c1")
        self.assertEqual(sent[0]["missionId"], expected_mission_id)
        self.assertEqual(sent[0]["revision"], 1)
        self.assertTrue(sent[0]["reason"])
        self.assertEqual(started, [])
        return sent[0]

    async def test_new_task_with_invalid_mission_id_is_rejected(self):
        cases = [
            (True, None),
            (0, 0),
            (2 ** 53, None),
            (-3, -3),
            ("abc", "abc"),
            ("x" * 64, "x" * 64),
            ("x" * 100, None),
            (10 ** 400, None),
            (1.5, None),
            ([1], None),
        ]
        for bad, expected_echo in cases:
            with self.subTest(mission_id=bad if not isinstance(bad, int) or bad < 10 ** 20 else "huge"):
                reject = await self._assert_rejected(
                    self._new_task(missionId=bad), expected_echo
                )
                self.assertIn("mission.id", reject["reason"])

    async def test_rejected_new_task_does_not_cancel_running_mission(self):
        release = asyncio.Event()
        runs = []

        async def fake_run_mission(websocket, orchestrator, task_text, mission_id=None):
            runs.append(task_text)
            try:
                await release.wait()
            except asyncio.CancelledError:
                runs.append(f"cancelled:{task_text}")
                raise

        snapshots = []
        ws = FakeWebSocket([
            self._new_task("primeira", missionId=1),
            self._new_task("   ", missionId=2),
            lambda: snapshots.append(list(runs)),
            self._new_task("segunda", missionId=3),
        ])
        with mock.patch.object(ws_server, "_run_mission", fake_run_mission):
            await ws_server.handler(ws)

        self.assertEqual(snapshots, [["primeira"]])
        self.assertEqual(runs, ["primeira", "cancelled:primeira", "segunda"])
        self.assertEqual(
            [m["type"] for m in ws.sent], ["ACK", "REJECT", "ACK"]
        )

    async def test_new_task_over_4000_chars_is_rejected(self):
        reject = await self._assert_rejected(
            self._new_task("x" * 4001, missionId=1), 1
        )
        self.assertIn("4000", reject["reason"])

    async def test_new_task_empty_or_non_string_is_rejected(self):
        for bad in ("", "   ", None, 5):
            with self.subTest(task=bad):
                reject = await self._assert_rejected(self._new_task(bad, missionId=1), 1)
                self.assertEqual(reject["reason"], "mission.task must be a non-empty string")

    async def test_new_task_valid_still_acks(self):
        sent, started = await self._drive(self._new_task(missionId=7))
        self.assertEqual(
            sent,
            [{"type": "ACK", "commandId": "c1", "missionId": 7, "revision": 1}],
        )
        self.assertEqual(started, [("status do brain", 7)])

    async def test_new_task_without_mission_id_defaults_to_one(self):
        sent, started = await self._drive(self._new_task())
        self.assertEqual(sent[0]["type"], "ACK")
        self.assertEqual(sent[0]["missionId"], 1)
        self.assertEqual(started, [("status do brain", 1)])


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
        self.stack.enter_context(mock.patch("backend.orchestrator.check_mission", side_effect=self._pass_guard))

    @staticmethod
    def _pass_guard(steps, mission_id, pipeline=None):
        return {"action": "proceed", "semaphore": "GREEN", "gate_results": []}

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


class TestOrchestratorGuard(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        tmp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.log = Path(tmp) / "trace.jsonl"
        self.stack.enter_context(mock.patch.object(tracing, "TRACE_LOG", self.log))

        async def fake(**kwargs):
            return {"tool": "fake", "found": False, "available": []}

        self.stack.enter_context(mock.patch.dict("core.broker.IMPLEMENTATIONS", {"get_brain_status": fake}))

    def rows(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    async def _drive(self, steps, check=None):
        orchestrator = Orchestrator(pace=0)
        events = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(orchestrator, "_match_pattern", return_value=steps))
            if check is not None:
                stack.enter_context(mock.patch("backend.orchestrator.check_mission", return_value=check))
            async for event in orchestrator.run_mission("qualquer", mission_id=5):
                events.append(event)
                if event.get("type") == "approval_request":
                    orchestrator.approve()
        return events

    async def test_mission_with_unknown_tool_is_blocked_before_any_step(self):
        steps = [{"agent": "coder", "tool": "drop_table", "input": {}, "bubble": "x"}]
        events = await self._drive(steps)
        self.assertFalse([r for r in self.rows() if r["event"] == "call"])
        self.assertTrue([r for r in self.rows() if r["event"] == "gate.pipeline"])
        self.assertEqual(events[-1]["type"], "message")
        self.assertEqual(events[-1]["agentId"], "manager")
        self.assertIn("bloqueada", events[-1]["payload"]["message"])
        self.assertNotIn("completion", [e["type"] for e in events])

    async def test_yellow_mission_waits_for_approval(self):
        steps = [{"agent": "coder", "tool": "get_brain_status", "input": {}, "bubble": "x"}]
        check = {"action": "approval", "semaphore": "YELLOW", "gate_results": []}
        orchestrator = Orchestrator(pace=0)
        events = []

        async def consume():
            with mock.patch.object(orchestrator, "_match_pattern", return_value=steps),                     mock.patch("backend.orchestrator.check_mission", return_value=check):
                async for event in orchestrator.run_mission("qualquer", mission_id=6):
                    events.append(event)
                    if event["type"] == "approval_request" and event["agentId"] == "reviewer":
                        orchestrator.approve()

        task = asyncio.ensure_future(consume())
        for _ in range(50):
            await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertTrue(orchestrator.awaiting_approval)
        self.assertEqual(events[-1]["type"], "approval_request")
        self.assertEqual(events[-1]["agentId"], "manager")
        self.assertFalse([r for r in self.rows() if r["event"] == "call"])
        orchestrator.approve()
        await asyncio.wait_for(task, timeout=5)
        self.assertEqual(events[-1]["type"], "completion")

    async def test_yellow_mission_timeout_ends_with_message(self):
        steps = [{"agent": "coder", "tool": "get_brain_status", "input": {}, "bubble": "x"}]
        check = {"action": "approval", "semaphore": "YELLOW", "gate_results": []}
        with mock.patch("backend.orchestrator.asyncio.wait_for", side_effect=asyncio.TimeoutError) as wf:
            events = await self._drive(steps, check)
        wf.assert_called_once()
        self.assertEqual(events[-1]["type"], "message")
        self.assertFalse([r for r in self.rows() if r["event"] == "call"])


if __name__ == "__main__":
    unittest.main()

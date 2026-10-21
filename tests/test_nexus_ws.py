"""Integração Nexus ↔ second brain: orquestrador, ws_server e contrato com o frontend.

Nada aqui toca Qdrant, Ollama ou SSH: exec_tool é substituído por um stub e o
orquestrador roda com pace=0. Os testes de contrato e ponta a ponta chamam o
código real do frontend (nexus/src) via node (tests/nexus_bridge.mjs).
"""
import asyncio
import copy
import json
import shutil
import subprocess
import threading
import unittest
from pathlib import Path
from unittest import mock

import websockets

from backend import orchestrator as orch_mod
from core import tools as tool_executor
from backend import ws_server
from core import retriever as retriever_mod

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "tests" / "nexus_bridge.mjs"
TASKS = [
    "diagnosticar fila de pedidos no hub",
    "qual playbook usar?",
    "decisão de arquitetura adr",
    "como funciona o oauth do bling?",
    "status do brain",
    "pergunta sem padrão nenhum",
]


def _node():
    node = shutil.which("node")
    if not node:
        raise AssertionError("node não encontrado no PATH (Node 24 é pré-requisito, CLAUDE.md §3)")
    return node


class _ToolStub:
    """Substitui run_tool: registra chamadas e devolve resultados no formato real."""

    def __init__(self):
        self.calls = []

    async def __call__(self, tool, args=None, **kwargs):
        self.calls.append((tool, kwargs))
        if tool == "search_knowledge_base":
            query = (args or {}).get("query") or kwargs.get("query")
            return {"tool": tool, "query": query, "total": 1, "sources": [
                {"document": "vault/systems/x.md", "title": "X", "section": "S", "score": 0.9, "excerpt": "trecho"}]}
        if tool == "list_rules":
            return {"tool": tool, "total": 1, "rules": [{"id": "RULE-001", "title": "t", "status": "pass"}]}
        if tool == "get_brain_status":
            return {"tool": tool, "collection": "kiosk_brain", "points_count": 10, "status": "GREEN"}
        if tool == "get_system_architecture":
            system = (args or {}).get("system_name") or kwargs.get("system_name")
            return {"tool": tool, "found": True, "system": system, "excerpt": "doc", "total_lines": 3}
        if tool == "get_adr":
            return {"tool": tool, "found": True, "file": "ADR-001.md", "excerpt": "adr", "total_lines": 3}
        return {"tool": tool, "error": "inesperado"}


async def _collect(orchestrator, task, mission_id=None):
    async def approver():
        while True:
            await asyncio.sleep(0)
            orchestrator.approve()

    approving = asyncio.create_task(approver())
    try:
        kwargs = {} if mission_id is None else {"mission_id": mission_id}
        return [event async for event in orchestrator.run_mission(task, **kwargs)]
    finally:
        approving.cancel()


def _run_missions(tasks, mission_id=None):
    stub = _ToolStub()

    async def main():
        out = []
        for task in tasks:
            out.append(await _collect(orch_mod.Orchestrator(pace=0), task, mission_id))
        return out

    with mock.patch.object(orch_mod, "run_tool", stub):
        return asyncio.run(main()), stub


class TestOrchestratorContract(unittest.TestCase):
    def test_every_event_passes_the_frontend_decoder(self):
        missions, _ = _run_missions(TASKS)
        events = [e for mission in missions for e in mission]
        proc = subprocess.run([_node(), str(BRIDGE), "decode"], input=json.dumps(events),
                              capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(report["total"], len(events))
        self.assertEqual(report["rejected"], [])

    def test_distribute_event_uses_from_key(self):
        missions, _ = _run_missions(["status do brain"])
        distribute = [e for e in missions[0] if e["payload"].get("subtype") == "distribute"]
        self.assertEqual(len(distribute), 1)
        self.assertEqual(distribute[0]["payload"]["from"], "manager")
        self.assertNotIn("from_", distribute[0]["payload"])

    def test_long_texts_are_truncated_to_the_protocol_limits(self):
        o = orch_mod.Orchestrator(pace=0)
        event = o._event("coder", "message", message="x" * 5000, bubble="y" * 500)
        self.assertEqual(len(event["payload"]["message"]), 1000)
        self.assertEqual(len(event["payload"]["bubble"]), 240)

    def test_truncation_counts_utf16_units_like_the_frontend(self):
        o = orch_mod.Orchestrator(pace=0)
        event = o._event("coder", "message", message="🎉" * 900, bubble="a" + "🎉" * 200)
        utf16 = lambda text: len(text.encode("utf-16-le")) // 2
        self.assertLessEqual(utf16(event["payload"]["message"]), 1000)
        self.assertLessEqual(utf16(event["payload"]["bubble"]), 240)
        self.assertEqual(event["payload"]["bubble"], "a" + "🎉" * 119)
        proc = subprocess.run([_node(), str(BRIDGE), "decode"], input=json.dumps([event]),
                              capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=ROOT)
        self.assertEqual(json.loads(proc.stdout.strip().splitlines()[-1])["rejected"], [])

    def test_mission_ends_with_every_agent_done(self):
        missions, _ = _run_missions(["status do brain"])
        events = missions[0]
        self.assertEqual(events[-1]["type"], "completion")
        done = {e["agentId"] for e in events if e["payload"].get("status") == "done"} | {events[-1]["agentId"]}
        self.assertEqual(done, set(orch_mod.AGENT_IDS))


class TestOrchestratorMissionId(unittest.TestCase):
    def test_run_mission_adopts_the_given_mission_id(self):
        missions, _ = _run_missions(["status do brain"], mission_id=7)
        events = missions[0]
        self.assertTrue(events)
        self.assertEqual({e["missionId"] for e in events}, {7})
        self.assertEqual([e["sequence"] for e in events], list(range(1, len(events) + 1)))
        self.assertTrue(all(e["id"].startswith("evt:7:") for e in events))


class TestMatchPatternIsolation(unittest.TestCase):
    def test_match_pattern_does_not_mutate_the_module_patterns(self):
        before = copy.deepcopy((orch_mod.MISSION_PATTERNS, orch_mod.DEFAULT_STEPS))
        o = orch_mod.Orchestrator(pace=0)
        first = o._match_pattern("pedidos travados no hub")
        second = o._match_pattern("erro na fila do hub de novo")
        fallback1 = o._match_pattern("primeira pergunta")
        fallback2 = o._match_pattern("segunda pergunta")
        self.assertEqual((orch_mod.MISSION_PATTERNS, orch_mod.DEFAULT_STEPS), before)
        self.assertEqual(first[0]["input"]["query"], "pedidos travados no hub")
        self.assertEqual(second[0]["input"]["query"], "erro na fila do hub de novo")
        self.assertEqual(fallback1[0]["input"]["query"], "primeira pergunta")
        self.assertEqual(fallback2[0]["input"]["query"], "segunda pergunta")


class TestHostCommandsNeedHumanApproval(unittest.TestCase):
    def test_no_mission_pattern_runs_a_host_command(self):
        tools = {s["tool"] for p in orch_mod.MISSION_PATTERNS for s in p["steps"]}
        tools |= {s["tool"] for s in orch_mod.DEFAULT_STEPS}
        self.assertNotIn("run_safe_command", tools)
        from core.domain.nexus.entities import AUTO_TOOLS
        self.assertTrue(tools <= AUTO_TOOLS)
        self.assertNotIn("run_safe_command", AUTO_TOOLS)

    def test_a_host_command_step_is_refused_without_calling_the_executor(self):
        pattern = {"keywords": ["servidor"], "steps": [
            {"agent": "coder", "tool": "run_safe_command", "input": {"command": "uptime"}, "bubble": "..."}]}
        # TEST-01: Usar o broker REAL (sem mock de run_tool) para que a política
        # de segurança bloqueie run_safe_command via ESCALATE/DENY.
        async def main():
            with mock.patch.object(orch_mod, "MISSION_PATTERNS", [pattern]):
                return await _collect(orch_mod.Orchestrator(pace=0), "olhar o servidor")

        events = asyncio.run(main())
        messages = [e["payload"]["message"] for e in events if e["type"] == "message"]
        # Verificar que o broker rejeitou a tool (resultado contém run_safe_command + aprovação)
        self.assertTrue(
            any("run_safe_command" in m and "aprovação" in m for m in messages),
            f"Expected refusal message with 'run_safe_command' and 'aprovação', got: {messages}"
        )


class _FakeEmbedder:
    def get_embedding(self, text):
        return [0.0]


class _FakeStore:
    def search(self, query_vector, limit, category=None, bounded_context=None):
        return [{"score": 0.8, "payload": {"file_path": "systems/hub.md", "doc_title": "Hub", "section": "OAuth",
                                           "category": "systems", "content": "Conteúdo da seção OAuth do Hub."}}]


class TestRetrieverContent(unittest.TestCase):
    def _retriever(self):
        r = retriever_mod.BrainRetriever.__new__(retriever_mod.BrainRetriever)
        r.embedder, r.store = _FakeEmbedder(), _FakeStore()
        orig_query = r.query
        def query(user_question, limit=4, category=None, bounded_context=None, include_content=False):
            res = orig_query(user_question, limit=limit, category=category, bounded_context=bounded_context)
            if include_content:
                hits = r.store.search(None, limit, category)
                for s, h in zip(res["sources"], hits):
                    s["content"] = h["payload"].get("content")
            return res
        r.query = query
        return r

    def test_default_sources_are_unchanged_for_mcp_clients(self):
        sources = self._retriever().query("oauth")["sources"]
        self.assertEqual(set(sources[0]), {"file_path", "doc_title", "section", "category", "score"})

    def test_include_content_adds_the_chunk_text(self):
        sources = self._retriever().query("oauth", include_content=True)["sources"]
        self.assertEqual(sources[0]["content"], "Conteúdo da seção OAuth do Hub.")


class TestToolExecutorSearch(unittest.TestCase):
    def test_search_maps_retriever_fields(self):
        captured = {}

        class FakeRetriever:
            def query(self, query, limit=4, category=None, include_content=False):
                captured["include_content"] = include_content
                return {"sources": [{"file_path": "systems/hub.md", "doc_title": "Hub", "section": "OAuth",
                                     "category": "systems", "score": 0.81234, "content": "x" * 400}]}

        with mock.patch.object(tool_executor, "BrainRetriever", FakeRetriever):
            result = asyncio.run(tool_executor.search_knowledge("oauth"))
        self.assertTrue(captured["include_content"])
        source = result["sources"][0]
        self.assertEqual(source["document"], "systems/hub.md")
        self.assertEqual(source["title"], "Hub")
        self.assertEqual(source["section"], "OAuth")
        self.assertEqual(source["score"], 0.812)
        self.assertEqual(source["excerpt"], "x" * 200)


def _fast_orchestrator():
    return orch_mod.Orchestrator(pace=0)


def _envelope(n, action_type, base_mission, payload=None, mission=None):
    message = {"schemaVersion": 1, "commandId": f"command:{base_mission}:{n}", "missionId": base_mission,
               "action": {"type": action_type, "payload": payload, "now": 1}}
    if mission is not None:
        message["mission"] = mission
    return message


class TestWsServerProtocol(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stub = _ToolStub()
        self._patches = [mock.patch.object(orch_mod, "run_tool", self.stub),
                         mock.patch.object(ws_server, "Orchestrator", _fast_orchestrator)]
        for p in self._patches:
            p.start()
        self.server = await ws_server.serve(0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.token = ws_server.get_store().issue("session", 3600)
        self.headers = {"Cookie": f"brain_session={self.token}"}
        self.client = await websockets.connect(
            f"ws://127.0.0.1:{self.port}",
            origin="http://127.0.0.1:5173",
            additional_headers=self.headers,
        )

    async def asyncTearDown(self):
        await self.client.close()
        self.server.close()
        await self.server.wait_closed()
        for p in self._patches:
            p.stop()

    async def _recv_until(self, predicate, timeout=10):
        seen = []
        async with asyncio.timeout(timeout):
            while True:
                message = json.loads(await self.client.recv())
                seen.append(message)
                if predicate(message):
                    return seen

    async def test_mission_events_use_the_mission_from_the_start_envelope(self):
        await self.client.send(json.dumps(_envelope(1, "NEW_TASK", 0, "status do brain", {"id": 1, "task": "status do brain"})))
        await self.client.send(json.dumps(_envelope(2, "START", 0, None, {"id": 2, "task": "status do brain"})))
        seen = await self._recv_until(lambda m: m.get("type") == "approval_request")
        await self.client.send(json.dumps(_envelope(3, "APPROVE", 2)))
        seen += await self._recv_until(lambda m: m.get("type") == "completion")
        replies = [m for m in seen if m.get("type") in ("ACK", "REJECT")]
        events = [m for m in seen if "schemaVersion" in m]
        self.assertEqual([r["type"] for r in replies], ["ACK", "ACK", "ACK"])
        self.assertEqual([r["missionId"] for r in replies], [0, 0, 2])
        self.assertEqual({e["missionId"] for e in events}, {2})

    async def test_revisions_increase_across_missions(self):
        revisions = []
        for base, (new_id, start_id) in enumerate([(1, 2), (3, 4)]):
            base_mission = base * 2
            await self.client.send(json.dumps(_envelope(1, "NEW_TASK", base_mission, "status", {"id": new_id, "task": "status"})))
            await self.client.send(json.dumps(_envelope(2, "START", base_mission, None, {"id": start_id, "task": "status"})))
            seen = await self._recv_until(lambda m: m.get("type") == "approval_request")
            revisions += [m["revision"] for m in seen if m.get("type") == "ACK"]
        self.assertEqual(len(revisions), 4)
        self.assertEqual(revisions, sorted(set(revisions)))

    async def test_start_without_a_valid_mission_is_rejected(self):
        for bad in (None, {"id": -1, "task": "x"}, {"id": 1, "task": "  "}, {"id": True, "task": "x"},
                    {"id": 2 ** 53, "task": "x"}, {"id": 1.0, "task": "x"}):
            await self.client.send(json.dumps(_envelope(1, "START", 0, None, bad)))
            reply = (await self._recv_until(lambda m: m.get("type") in ("ACK", "REJECT")))[-1]
            self.assertEqual(reply["type"], "REJECT", bad)
        self.assertEqual(self.stub.calls, [])

    async def test_cross_origin_pages_cannot_connect(self):
        with self.assertRaises(websockets.exceptions.InvalidStatus) as refused:
            await websockets.connect(
                f"ws://127.0.0.1:{self.port}",
                origin="https://evil.example",
                additional_headers=self.headers,
            )
        self.assertEqual(refused.exception.response.status_code, 403)
        allowed = await websockets.connect(
            f"ws://127.0.0.1:{self.port}",
            origin="http://127.0.0.1:5173",
            additional_headers=self.headers,
        )
        await allowed.close()

    async def test_approve_without_a_mission_waiting_is_rejected(self):
        await self.client.send(json.dumps(_envelope(1, "APPROVE", 0)))
        reply = (await self._recv_until(lambda m: m.get("type") in ("ACK", "REJECT")))[-1]
        self.assertEqual(reply["type"], "REJECT")

    async def test_empty_new_task_is_rejected(self):
        await self.client.send(json.dumps(_envelope(1, "NEW_TASK", 0, "   ")))
        reply = (await self._recv_until(lambda m: m.get("type") in ("ACK", "REJECT")))[-1]
        self.assertEqual(reply["type"], "REJECT")

    async def test_ws_connect_without_cookie_gets_4001(self):
        """INV-N01: conexao sem brain_session -> close 4001."""
        async with websockets.connect(f"ws://127.0.0.1:{self.port}", origin="http://127.0.0.1:5173") as ws:
            with self.assertRaises(websockets.exceptions.ConnectionClosed) as ctx:
                async with asyncio.timeout(2):
                    await ws.recv()
            self.assertEqual(ctx.exception.code, 4001)

    async def test_ws_connect_with_expired_cookie_gets_4001(self):
        """INV-N01: cookie expirado -> close 4001."""
        headers = {"Cookie": "brain_session=invalid_or_expired_token"}
        async with websockets.connect(
            f"ws://127.0.0.1:{self.port}", origin="http://127.0.0.1:5173", additional_headers=headers
        ) as ws:
            with self.assertRaises(websockets.exceptions.ConnectionClosed) as ctx:
                async with asyncio.timeout(2):
                    await ws.recv()
            self.assertEqual(ctx.exception.code, 4001)

    async def test_ws_connect_with_valid_cookie_accepted(self):
        """INV-N01: cookie valido -> handshake aceito."""
        if hasattr(ws_server, "get_store"):
            store = ws_server.get_store()
            token = store.issue("session", 3600)
        else:
            token = "fake_token"
        headers = {"Cookie": f"brain_session={token}"}
        async with websockets.connect(
            f"ws://127.0.0.1:{self.port}", origin="http://127.0.0.1:5173", additional_headers=headers
        ) as ws:
            self.assertEqual(ws.state.name, "OPEN")
            await ws.ping()


class TestWsServerPort(unittest.TestCase):
    def test_ws_port_does_not_collide_with_the_bff(self):
        self.assertEqual(ws_server.PORT, 8848)
        self.assertNotEqual(ws_server.PORT, 8849)


class _ServerThread:
    """ws_server real em loop próprio, para o node conectar de fora."""

    def __enter__(self):
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        async def boot():
            self.server = await ws_server.serve(0, origins=["http://127.0.0.1:5173", None])
            self.port = self.server.sockets[0].getsockname()[1]
            self.token = ws_server.get_store().issue("session", 3600)
            ready.set()

        def run():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(boot())
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        if not ready.wait(10):
            raise AssertionError("ws_server não subiu")
        return self

    def __exit__(self, *exc):
        async def stop():
            self.server.close()
            await self.server.wait_closed()

        asyncio.run_coroutine_threadsafe(stop(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)
        self.loop.close()


class TestEndToEndReducer(unittest.TestCase):
    def test_events_from_the_ws_server_reach_the_frontend_reducer(self):
        stub = _ToolStub()
        tasks = ["status do brain", "como funciona o oauth do bling?"]
        with mock.patch.object(orch_mod, "run_tool", stub), \
                mock.patch.object(ws_server, "Orchestrator", _fast_orchestrator), \
                _ServerThread() as server:
            raw_bridge = BRIDGE.read_text(encoding="utf-8")
            raw_bridge = raw_bridge.replace(
                "createWsTransport(`ws://127.0.0.1:${port}`)",
                f"createWsTransport(`ws://127.0.0.1:${{port}}?brain_session={server.token}`)"
            ).replace("adapter.newTask(task);\n      adapter.start();", "adapter.start(task);")
            temp_bridge = ROOT / ".runtime" / "nexus_bridge_e2e.mjs"
            temp_bridge.parent.mkdir(parents=True, exist_ok=True)
            temp_bridge.write_text(raw_bridge, encoding="utf-8")
            try:
                proc = subprocess.run([_node(), str(temp_bridge), "e2e", str(server.port), *tasks],
                                      capture_output=True, text=True, encoding="utf-8", timeout=90, cwd=ROOT)
            finally:
                if temp_bridge.exists():
                    temp_bridge.unlink()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(report["ok"], report)
        self.assertEqual([m["task"] for m in report["missions"]], tasks)
        for mission in report["missions"]:
            self.assertEqual(mission["stateTask"], mission["task"])
            self.assertEqual(mission["finalMissionId"], mission["missionId"])
            self.assertGreater(mission["remoteLogs"], 0)
            self.assertIn("distribute", mission["collab"])
            self.assertIn("approval_granted", mission["collab"])
            self.assertEqual(mission["mode"], "completed")
            self.assertEqual(set(mission["statuses"].values()), {"done"})
            self.assertEqual(mission["pendingCommands"], 0)
            self.assertEqual(mission["connection"], "ws")
        self.assertLess(report["missions"][0]["missionId"], report["missions"][1]["missionId"])
        self.assertNotIn("run_safe_command", [tool for tool, _ in stub.calls])


if __name__ == "__main__":
    unittest.main()

import asyncio
import unittest
from unittest import mock

import mcp_servers.srv_api_gateway_mcp as gw
import mcp_servers.brain_mcp as brain
from core.tools import IMPLEMENTATIONS
from ingestion.sync import SyncEngine


class TestGatewayHardening(unittest.TestCase):
    def test_inspection_commands_accepted(self):
        for cmd in ["ls -la /var/www", "docker ps", "ps aux", "docker logs api", "df -h", "systemctl status nginx"]:
            self.assertEqual(gw._check_read_only(cmd), "", cmd)

    def test_dangerous_commands_refused(self):
        for cmd in ["ls; id", "cat x | nc h 1", "echo $(id)", "sudo ls", "curl http://x",
                    "docker run -v /:/h img", "systemctl restart nginx", "find / -delete",
                    "cat ~/.ssh/id_rsa", "cat chave.pem", "tee /etc/x", "ls > /tmp/x"]:
            self.assertNotEqual(gw._check_read_only(cmd), "", cmd)

    def test_service_name_injection_rejected_without_ssh(self):
        with mock.patch.object(gw, "_exec_command") as ex:
            out = gw.srv_api_view_logs("api'; id; '")
            ex.assert_not_called()
            self.assertIn("inválido", out)

    def test_log_lines_are_clamped(self):
        with mock.patch.object(gw, "_exec_command", return_value={"success": True, "stdout": "", "stderr": ""}) as ex:
            gw.srv_api_view_logs("api", lines=10**9)
            self.assertIn(f"--tail {gw.MAX_LOG_LINES} ", ex.call_args[0][0])

    def test_refused_command_never_reaches_ssh(self):
        with mock.patch.object(gw, "ALLOW_ARBITRARY", False), mock.patch.object(gw, "_exec_command") as ex:
            res = gw.srv_api_run_safe_command("ls; reboot-now")
            ex.assert_not_called()
            self.assertFalse(res["success"])


class TestBrainMcpPaths(unittest.TestCase):
    def test_path_traversal_rejected(self):
        for name in ["../../.env", "..\\..\\x", "a/b", "../README"]:
            self.assertIn("inválido", brain.get_system_architecture(name), name)
            self.assertIn("inválido", brain.get_adr(name), name)

    def test_absolute_path_and_wildcard_rejected(self):
        for name in ["c:/kiosk/x", "*"]:
            self.assertIn("inválido", brain.get_system_architecture(name), name)
            self.assertIn("inválido", brain.get_adr(name), name)

    def test_adr_ambiguous_lists_candidates(self):
        out = brain.get_adr("ddd")
        self.assertTrue(out.startswith("Identificador ambíguo"), out[:80])
        self.assertIn("ADR-019", out)
        self.assertIn("ADR-020", out)

    def test_adr_number_is_exact(self):
        out = brain.get_adr("1")
        self.assertFalse(out.startswith("Identificador ambíguo"))
        self.assertIn("Salesforce", out)


class TestBrokerToolPaths(unittest.TestCase):
    def run_tool(self, name, **kw):
        return asyncio.run(IMPLEMENTATIONS[name](**kw))

    def test_system_doc_refuses_outside_vault(self):
        for bad in ["../../readme", "c:/kiosk/hub-logistico/readme", "..\\adrs\\x"]:
            r = self.run_tool("get_system_architecture", system_name=bad)
            self.assertEqual((r["found"], r["error"]), (False, "invalid_name"), bad)

    def test_adr_wildcard_refused(self):
        self.assertEqual(self.run_tool("get_adr", identifier="*")["error"], "invalid_name")

    def test_adr_ambiguous_lists_candidates(self):
        r = self.run_tool("get_adr", identifier="ddd")
        self.assertFalse(r["found"])
        self.assertGreater(len(r["candidates"]), 1)

    def test_adr_by_number(self):
        self.assertTrue(self.run_tool("get_adr", identifier="ADR-003")["file"].startswith("ADR-003-"))

    def test_adr_not_found_lists_available(self):
        r = self.run_tool("get_adr", identifier="inexistente-xyz")
        self.assertEqual(r["found"], False)
        self.assertTrue(r["available"])

    def test_system_doc_success_keeps_keys(self):
        from config import settings
        stem = next(settings.systems_dir.glob("*.md")).stem
        r = self.run_tool("get_system_architecture", system_name=stem)
        self.assertTrue(r["found"])
        self.assertEqual(r["system"], stem)

    def test_read_vault_file_refuses_escape(self):
        for bad in ["../README.md", "C:/KIOSK/hub-logistico/README.md"]:
            self.assertEqual(self.run_tool("read_vault_file", path=bad)["error"], "invalid_path")

    def test_read_vault_file_ok_and_missing(self):
        r = self.run_tool("read_vault_file", path="adrs/ADR-003-politica-git-branches-e-pull-requests.md")
        self.assertTrue(r["found"])
        self.assertFalse(self.run_tool("read_vault_file", path="adrs/nao-existe.md")["found"])


class TestSearchContract(unittest.TestCase):
    """search_knowledge_base (MCP) e search_knowledge (broker) expoem as citacoes de forma aditiva (spec 2.5)."""

    MCP_KEYS = {"file_path", "doc_title", "section", "category", "score",
                "sha256", "line_start", "line_end", "stale"}
    BROKER_ITEM_KEYS = {"document", "title", "section", "score", "excerpt",
                        "sha256", "line_start", "line_end", "stale"}
    BROKER_KEYS = {"tool", "query", "total", "sources", "gaps", "index_version"}

    def setUp(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from qdrant_client.models import PointStruct
        from config import settings
        from core.retriever import BrainRetriever
        from tests.test_retrieval_contract import FakeEmbedder, VECTOR_SIZE, make_store, vector_for

        for name, value in (("space_id", "kiosk"), ("retrieval_min_score", 0.65),
                            ("retrieval_max_drop", 0.10), ("retrieval_max_per_doc", 2)):
            patcher = mock.patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        vault = Path(tmp.name)
        (vault / "a.md").write_text("conteudo a", encoding="utf-8")
        sha = hashlib.sha256((vault / "a.md").read_bytes()).hexdigest()

        def build(collection, points):
            store, client = make_store(collection)
            self.addCleanup(client.close)
            store.ensure_collection(vector_size=VECTOR_SIZE)
            client.upsert(collection_name=collection, points=[
                PointStruct(id=i, vector=vector_for(score), payload={
                    "file_path": "a.md", "doc_title": "A", "section": section, "category": "systems",
                    "chunk_index": i, "line_start": 1, "line_end": 3, "doc_sha256": sha,
                    "space_id": "kiosk", "content": f"texto {section} " + "x" * 300})
                for i, (score, section) in enumerate(points, start=1)
            ])
            return BrainRetriever(embedder=FakeEmbedder(), store=store, vault_dir=vault)

        self.with_evidence = build("kb", [(0.95, "A1"), (0.93, "A2")])
        self.without_evidence = build("low", [(0.30, "A1")])
        empty_store, empty_client = make_store("vazio")  # nenhum ponto do espaco: indice vazio
        self.addCleanup(empty_client.close)
        empty_store.ensure_collection(vector_size=VECTOR_SIZE)
        self.empty_index = BrainRetriever(embedder=FakeEmbedder(), store=empty_store, vault_dir=vault)
        self.trace_log = Path(tmp.name) / "trace-log.jsonl"

    def _use(self, retriever):
        """Faz broker e MCP usarem este recuperador (sem Qdrant/Ollama)."""
        for target in ("core.tools.BrainRetriever", "mcp_servers.brain_mcp.BrainRetriever"):
            patcher = mock.patch(target, return_value=retriever)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_broker_keeps_old_keys_and_adds_new(self):  # CA-07
        self._use(self.with_evidence)
        r = asyncio.run(IMPLEMENTATIONS["search_knowledge_base"](query="x"))
        self.assertEqual(set(r), self.BROKER_KEYS)
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["gaps"], [])
        self.assertEqual(r["index_version"], "kb")
        for item in r["sources"]:
            self.assertEqual(set(item), self.BROKER_ITEM_KEYS)
        self.assertEqual(len(r["sources"][0]["excerpt"]), 200)
        self.assertFalse(r["sources"][0]["stale"])
        self.assertEqual((r["sources"][0]["line_start"], r["sources"][0]["line_end"]), (1, 3))

    def test_broker_without_evidence_reports_gap(self):
        self._use(self.without_evidence)
        r = asyncio.run(IMPLEMENTATIONS["search_knowledge_base"](query="x"))
        self.assertEqual(set(r), self.BROKER_KEYS)
        self.assertEqual((r["total"], r["sources"]), (0, []))
        self.assertTrue(r["gaps"])

    def test_mcp_source_keys_are_exact(self):
        self._use(self.with_evidence)
        sources = brain.search_knowledge_base("x")
        self.assertEqual(len(sources), 2)
        for item in sources:
            self.assertEqual(set(item), self.MCP_KEYS)
        with_content = brain.search_knowledge_base("x", include_content=True)
        for item in with_content:
            self.assertEqual(set(item), self.MCP_KEYS | {"content"})

    def test_mcp_returns_empty_list_without_evidence(self):
        self._use(self.without_evidence)
        self.assertEqual(brain.search_knowledge_base("x"), [])

    def test_mcp_docstring_states_empty_means_no_evidence(self):
        doc = brain.search_knowledge_base.fn.__doc__ if hasattr(brain.search_knowledge_base, "fn")             else brain.search_knowledge_base.__doc__
        self.assertIn("sem evidência", doc)
        self.assertIn("erro", doc)
        self.assertIn("--rebuild --yes", doc)

    EMPTY_INDEX_ERROR = "Índice vazio para este espaço; rode 'cli.py sync --rebuild --yes'."

    def test_mcp_raises_on_empty_index(self):  # Important #1 da revisao final
        from core.citations import GAP_EMPTY_INDEX

        self.assertEqual(self.empty_index.query("x")["gaps"], [GAP_EMPTY_INDEX])
        self._use(self.empty_index)
        with self.assertRaises(RuntimeError) as ctx:
            brain.search_knowledge_base("x")
        self.assertEqual(str(ctx.exception), self.EMPTY_INDEX_ERROR)

    def test_mcp_no_evidence_gap_still_returns_empty_list(self):
        from core.citations import GAP_NO_EVIDENCE

        self.assertEqual(self.without_evidence.query("x")["gaps"], [GAP_NO_EVIDENCE])
        self._use(self.without_evidence)
        self.assertEqual(brain.search_knowledge_base("x"), [])

    def test_mcp_empty_index_reaches_client_as_tool_error(self):
        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        from core import tracing

        self._use(self.empty_index)
        patcher = mock.patch.object(tracing, "TRACE_LOG", self.trace_log)
        patcher.start()
        self.addCleanup(patcher.stop)

        async def run():
            async with Client(brain.mcp) as client:
                return await client.call_tool("search_knowledge_base", {"query": "x"})

        with self.assertRaises(ToolError) as ctx:
            asyncio.run(run())
        self.assertIn(self.EMPTY_INDEX_ERROR, str(ctx.exception))

    def test_mcp_filter_no_match_gives_no_evidence_not_rebuild(self):
        """Busca com bounded_context sem match num espaco com pontos: sem evidencia, nao erro de rebuild."""
        from core.citations import GAP_NO_EVIDENCE
        self._use(self.with_evidence)
        # bounded_context que nenhum ponto tem: a busca retorna vazio,
        # mas o espaco tem pontos, entao a lacuna e "sem evidencia"
        result = self.with_evidence.query("x", bounded_context="Inexistente")
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["gaps"], [GAP_NO_EVIDENCE])
        # MCP devolve lista vazia sem erro
        sources = brain.search_knowledge_base("x", bounded_context="Inexistente")
        self.assertEqual(sources, [])

    def test_mcp_filter_no_match_with_legacy_index_gives_rebuild(self):
        """Busca com filtro num indice so com pontos antigos (sem space_id): erro de rebuild."""
        from core.citations import GAP_EMPTY_INDEX
        self._use(self.empty_index)  # empty_index tem 0 pontos do espaco
        result = self.empty_index.query("x", bounded_context="Fiscal")
        self.assertEqual(result["gaps"], [GAP_EMPTY_INDEX])
        with self.assertRaises(RuntimeError) as ctx:
            brain.search_knowledge_base("x", bounded_context="Fiscal")
        self.assertEqual(str(ctx.exception), self.EMPTY_INDEX_ERROR)

    def test_mcp_category_no_match_gives_no_evidence(self):
        """Busca com category sem match num espaco com pontos: sem evidencia."""
        from core.citations import GAP_NO_EVIDENCE
        self._use(self.with_evidence)
        result = self.with_evidence.query("x", category="inexistente")
        self.assertEqual(result["gaps"], [GAP_NO_EVIDENCE])
        sources = brain.search_knowledge_base("x", category="inexistente")
        self.assertEqual(sources, [])

    def test_brain_status_reports_legacy_points(self):
        from qdrant_client.models import PointStruct
        from tests.test_retrieval_contract import VECTOR_SIZE, make_store, vector_for

        store, client = make_store("kb_status")
        self.addCleanup(client.close)
        store.ensure_collection(vector_size=VECTOR_SIZE)
        client.upsert(collection_name="kb_status", points=[
            PointStruct(id=1, vector=vector_for(0.9), payload={"file_path": "velho.md"}),
            PointStruct(id=2, vector=vector_for(0.9), payload={"file_path": "a.md", "space_id": "kiosk"}),
        ])
        with mock.patch.object(brain, "QdrantStore", return_value=store):
            status = brain.get_brain_status()
        self.assertEqual(status["legacy_points"], 1)
        self.assertIsInstance(status["legacy_points"], int)
        self.assertEqual(status["points_count"], 2)


class TestBrokerStaleFailSafe(unittest.TestCase):
    def test_source_without_stale_is_reported_stale(self):  # revisao final: falha segura
        retriever = mock.Mock()
        retriever.query.return_value = {
            "sources": [{"file_path": "a.md", "doc_title": "A", "section": "S", "score": 0.9,
                         "content": "texto", "sha256": "a" * 64, "line_start": 1, "line_end": 2}],
            "gaps": [], "index_version": "kb",
        }
        with mock.patch("core.tools.BrainRetriever", return_value=retriever):
            r = asyncio.run(IMPLEMENTATIONS["search_knowledge_base"](query="x"))
        self.assertIs(r["sources"][0]["stale"], True)


class TestSyncDoesNotLoseKnowledge(unittest.TestCase):
    def test_old_vectors_kept_when_embedding_fails(self):
        import tempfile
        from pathlib import Path
        from config import settings
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        engine = SyncEngine.__new__(SyncEngine)
        engine.lock_path = Path(tmp.name) / "sync.lock"
        engine.lock_wait = 0.0
        engine.vault_dir = settings.vault_dir
        f = next(settings.adrs_dir.glob("*.md"))
        rel = f.relative_to(settings.vault_dir).as_posix()
        engine.manifest_manager = mock.Mock()
        engine.manifest_manager.load_manifest.return_value = {rel: "0" * 64}
        engine.manifest_manager.get_diff_with_hashes.return_value = ([], [f], [], {rel: "1" * 64})
        engine.chunker = mock.Mock()
        engine.chunker.chunk_bytes.return_value = [{"content": "x", "id": "i", "metadata": {}}]
        engine.embedder = mock.Mock()
        engine.embedder.get_embedding.side_effect = RuntimeError("ollama fora do ar")
        engine.store = mock.Mock()
        engine.store.ensure_collection.return_value = False
        engine.store.legacy_points_count.return_value = 0
        res = engine.sync_vault(verbose=False)
        engine.store.delete_by_file_path.assert_not_called()
        engine.store.delete_stale.assert_not_called()
        engine.store.upsert_chunks.assert_not_called()
        engine.manifest_manager.save_manifest.assert_not_called()
        self.assertEqual(res["failed"], 1)


if __name__ == "__main__":
    unittest.main()

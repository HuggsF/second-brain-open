"""Testes de consistencia vault -> Qdrant (onda A)."""
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import settings
from core.chunker import MarkdownChunker
from core.hasher import ManifestError, ManifestManager
from core.qdrant_store import QdrantStore
from core.sync_lock import SyncBusy, sync_lock
from ingestion.sync import MigrationNeedsConfirmation, SyncEngine


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


THREE_SECTIONS = "## S1\n\ntexto um\n\n## S2\n\ntexto dois\n\n## S3\n\ntexto tres\n"
ONE_SECTION = "## S1\n\ntexto novo\n"


class TestManifest(unittest.TestCase):
    def setUp(self):
        self._vault_tmp = tempfile.TemporaryDirectory()
        self._manifest_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._vault_tmp.cleanup)
        self.addCleanup(self._manifest_tmp.cleanup)
        self.vault = Path(self._vault_tmp.name)
        self.path = Path(self._manifest_tmp.name) / "manifest.json"
        self.mm = ManifestManager(manifest_path=self.path)
        (self.vault / "a.md").write_text("conteudo a", encoding="utf-8")

    def test_missing_manifest_is_empty(self):
        self.assertEqual(self.mm.load_manifest(), {})

    def test_unreadable_manifest_raises(self):
        for raw in ['{"a.md": "trunc', "[]", '{"a.md": 1}']:
            with self.subTest(raw=raw):
                self.path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ManifestError) as ctx:
                    self.mm.load_manifest()
                self.assertIn(str(self.path), str(ctx.exception))

    def test_interrupted_save_keeps_previous(self):  # CA-04
        self.mm.save_manifest({"a.md": "1" * 64})
        with mock.patch("core.hasher.os.replace", side_effect=OSError("queda")):
            with self.assertRaises(OSError):
                self.mm.save_manifest({"b.md": "2" * 64})
        self.assertEqual(self.mm.load_manifest(), {"a.md": "1" * 64})

    def test_diff_returns_hashes(self):
        added, modified, deleted, hashes = self.mm.get_diff_with_hashes(self.vault)
        expected = hashlib.sha256((self.vault / "a.md").read_bytes()).hexdigest()
        self.assertEqual(hashes["a.md"], expected)
        self.assertEqual([p.name for p in added], ["a.md"])
        self.assertEqual((modified, deleted), ([], []))

    def test_get_diff_keeps_three_items(self):
        self.assertEqual(len(self.mm.get_diff(self.vault)), 3)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.client = QdrantClient(location=":memory:")
        self.addCleanup(self.client.close)
        with mock.patch("core.qdrant_store.QdrantClient", return_value=self.client):
            self.store = QdrantStore(url="http://qdrant.invalid", collection_name="kb")

    def _chunks(self, rel_path, n):
        return [
            {"id": f"{rel_path}:{i}", "content": f"c{i}", "metadata": {"file_path": rel_path}}
            for i in range(n)
        ]

    def _load(self, rel_path, n):
        chunks = self._chunks(rel_path, n)
        self.store.upsert_chunks(chunks, [[1.0, 0.0, 0.0, 0.0]] * n)

    def test_ensure_collection_reports_creation(self):
        self.assertTrue(self.store.ensure_collection(4))
        self.assertFalse(self.store.ensure_collection(4))

    def test_ensure_collection_respects_alias(self):  # Emenda E1
        self.client.create_collection("kb__1", vectors_config=VectorParams(size=4, distance=Distance.COSINE))
        self.store.swap_alias("kb", "kb__1", has_old_alias=False)
        self.assertFalse(self.store.ensure_collection(4))
        self.assertNotIn("kb", [c.name for c in self.client.get_collections().collections])

    def test_delete_stale_keeps_new_and_other_files(self):
        self.store.ensure_collection(4)
        self._load("a.md", 3)
        self._load("b.md", 1)
        self.store.delete_stale("a.md", self.store.point_ids([{"id": "a.md:0"}]))
        self.assertEqual(self.store.indexed_files(), {"a.md": 1, "b.md": 1})

    def test_delete_stale_empty_keep_removes_whole_file(self):
        self.store.ensure_collection(4)
        self._load("a.md", 2)
        self._load("b.md", 1)
        self.store.delete_stale("a.md", set())
        self.assertEqual(self.store.indexed_files(), {"b.md": 1})

    def test_point_ids_match_upsert_rule(self):
        self.store.ensure_collection(4)
        self._load("a.md", 2)
        stored = {str(p.id) for p in self.client.scroll("kb", limit=10)[0]}
        self.assertEqual(self.store.point_ids(self._chunks("a.md", 2)), stored)

    def test_indexed_files_paginates(self):
        self.store.ensure_collection(4)
        for name, n in (("a.md", 300), ("b.md", 200), ("c.md", 100)):
            self._load(name, n)
        files = self.store.indexed_files()
        self.assertEqual(sum(files.values()), 600)
        self.assertEqual(files, {"a.md": 300, "b.md": 200, "c.md": 100})

    def test_alias_helpers(self):
        self.assertIsNone(self.store.alias_target("kb"))
        self.store.create_named_collection("kb__1", 4)
        self.store.create_named_collection("kb__2", 4)
        self.assertTrue(self.store.is_real_collection("kb__1"))
        self.assertFalse(self.store.is_real_collection("kb"))
        self.store.swap_alias("kb", "kb__1", has_old_alias=False)
        self.assertEqual(self.store.alias_target("kb"), "kb__1")
        self.assertFalse(self.store.is_real_collection("kb"))
        self.store.swap_alias("kb", "kb__2", has_old_alias=True)
        self.assertEqual(self.store.alias_target("kb"), "kb__2")
        self.assertEqual(sorted(self.store.collections_with_prefix("kb__")), ["kb__1", "kb__2"])
        self.store.drop_collection("kb__1")
        self.assertEqual(self.store.collections_with_prefix("kb__"), ["kb__2"])


class TestChunkBytes(unittest.TestCase):
    def test_crlf_bytes_match_text_mode_reading(self):
        raw = "## S1\r\n\r\ntexto um\r\n".encode("utf-8")
        chunks = MarkdownChunker().chunk_bytes(raw, "a.md")
        self.assertEqual(len(chunks), 1)
        self.assertNotIn("\r", chunks[0]["content"])
        self.assertEqual(chunks[0]["metadata"]["section"], "S1")

    def test_category_is_immediate_parent_like_chunk_file(self):
        chunker = MarkdownChunker()
        cases = {"a.md": "general", "adrs/x.md": "adrs", "architecture/full-cycle/x.md": "full-cycle"}
        for rel, category in cases.items():
            with self.subTest(rel=rel):
                chunks = chunker.chunk_bytes(ONE_SECTION.encode("utf-8"), rel)
                self.assertEqual(chunks[0]["metadata"]["category"], category)
                self.assertEqual(chunks[0]["metadata"]["file_path"], rel)
                self.assertEqual(chunks[0]["metadata"]["doc_title"], "X" if rel != "a.md" else "A")


class FakeEmbedder:
    def get_embedding(self, text):
        return [0.1] * settings.vector_size


class SyncTestBase(unittest.TestCase):
    """Qdrant em memoria, vault/manifesto/lock temporarios e embedder falso."""

    def setUp(self):
        vault_tmp = tempfile.TemporaryDirectory()
        state_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(vault_tmp.cleanup)
        self.addCleanup(state_tmp.cleanup)
        self.vault = Path(vault_tmp.name)
        state = Path(state_tmp.name)
        self.manifest_path = state / "manifest.json"

        self.client = QdrantClient(location=":memory:")
        self.addCleanup(self.client.close)
        with mock.patch("core.qdrant_store.QdrantClient", return_value=self.client):
            self.engine = SyncEngine(lock_path=state / "run" / "sync.lock", lock_wait=0.0)
            self.store = QdrantStore(url="http://qdrant.invalid", collection_name="kb")
        self.engine.store = self.store
        self.engine.embedder = FakeEmbedder()
        self.engine.manifest_manager = ManifestManager(manifest_path=self.manifest_path)
        self.engine.vault_dir = self.vault

        (self.vault / "a.md").write_text(THREE_SECTIONS, encoding="utf-8")

    def manifest(self):
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))


class TestIncrementalSync(SyncTestBase):
    def index_initial(self):
        res = self.engine.sync_vault(verbose=False)
        self.assertEqual(res["failed"], 0)
        self.assertEqual(self.store.indexed_files(), {"a.md": 3})

    def test_hash_written_is_hash_indexed(self):  # CA-06
        self.indexed_bytes = {}
        real = self.engine.chunker.chunk_bytes

        def spy(raw, rel_path, *args, **kwargs):
            self.indexed_bytes[rel_path] = raw
            # edicao concorrente: o arquivo muda no disco enquanto o sync indexa
            (self.vault / rel_path).write_text(ONE_SECTION, encoding="utf-8")
            return real(raw, rel_path, *args, **kwargs)

        with mock.patch.object(self.engine.chunker, "chunk_bytes", side_effect=spy):
            self.engine.sync_vault(verbose=False)
        self.assertEqual(self.manifest()["a.md"], sha256(self.indexed_bytes["a.md"]))
        self.assertEqual(self.store.indexed_files(), {"a.md": 3})
        # o proximo sync percebe a edicao e reindexa
        res = self.engine.sync_vault(verbose=False)
        self.assertEqual((res["modified"], res["chunks_indexed"]), (1, 1))
        self.assertEqual(self.store.indexed_files(), {"a.md": 1})

    def test_edit_between_diff_and_read_records_new_bytes(self):  # CA-06 / INV-N05
        mm = self.engine.manifest_manager
        real = mm.get_diff_with_hashes

        def diff_then_edit(*args, **kwargs):
            result = real(*args, **kwargs)
            (self.vault / "a.md").write_text(ONE_SECTION, encoding="utf-8")
            return result

        with mock.patch.object(mm, "get_diff_with_hashes", side_effect=diff_then_edit):
            self.engine.sync_vault(verbose=False)
        self.assertEqual(self.manifest()["a.md"], sha256((self.vault / "a.md").read_bytes()))
        self.assertEqual(self.store.indexed_files(), {"a.md": 1})

    def test_shrinking_file_never_has_zero_points(self):  # CA-07 / INV-N06
        self.index_initial()
        (self.vault / "a.md").write_text(ONE_SECTION, encoding="utf-8")
        self.points_seen_before_delete = 0
        self.points_seen_before_upsert = 0
        real_delete = self.store.delete_stale
        real_upsert = self.store.upsert_chunks

        def delete_spy(rel_path, keep_ids):
            self.points_seen_before_delete = self.store.indexed_files().get("a.md", 0)
            return real_delete(rel_path, keep_ids)

        def upsert_spy(chunks, vectors):
            self.points_seen_before_upsert = self.store.indexed_files().get("a.md", 0)
            return real_upsert(chunks, vectors)

        with mock.patch.object(self.store, "delete_stale", side_effect=delete_spy), \
                mock.patch.object(self.store, "upsert_chunks", side_effect=upsert_spy):
            res = self.engine.sync_vault(verbose=False)
        self.assertEqual(res["failed"], 0)
        self.assertGreater(self.points_seen_before_upsert, 0)
        self.assertGreater(self.points_seen_before_delete, 0)
        self.assertEqual(self.store.indexed_files()["a.md"], 1)

    def test_renamed_note_moves_index(self):  # Review Focus 1
        self.index_initial()
        (self.vault / "a.md").rename(self.vault / "b.md")
        self.engine.sync_vault(verbose=False)
        self.assertEqual(set(self.store.indexed_files()), {"b.md"})
        self.assertEqual(set(self.manifest()), {"b.md"})

    def test_unreadable_manifest_touches_nothing(self):  # CA-03
        self.index_initial()
        self.before = self.store.indexed_files()
        (self.vault / "a.md").write_text(ONE_SECTION, encoding="utf-8")
        self.manifest_path.write_text("{", encoding="utf-8")
        with self.assertRaises(ManifestError):
            self.engine.sync_vault(verbose=False)
        self.assertEqual(self.store.indexed_files(), self.before)

    def test_qdrant_down_leaves_manifest(self):  # Review Focus 5
        self.index_initial()
        self.manifest_before = self.manifest_path.read_bytes()
        (self.vault / "a.md").write_text(ONE_SECTION, encoding="utf-8")
        with mock.patch.object(self.store, "ensure_collection", side_effect=ConnectionError("fora")):
            with self.assertRaises(ConnectionError):
                self.engine.sync_vault(verbose=False)
        self.assertEqual(self.manifest_path.read_bytes(), self.manifest_before)

    def test_delete_stale_failure_keeps_manifest(self):  # spec 6.2
        self.index_initial()
        old_hash = self.manifest()["a.md"]
        (self.vault / "a.md").write_text(ONE_SECTION, encoding="utf-8")
        with mock.patch.object(self.store, "delete_stale", side_effect=RuntimeError("fora")):
            res = self.engine.sync_vault(verbose=False)
        self.assertEqual((res["failed"], res["failed_files"]), (1, ["a.md"]))
        self.assertEqual(self.manifest()["a.md"], old_hash)
        # o proximo sync repete e limpa o que sobrou
        self.engine.sync_vault(verbose=False)
        self.assertEqual(self.store.indexed_files(), {"a.md": 1})

    def test_emptied_file_loses_points_and_records_hash(self):
        self.index_initial()
        (self.vault / "a.md").write_text("", encoding="utf-8")
        res = self.engine.sync_vault(verbose=False)
        self.assertEqual(res["failed"], 0)
        self.assertEqual(self.store.indexed_files(), {})
        self.assertEqual(self.manifest()["a.md"], sha256(b""))

    def test_busy_lock_raises(self):
        with sync_lock(self.engine.lock_path):
            with self.assertRaises(SyncBusy):
                self.engine.sync_vault(verbose=False)
        self.assertFalse(self.manifest_path.exists())

    def test_undecodable_note_goes_to_failed(self):
        (self.vault / "ruim.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
        res = self.engine.sync_vault(verbose=False)
        self.assertEqual((res["failed"], res["failed_files"]), (1, ["ruim.md"]))
        self.assertEqual(self.store.indexed_files(), {"a.md": 3})
        self.assertNotIn("ruim.md", self.manifest())
        self.assertIn("a.md", self.manifest())

    def test_second_run_is_noop(self):
        self.engine.sync_vault(verbose=False)
        self.assertEqual(self.engine.sync_vault(verbose=False)["chunks_indexed"], 0)


class TestReconcile(SyncTestBase):
    def setUp(self):
        super().setUp()
        (self.vault / "b.md").write_text(ONE_SECTION, encoding="utf-8")
        res = self.engine.sync_vault(verbose=False)
        self.assertEqual(res["failed"], 0)
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})

    def test_empty_collection_is_refilled(self):  # CA-08
        self.client.delete_collection("kb")  # manifesto continua cheio
        self.engine.sync_vault(verbose=False)
        self.assertEqual(set(self.store.indexed_files()), {"a.md", "b.md"})

    def test_orphan_removed(self):  # CA-08
        self.store.upsert_chunks(
            [{"id": "x.md:0", "content": "x", "metadata": {"file_path": "x.md"}}], [[1.0] * 768]
        )
        self.assertEqual(self.engine.reconcile(verbose=False)["orphans_removed"], 1)
        self.assertNotIn("x.md", self.store.indexed_files())

    def test_reconcile_twice_reports_zeros(self):
        self.engine.reconcile(verbose=False)
        self.assertEqual(
            self.engine.reconcile(verbose=False),
            {
                "orphans_removed": 0, "missing_reindexed": 0, "untracked_reindexed": 0,
                "failed": 0, "failed_files": [],
            },
        )

    def test_missing_from_index_is_reindexed(self):
        self.store.delete_by_file_path("b.md")
        res = self.engine.reconcile(verbose=False)
        self.assertEqual(
            res,
            {"orphans_removed": 0, "missing_reindexed": 1, "untracked_reindexed": 0,
             "failed": 0, "failed_files": []},
        )
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})
        self.assertIn("b.md", self.manifest())

    def test_untracked_in_vault_is_reindexed(self):
        manifest = self.manifest()
        manifest.pop("b.md")
        self.engine.manifest_manager.save_manifest(manifest)
        res = self.engine.reconcile(verbose=False)
        self.assertEqual(
            res,
            {"orphans_removed": 0, "missing_reindexed": 0, "untracked_reindexed": 1,
             "failed": 0, "failed_files": []},
        )
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})
        self.assertIn("b.md", self.manifest())

    def test_orphan_in_vault_is_untracked_not_orphan(self):
        self.store.upsert_chunks(
            [{"id": "c.md:0", "content": "c", "metadata": {"file_path": "c.md"}}], [[1.0] * 768]
        )
        (self.vault / "c.md").write_text(ONE_SECTION, encoding="utf-8")
        res = self.engine.reconcile(verbose=False)
        self.assertEqual(
            (res["orphans_removed"], res["missing_reindexed"], res["untracked_reindexed"]), (0, 0, 1)
        )
        self.assertEqual(self.store.indexed_files()["c.md"], 1)

    def test_zero_chunk_file_is_not_reported_as_missing(self):
        (self.vault / "e.md").write_text("", encoding="utf-8")
        self.engine.sync_vault(verbose=False)
        self.assertIn("e.md", self.manifest())
        self.assertNotIn("e.md", self.store.indexed_files())
        zeros = {
            "orphans_removed": 0, "missing_reindexed": 0, "untracked_reindexed": 0,
            "failed": 0, "failed_files": [],
        }
        self.assertEqual(self.engine.reconcile(verbose=False), zeros)
        self.assertEqual(self.engine.reconcile(verbose=False), zeros)

    def test_deleted_file_is_left_to_the_diff(self):
        (self.vault / "b.md").unlink()
        self.store.delete_by_file_path("b.md")
        res = self.engine.reconcile(verbose=False)
        self.assertEqual(res["missing_reindexed"], 0)
        self.assertNotIn("b.md", self.manifest())
        self.assertEqual(set(self.store.indexed_files()), {"a.md"})

    def test_unreadable_manifest_with_missing_collection_does_not_create_it(self):
        self.client.delete_collection("kb")
        self.manifest_path.write_text("{", encoding="utf-8")
        with self.assertRaises(ManifestError):
            self.engine.sync_vault(verbose=False)
        self.assertNotIn("kb", [c.name for c in self.client.get_collections().collections])
        with self.assertRaises(ManifestError):
            self.engine.reconcile(verbose=False)
        self.assertNotIn("kb", [c.name for c in self.client.get_collections().collections])

    def test_failure_inside_auto_reconcile_is_retried_next_sync(self):
        self.client.delete_collection("kb")  # manifesto cheio, colecao some
        with mock.patch.object(self.store, "indexed_files", side_effect=ConnectionError("fora")):
            with self.assertRaises(ConnectionError):
                self.engine.sync_vault(verbose=False)
        # a colecao foi recriada (vazia) pelo sync que falhou: created nao se repete
        self.assertEqual(self.store.points_count(), 0)
        self.engine.sync_vault(verbose=False)
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})

    def test_populated_collection_does_not_reconcile(self):
        with mock.patch.object(self.engine, "_reconcile_unlocked") as spy:
            self.engine.sync_vault(verbose=False)
        spy.assert_not_called()

    def test_undecodable_missing_file_is_counted_as_missing(self):
        self.store.delete_by_file_path("b.md")
        with mock.patch.object(self.engine.chunker, "chunk_bytes",
                               side_effect=UnicodeDecodeError("utf-8", b"abc", 0, 1, "invalido")):
            report = self.engine._reconcile_unlocked(self.manifest(), verbose=False)
        self.assertEqual(report["missing_reindexed"], 1)
        self.assertNotIn("b.md", self.manifest())

    def test_reconcile_reports_sync_failures(self):
        self.store.delete_by_file_path("b.md")
        with mock.patch.object(self.engine.embedder, "get_embedding", side_effect=RuntimeError("ollama fora")):
            res = self.engine.reconcile(verbose=False)
        self.assertEqual(res["missing_reindexed"], 1)
        self.assertEqual((res["failed"], res["failed_files"]), (1, ["b.md"]))
        self.assertNotIn("b.md", self.store.indexed_files())

    def test_reconcile_holds_the_lock(self):
        with sync_lock(self.engine.lock_path):
            with self.assertRaises(SyncBusy):
                self.engine.reconcile(verbose=False)


class FailingOnCallEmbedder:
    """Embedder falso que levanta RuntimeError("ollama") na N-esima chamada."""

    def __init__(self, fail_on_call):
        self.fail_on_call = fail_on_call
        self.calls = 0

    def get_embedding(self, text):
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("ollama")
        return [0.1] * settings.vector_size


class TestRebuild(SyncTestBase):
    """Estado inicial: alias "kb" -> colecao real "kb__old" com pontos."""

    def setUp(self):
        super().setUp()
        (self.vault / "b.md").write_text(ONE_SECTION, encoding="utf-8")
        self.mm = self.engine.manifest_manager
        self.store.create_named_collection("kb__old", settings.vector_size)
        self.client.upsert(
            "kb__old",
            points=[PointStruct(id=1, vector=[0.2] * settings.vector_size, payload={"file_path": "velho.md"})],
        )
        self.store.swap_alias("kb", "kb__old", has_old_alias=False)
        # Escritas da reconstrucao criam um QdrantStore novo: precisa ver o mesmo cliente em memoria.
        patcher = mock.patch("core.qdrant_store.QdrantClient", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_kb_real_collection(self):
        self.store.drop_collection("kb__old")  # o alias cai junto com a colecao
        self.assertIsNone(self.store.alias_target("kb"))
        self.store.create_named_collection("kb", settings.vector_size)
        self.client.upsert(
            "kb",
            points=[PointStruct(id=1, vector=[0.2] * settings.vector_size, payload={"file_path": "velho.md"})],
        )

    def test_failed_rebuild_keeps_alias(self):  # CA-09 / INV-N07
        self.engine.embedder = FailingOnCallEmbedder(fail_on_call=2)
        with self.assertRaises(RuntimeError):
            self.engine.rebuild(verbose=False)
        self.assertEqual(self.store.alias_target("kb"), "kb__old")
        self.assertEqual(self.store.collections_with_prefix("kb__"), ["kb__old"])
        self.assertEqual(self.store.indexed_files(), {"velho.md": 1})
        self.assertFalse(self.manifest_path.exists())

    def test_successful_rebuild_swaps_and_drops_old(self):  # CA-09
        r = self.engine.rebuild(verbose=False)
        self.assertEqual(self.store.alias_target("kb"), r["collection"])
        self.assertEqual(self.store.collections_with_prefix("kb__"), [r["collection"]])
        self.assertRegex(r["collection"], r"^kb__\d{14}$")
        self.assertEqual((r["files"], r["chunks"], r["migrated"]), (2, 4, False))
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})
        self.assertEqual(
            self.manifest(),
            {name: sha256((self.vault / name).read_bytes()) for name in ("a.md", "b.md")},
        )

    def test_migration_requires_confirmation(self):  # CA-10
        self.make_kb_real_collection()
        with self.assertRaises(MigrationNeedsConfirmation):
            self.engine.rebuild(verbose=False)
        # nada foi criado nem indexado antes da confirmacao
        self.assertTrue(self.store.is_real_collection("kb"))
        self.assertEqual(self.store.collections_with_prefix("kb__"), [])
        r = self.engine.rebuild(verbose=False, confirm_migration=True)
        self.assertTrue(r["migrated"])
        self.assertFalse(self.store.is_real_collection("kb"))
        self.assertEqual(self.store.alias_target("kb"), r["collection"])
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})

    def test_failed_migration_keeps_real_collection(self):  # INV-N07
        self.make_kb_real_collection()
        self.engine.embedder = FailingOnCallEmbedder(fail_on_call=1)
        with self.assertRaises(RuntimeError):
            self.engine.rebuild(verbose=False, confirm_migration=True)
        self.assertTrue(self.store.is_real_collection("kb"))
        self.assertEqual(self.store.collections_with_prefix("kb__"), [])
        self.assertEqual(self.store.indexed_files(), {"velho.md": 1})

    def test_rebuild_ignores_corrupt_manifest(self):
        self.manifest_path.write_text("{", encoding="utf-8")
        self.engine.rebuild(verbose=False, confirm_migration=True)
        self.assertEqual(set(self.mm.load_manifest()), {"a.md", "b.md"})

    def test_empty_vault_never_swaps(self):  # INV-N07: colecao vazia
        for p in self.vault.glob("*.md"):
            p.unlink()
        with self.assertRaises(RuntimeError):
            self.engine.rebuild(verbose=False)
        self.assertEqual(self.store.alias_target("kb"), "kb__old")
        self.assertEqual(self.store.collections_with_prefix("kb__"), ["kb__old"])

    def test_leftover_collection_from_crashed_rebuild_is_dropped(self):  # spec 6.2
        self.store.create_named_collection("kb__20260101000000", settings.vector_size)
        r = self.engine.rebuild(verbose=False)
        self.assertEqual(self.store.collections_with_prefix("kb__"), [r["collection"]])
        self.assertEqual(self.store.alias_target("kb"), r["collection"])

    def test_same_second_rebuild_gets_suffix(self):
        with mock.patch("ingestion.sync._utc_stamp", return_value="20261027120000"):
            first = self.engine.rebuild(verbose=False)
            second = self.engine.rebuild(verbose=False)
        self.assertEqual(first["collection"], "kb__20261027120000")
        self.assertEqual(second["collection"], "kb__20261027120000_1")
        self.assertEqual(self.store.alias_target("kb"), second["collection"])
        self.assertEqual(self.store.collections_with_prefix("kb__"), [second["collection"]])
        self.assertEqual(self.store.indexed_files(), {"a.md": 3, "b.md": 1})

    def test_rebuild_holds_the_lock(self):
        with sync_lock(self.engine.lock_path):
            with self.assertRaises(SyncBusy):
                self.engine.rebuild(verbose=False)
        self.assertEqual(self.store.alias_target("kb"), "kb__old")
        self.assertEqual(self.store.collections_with_prefix("kb__"), ["kb__old"])

    def test_undecodable_note_aborts_rebuild(self):  # INV-N07
        (self.vault / "ruim.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
        with self.assertRaises(RuntimeError) as ctx:
            self.engine.rebuild(verbose=False)
        self.assertIn("ruim.md", str(ctx.exception))
        self.assertEqual(self.store.alias_target("kb"), "kb__old")
        self.assertEqual(self.store.collections_with_prefix("kb__"), ["kb__old"])
        self.assertEqual(self.store.indexed_files(), {"velho.md": 1})
        self.assertFalse(self.manifest_path.exists())

    def test_incremental_sync_after_rebuild_is_noop(self):
        self.engine.rebuild(verbose=False)
        res = self.engine.sync_vault(verbose=False)
        self.assertEqual((res["added"], res["modified"], res["deleted"]), (0, 0, 0))


class FakeEvent:
    def __init__(self, path, is_directory=False):
        self.src_path = path
        self.is_directory = is_directory


class FakeTimer:
    def __init__(self, interval, fn, owner):
        self.interval = interval
        self.fn = fn
        self.owner = owner
        self.daemon = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.owner.cancelled += 1

    def fire(self):
        self.fn()


class TestWatcher(unittest.TestCase):
    """Debounce de borda final: um sync apos o ultimo evento (CA-11)."""

    def setUp(self):
        from ingestion.scheduler import VaultChangeHandler

        self.timers = []
        self.cancelled = 0
        self.sync_fn = mock.Mock(return_value=None)

        def factory(interval, fn):
            t = FakeTimer(interval, fn, self)
            self.timers.append(t)
            return t

        self.handler = VaultChangeHandler(self.sync_fn, debounce_seconds=2.0, timer_factory=factory)

    def test_burst_gives_one_trailing_sync(self):
        for _ in range(3):
            self.handler.on_any_event(FakeEvent("a.md"))
        self.assertEqual(self.cancelled, 2)
        self.assertEqual(len(self.timers), 3)
        self.timers[-1].fire()
        self.assertEqual(self.sync_fn.call_count, 1)

    def test_event_does_not_sync_before_timer_fires(self):
        self.handler.on_any_event(FakeEvent("a.md"))
        self.assertEqual(self.sync_fn.call_count, 0)
        self.assertTrue(self.timers[-1].started)
        self.assertEqual(self.timers[-1].interval, 2.0)

    def test_timer_is_daemon(self):
        self.handler.on_any_event(FakeEvent("a.md"))
        self.assertTrue(self.timers[-1].daemon)

    def test_busy_rearms(self):
        self.sync_fn.side_effect = [SyncBusy(), None]
        self.handler.on_any_event(FakeEvent("a.md"))
        self.timers[-1].fire()
        self.assertEqual(len(self.timers), 2)
        self.assertEqual(self.timers[-1].interval, 2.0)
        self.timers[-1].fire()
        self.assertEqual(self.sync_fn.call_count, 2)
        self.assertEqual(len(self.timers), 2)

    def test_other_error_is_logged_and_not_rearmed(self):
        self.sync_fn.side_effect = RuntimeError("boom")
        self.handler.on_any_event(FakeEvent("a.md"))
        self.timers[-1].fire()
        self.assertEqual(len(self.timers), 1)

    def test_non_markdown_ignored(self):
        self.handler.on_any_event(FakeEvent("a.png"))
        self.assertEqual(self.timers, [])

    def test_directory_ignored(self):
        self.handler.on_any_event(FakeEvent("sub.md", is_directory=True))
        self.assertEqual(self.timers, [])


class TestRunWatcher(unittest.TestCase):
    """run_watcher: sync inicial, lock ocupado no inicio e ligacao do observer (spec 6.1, ADR-033 D2)."""

    def setUp(self):
        from ingestion import scheduler

        self.scheduler = scheduler
        self.timers = []
        self.cancelled = 0
        engine_patch = mock.patch.object(scheduler, "SyncEngine")
        observer_patch = mock.patch.object(scheduler, "Observer")
        # o laco `while True: time.sleep(1)` termina como num Ctrl+C, sem dormir
        sleep_patch = mock.patch.object(scheduler.time, "sleep", side_effect=KeyboardInterrupt)
        self.engine_cls = engine_patch.start()
        self.observer = observer_patch.start().return_value
        sleep_patch.start()
        for p in (engine_patch, observer_patch, sleep_patch):
            self.addCleanup(p.stop)
        self.engine = self.engine_cls.return_value

    def factory(self, interval, fn):
        t = FakeTimer(interval, fn, self)
        self.timers.append(t)
        return t

    def test_busy_first_sync_still_starts_and_arms_retry(self):
        self.engine.sync_vault.side_effect = [SyncBusy(), {"failed": 0}]
        self.scheduler.run_watcher(timer_factory=self.factory)
        self.observer.schedule.assert_called_once()
        self.observer.start.assert_called_once()
        self.observer.stop.assert_called_once()
        self.observer.join.assert_called_once()
        self.assertEqual(len(self.timers), 1)
        self.assertTrue(self.timers[0].started)
        self.assertTrue(self.timers[0].daemon)
        self.timers[0].fire()
        self.assertEqual(self.engine.sync_vault.call_count, 2)
        self.engine.sync_vault.assert_called_with(verbose=True)

    def test_first_sync_ok_schedules_observer_on_vault(self):
        self.engine.sync_vault.return_value = {"failed": 0}
        self.scheduler.run_watcher(timer_factory=self.factory)
        self.engine_cls.assert_called_once_with(lock_wait=30.0)
        self.engine.sync_vault.assert_called_once_with(verbose=True)
        self.assertEqual(self.timers, [])
        args, kwargs = self.observer.schedule.call_args
        handler = args[0]
        self.assertEqual(kwargs, {"path": str(settings.vault_dir), "recursive": True})
        self.assertIsInstance(handler, self.scheduler.VaultChangeHandler)
        self.observer.start.assert_called_once()
        handler.sync_fn()
        self.assertEqual(self.engine.sync_vault.call_count, 2)
        self.engine.sync_vault.assert_called_with(verbose=True)
        # o handler usa a fabrica de timer recebida
        handler.on_any_event(FakeEvent("a.md"))
        self.assertEqual(len(self.timers), 1)


class TestCli(unittest.TestCase):
    """cli.py sync --reconcile/--rebuild/--yes e mensagens de erro (spec 2.7, 2.8)."""

    SYNC_OK = {"added": 1, "modified": 2, "deleted": 3, "chunks_indexed": 4, "failed": 0, "failed_files": []}
    RECONCILE_OK = {"orphans_removed": 5, "missing_reindexed": 6, "untracked_reindexed": 7,
                    "failed": 0, "failed_files": []}
    REBUILD_OK = {"collection": "kiosk_brain_20261027", "files": 8, "chunks": 9, "migrated": False}

    def setUp(self):
        import importlib
        import importlib.util
        import sys
        import types

        import click
        from click.testing import CliRunner

        # cli.py importa scripts.sanitize no fim do modulo; se ele nao existe neste checkout,
        # um stub (so durante o teste) deixa o grupo carregar. sys.modules e restaurado no fim.
        modules = mock.patch.dict(sys.modules)
        modules.start()
        self.addCleanup(modules.stop)
        sys.modules.pop("cli", None)
        try:
            real_sanitize = importlib.util.find_spec("scripts.sanitize") is not None
        except ImportError:
            real_sanitize = False
        if not real_sanitize:
            stub = types.ModuleType("scripts.sanitize")
            stub.sanitize_cmd = click.Command("sanitize", callback=lambda: None)
            sys.modules["scripts.sanitize"] = stub
        cli_module = importlib.import_module("cli")

        self.cli = cli_module.cli
        self.runner = CliRunner()
        patcher = mock.patch("ingestion.sync.SyncEngine")
        self.engine = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.engine.sync_vault.return_value = dict(self.SYNC_OK)
        self.engine.reconcile.return_value = dict(self.RECONCILE_OK)
        self.engine.rebuild.return_value = dict(self.REBUILD_OK)

    def invoke(self, *args):
        result = self.runner.invoke(self.cli, ["sync", *args])
        # o console do cli e forcado a terminal: remove as sequencias ANSI antes de comparar
        result.output_text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        return result

    def test_plain_sync_prints_panel_and_exits_zero(self):
        result = self.invoke()
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.assertIn("Sincronização Concluída", result.output_text)
        self.engine.sync_vault.assert_called_once()
        self.engine.reconcile.assert_not_called()
        self.engine.rebuild.assert_not_called()

    def test_plain_sync_with_failures_exits_one(self):
        self.engine.sync_vault.return_value = dict(self.SYNC_OK, failed=2)
        result = self.invoke()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Sincronização com falhas", result.output_text)

    def test_reconcile_prints_result_and_exits_zero(self):
        result = self.invoke("--reconcile")
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.engine.reconcile.assert_called_once()
        self.engine.sync_vault.assert_not_called()
        for value in ("Órfãos removidos: 5", "Reindexados (faltavam no índice): 6",
                      "Reindexados (fora do manifesto): 7", "Falhas: 0"):
            self.assertIn(value, result.output_text)

    def test_reconcile_with_failures_exits_one(self):
        self.engine.reconcile.return_value = dict(self.RECONCILE_OK, failed=1)
        result = self.invoke("--reconcile")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Falhas: 1", result.output_text)

    def test_rebuild_prints_result_and_exits_zero(self):
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.engine.rebuild.assert_called_once_with(verbose=True, confirm_migration=False)
        self.assertIn("kiosk_brain_20261027", result.output_text)
        self.assertIn("Arquivos: 8", result.output_text)
        self.assertIn("Blocos: 9", result.output_text)

    def test_rebuild_yes_confirms_migration(self):
        result = self.invoke("--rebuild", "--yes")
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.engine.rebuild.assert_called_once_with(verbose=True, confirm_migration=True)

    def test_busy_lock_message(self):
        self.engine.sync_vault.side_effect = SyncBusy()
        result = self.invoke()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Outro sync está em andamento.", result.output_text)

    def test_busy_lock_message_on_reconcile_and_rebuild(self):
        self.engine.reconcile.side_effect = SyncBusy()
        self.engine.rebuild.side_effect = SyncBusy()
        for flag in ("--reconcile", "--rebuild"):
            result = self.invoke(flag)
            self.assertEqual(result.exit_code, 1, flag)
            self.assertIn("Outro sync está em andamento.", result.output_text)

    def test_unreadable_manifest_message(self):
        self.engine.sync_vault.side_effect = ManifestError("corrompido")
        result = self.invoke()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Manifesto ilegível; rode 'cli.py sync --rebuild'.", result.output_text)

    def test_migration_needs_confirmation_message(self):
        self.engine.rebuild.side_effect = MigrationNeedsConfirmation()
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 1)
        self.assertIn(
            "A coleção atual vira alias nesta reconstrução e a busca falha por um instante. "
            "Rode de novo com --yes.",
            result.output_text,
        )

    def test_generic_error_keeps_message_and_exit_one(self):
        self.engine.rebuild.side_effect = RuntimeError("colecao nova vazia")
        result = self.invoke("--rebuild", "--yes")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Erro ao sincronizar:", result.output_text)
        self.assertIn("colecao nova vazia", result.output_text)

    def test_yes_without_rebuild_is_usage_error(self):
        result = self.invoke("--yes")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("--yes só vale com --rebuild", result.output_text)
        self.engine.sync_vault.assert_not_called()

    def test_reconcile_with_rebuild_is_usage_error(self):
        result = self.invoke("--reconcile", "--rebuild")
        self.assertEqual(result.exit_code, 2)
        self.assertIn("--reconcile e --rebuild não podem ser usados juntos", result.output_text)
        self.engine.reconcile.assert_not_called()
        self.engine.rebuild.assert_not_called()


if __name__ == "__main__":
    unittest.main()

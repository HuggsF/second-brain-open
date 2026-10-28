"""Testes de consistencia vault -> Qdrant (onda A)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import settings
from core.chunker import MarkdownChunker
from core.hasher import ManifestError, ManifestManager
from core.qdrant_store import QdrantStore
from core.sync_lock import SyncBusy, sync_lock
from ingestion.sync import SyncEngine


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


if __name__ == "__main__":
    unittest.main()

"""Testes de consistencia vault -> Qdrant (onda A)."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from core.hasher import ManifestError, ManifestManager
from core.qdrant_store import QdrantStore


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


if __name__ == "__main__":
    unittest.main()

"""Testes de consistencia vault -> Qdrant (onda A)."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.hasher import ManifestError, ManifestManager


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


if __name__ == "__main__":
    unittest.main()

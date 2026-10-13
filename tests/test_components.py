import unittest
from unittest.mock import patch
from qdrant_client import QdrantClient
from pathlib import Path
from config import settings
from core.hasher import ManifestManager
from core.chunker import MarkdownChunker
from core.qdrant_store import QdrantStore

class TestSecondBrainCore(unittest.TestCase):
    def test_chunker_basic(self):
        chunker = MarkdownChunker(chunk_size=500, overlap=50)
        # Testa chunking da ADR
        adr_file = settings.adrs_dir / "ADR-001-migracao-sults-holmes-para-salesforce.md"
        self.assertTrue(adr_file.exists(), "ADR-001 deve existir")
        
        chunks = chunker.chunk_file(adr_file, settings.vault_dir)
        self.assertGreater(len(chunks), 0, "Deve gerar ao menos um chunk")
        first_chunk = chunks[0]
        self.assertIn("content", first_chunk)
        self.assertEqual(first_chunk["metadata"]["category"], "adrs")
        self.assertIn("ADR-001", first_chunk["metadata"]["doc_title"])

    def test_chunker_strips_frontmatter_into_metadata(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            note = vault / "adrs" / "ADR-900-x.md"
            note.parent.mkdir()
            note.write_bytes("\r\n".join(['---', 'type: adr', 'status: Aceito', 'date: 2026-10-12', '---', '# ADR-900: Teste', '', 'Intro.', '', '## Decisão', '', 'Usar X.', '']).encode("utf-8"))
            chunks = MarkdownChunker(chunk_size=500, overlap=50).chunk_file(note, vault)
        self.assertEqual([c["metadata"]["section"] for c in chunks], ["Introdução", "Decisão"])
        self.assertNotIn("status: Aceito", chunks[0]["content"])
        self.assertEqual(chunks[0]["metadata"]["doc_title"], "ADR-900: Teste")
        self.assertEqual((chunks[1]["metadata"]["status"], chunks[1]["metadata"]["doc_type"]), ("Aceito", "adr"))

    def test_hasher_diff(self):
        test_manifest = settings.base_dir / ".test_manifest.json"
        manifest_mgr = ManifestManager(manifest_path=test_manifest)
        added, modified, deleted = manifest_mgr.get_diff(settings.vault_dir)
        # Como o teste é novo, todos os arquivos criados devem ser reportados como adicionados
        self.assertGreater(len(added), 0, "Deve identificar arquivos adicionados no Vault")
        if test_manifest.exists():
            test_manifest.unlink()

    def test_qdrant_connection_and_collection(self):
        client = QdrantClient(location=":memory:")
        self.addCleanup(client.close)
        with patch("core.qdrant_store.QdrantClient", return_value=client):
            store = QdrantStore()

        store.ensure_collection(vector_size=768)
        stats = store.get_stats()
        self.assertNotIn("error", stats, f"Colecao local deve existir: {stats.get('error')}")
        self.assertEqual(stats["collection"], settings.qdrant_collection)
        self.assertEqual(stats["points_count"], 0)
        collection = client.get_collection(settings.qdrant_collection)
        self.assertEqual(collection.config.params.vectors.size, 768)

        independent_client = QdrantClient(location=":memory:")
        self.addCleanup(independent_client.close)
        with patch("core.qdrant_store.QdrantClient", return_value=independent_client):
            independent_store = QdrantStore()
        independent_store.ensure_collection(vector_size=768)

        store.upsert_chunks(
            [{"id": "offline-test-chunk", "content": "Local test content", "metadata": {}}],
            [[1.0] + [0.0] * 767],
        )
        self.assertEqual(store.get_stats()["points_count"], 1)
        self.assertEqual(independent_store.get_stats()["points_count"], 0)

if __name__ == "__main__":
    unittest.main()

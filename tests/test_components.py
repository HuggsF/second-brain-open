import unittest
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

    def test_hasher_diff(self):
        test_manifest = settings.base_dir / ".test_manifest.json"
        manifest_mgr = ManifestManager(manifest_path=test_manifest)
        added, modified, deleted = manifest_mgr.get_diff(settings.vault_dir)
        # Como o teste é novo, todos os arquivos criados devem ser reportados como adicionados
        self.assertGreater(len(added), 0, "Deve identificar arquivos adicionados no Vault")
        if test_manifest.exists():
            test_manifest.unlink()

    def test_qdrant_connection_and_collection(self):
        store = QdrantStore()
        store.ensure_collection(vector_size=768)
        stats = store.get_stats()
        self.assertNotIn("error", stats, f"Qdrant deve estar online: {stats.get('error')}")
        self.assertEqual(stats["collection"], settings.qdrant_collection)

if __name__ == "__main__":
    unittest.main()

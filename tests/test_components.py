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


class TestChunkLines(unittest.TestCase):
    BASE_COMMIT = "55d4b93"

    def lines_of(self, raw, chunk):  # helper: linhas originais do intervalo
        text = raw.decode("utf-8").replace("\r\n", "\n").split("\n")
        return text[chunk["metadata"]["line_start"] - 1: chunk["metadata"]["line_end"]]

    def test_section_lines_with_frontmatter_crlf(self):
        raw = "\r\n".join(["---", "type: adr", "---", "# T", "", "Intro.", "", "## Decisão", "", "Usar X.", "Linha 2.", ""]).encode()
        a, b = MarkdownChunker(chunk_size=500, overlap=50).chunk_bytes(raw, "adrs/x.md")
        self.assertEqual((a["metadata"]["line_start"], a["metadata"]["line_end"]), (4, 6))  # "# T" .. "Intro."
        self.assertEqual((b["metadata"]["line_start"], b["metadata"]["line_end"]), (10, 11))
        self.assertEqual(self.lines_of(raw, b), ["Usar X.", "Linha 2."])

    def test_sliding_window_lines_cover_their_words(self):
        body = "\n".join(f"palavra{i} " * 10 for i in range(40))  # seção longa, 40 linhas
        raw = f"# T\n## S\n{body}\n".encode()
        chunks = MarkdownChunker(chunk_size=200, overlap=50).chunk_bytes(raw, "systems/x.md")
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            words = c["content"].split("\n\n", 1)[1].split()
            joined = " ".join(" ".join(self.lines_of(raw, c)).split())
            self.assertIn(words[0], joined)
            self.assertIn(words[-1], joined)
            self.assertLessEqual(c["metadata"]["line_start"], c["metadata"]["line_end"])

    def test_lone_cr_stays_within_one_original_line(self):
        # O chunker normaliza CR isolado para quebra de linha; o intervalo continua no arquivo original
        # (só CRLF -> LF), então a linha com CR isolado conta como uma linha só.
        raw = b"# T\n## S\nA\rB\nC\n"
        intro, c = MarkdownChunker(chunk_size=500, overlap=50).chunk_bytes(raw, "x.md")
        self.assertEqual((intro["metadata"]["line_start"], intro["metadata"]["line_end"]), (1, 1))
        self.assertEqual((c["metadata"]["line_start"], c["metadata"]["line_end"]), (3, 4))
        self.assertEqual(self.lines_of(raw, c), ["A\rB", "C"])

    def test_content_and_ids_unchanged_on_real_vault(self):
        """Guarda de migração única da onda B contra o chunker de `55d4b93` (BASE_COMMIT).

        Prova que registrar linhas não mudou `content` nem `id` de nenhum chunk do vault real.
        Aposente este teste quando o chunker mudar de propósito: a diferença passa a ser esperada.
        """
        import importlib.util
        import subprocess
        import tempfile

        repo = Path(__file__).resolve().parent.parent
        try:
            source = subprocess.run(
                ["git", "show", f"{self.BASE_COMMIT}:core/chunker.py"],
                cwd=repo, capture_output=True, check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            self.skipTest(f"base do chunker indisponível via git: {exc}")
        with tempfile.TemporaryDirectory() as tmp:
            base_file = Path(tmp) / "chunker_base.py"
            base_file.write_bytes(source)
            spec = importlib.util.spec_from_file_location("chunker_base_55d4b93", base_file)
            old_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(old_module)
        old = old_module.MarkdownChunker()
        new = MarkdownChunker()

        vault = repo / "vault"
        files = sorted(vault.rglob("*.md"))
        self.assertGreater(len(files), 0)
        for path in files:
            rel = path.relative_to(vault).as_posix()
            with self.subTest(file=rel):
                raw = path.read_bytes()
                new_chunks = new.chunk_bytes(raw, rel)
                self.assertEqual(
                    [(c["id"], c["content"]) for c in old.chunk_bytes(raw, rel)],
                    [(c["id"], c["content"]) for c in new_chunks],
                )
                n_lines = len(raw.decode("utf-8").replace("\r\n", "\n").split("\n"))
                for c in new_chunks:
                    start, end = c["metadata"]["line_start"], c["metadata"]["line_end"]
                    self.assertTrue(1 <= start <= end <= n_lines, (c["id"], start, end, n_lines))


class TestRetrievalSettings(unittest.TestCase):
    def _load_config(self, env):
        import importlib.util
        import os
        keys = ("BRAIN_SPACE", "RETRIEVAL_MIN_SCORE", "RETRIEVAL_MAX_DROP", "RETRIEVAL_MAX_PER_DOC")
        clean = {k: v for k, v in os.environ.items() if k not in keys}
        clean.update(env)
        config_file = Path(__file__).resolve().parent.parent / "config.py"
        with patch.dict(os.environ, clean, clear=True):
            spec = importlib.util.spec_from_file_location("config_fresh_for_test", config_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module.settings

    def test_defaults(self):
        s = self._load_config({})
        self.assertEqual(
            (s.space_id, s.retrieval_min_score, s.retrieval_max_drop, s.retrieval_max_per_doc),
            ("kiosk", 0.70, 0.10, 1),
        )

    def test_env_overrides(self):
        s = self._load_config({"BRAIN_SPACE": "outro", "RETRIEVAL_MIN_SCORE": "0.5",
                               "RETRIEVAL_MAX_DROP": "0.2", "RETRIEVAL_MAX_PER_DOC": "3"})
        self.assertEqual(
            (s.space_id, s.retrieval_min_score, s.retrieval_max_drop, s.retrieval_max_per_doc),
            ("outro", 0.5, 0.2, 3),
        )
        self.assertIsInstance(s.retrieval_max_per_doc, int)


if __name__ == "__main__":
    unittest.main()

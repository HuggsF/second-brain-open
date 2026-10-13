import tempfile
import unittest
from pathlib import Path

from ingestion.drive_sync import DriveSyncEngine, reference_slug


class ReferenceNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = DriveSyncEngine(base_dir=Path(self.tmp.name), chrome_path="unused")

    def tearDown(self):
        self.tmp.cleanup()

    def test_slug_folds_accents_and_drops_extensions_and_copy_suffixes(self):
        self.assertEqual(reference_slug("09_Dominando_as_ferramentas_-_Sophia_Faria.pptx_3_ (1).pdf"), "09-dominando-as-ferramentas-sophia-faria")
        self.assertEqual(reference_slug("Gestão de Produtos com IA - Fabrício.pptx - Microsoft PowerPoint.pdf"), "gestao-de-produtos-com-ia-fabricio")
        self.assertEqual(reference_slug("PM3 - AI Product Specialist - V1.png"), "pm3-ai-product-specialist-v1")

    def test_note_has_frontmatter_crlf_and_no_raw_text_path(self):
        path = self.engine.generate_vault_reference("Aula 1.pdf", "file-1", "Texto da aula", "a" * 64)
        raw = path.read_bytes()
        self.assertEqual(path.name, "aula-1.md")
        self.assertTrue(raw.startswith(b"---\r\ntype: reference\r\n"))
        self.assertEqual(raw.replace(b"\r\n", b"").count(b"\n"), 0)
        text = raw.decode("utf-8")
        self.assertIn("source_sha256: " + "a" * 64, text)
        self.assertNotIn("extracted_drive", text)
        self.assertIn("\r\n# Referência de Produto: Aula 1.pdf\r\n", text)

    def test_same_source_hash_reuses_existing_note_without_overwriting(self):
        first = self.engine.generate_vault_reference("Aula 1.pdf", "file-1", "original", "b" * 64)
        first.write_bytes(first.read_bytes() + b"nota editada a mao\r\n")
        again = self.engine.generate_vault_reference("Aula 1 (copia).pdf", "file-2", "outro", "b" * 64)
        self.assertEqual(again, first)
        self.assertIn(b"nota editada a mao", first.read_bytes())
        self.assertEqual(len(list(self.engine.references_dir.glob("*.md"))), 1)


class SystemDesignPathsTests(unittest.TestCase):
    def test_outputs_live_in_this_repository_and_course_root_comes_from_env(self):
        import importlib
        import os
        from unittest import mock
        import ingestion.system_design_sync as sds
        repo = Path(__file__).resolve().parent.parent
        with mock.patch.dict(os.environ, {"SYSTEM_DESIGN_COURSE_ROOT": "D:/cursos/sd"}):
            sds = importlib.reload(sds)
            self.assertEqual(sds.COURSE_ROOT, Path("D:/cursos/sd"))
        self.assertEqual((sds.VAULT_DIR, sds.OUTPUT_DIR), (repo / "vault", repo / "extracted_system_design"))
        importlib.reload(sds)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from core.docs_registry import DocsRegistryError
from core.geracao.escrita import escrever


class EscritaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_escreve_pagina_nova(self):
        self.assertEqual(escrever(self.root, "p/a.mdx", "olá\nmundo"), "gerado")
        self.assertEqual((self.root / "p/a.mdx").read_bytes(), "olá\nmundo".encode("utf-8"))

    def test_nao_sobrescreve(self):
        escrever(self.root, "a.mdx", "um")
        self.assertEqual(escrever(self.root, "a.mdx", "dois"), "pulado")
        self.assertEqual((self.root / "a.mdx").read_text(encoding="utf-8"), "um")

    def test_cria_pastas(self):
        escrever(self.root, "x/demandas/dem-1/visao.mdx", "v")
        self.assertTrue((self.root / "x/demandas/dem-1/visao.mdx").is_file())

    def test_recusa_caminho_fora_do_root(self):
        for rel in ("../x.mdx", str(Path(self._tmp.name).parent / "y.mdx")):
            with self.assertRaises(DocsRegistryError):
                escrever(self.root, rel, "z")


if __name__ == "__main__":
    unittest.main()

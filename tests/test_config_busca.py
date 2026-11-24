"""Configuração da busca textual: caminhos por variável de ambiente e limites do piso."""
import os
import unittest
from unittest import mock

import config

VARIAVEIS = ("BRAIN_INDEX_PATH", "BRAIN_VAULT_DIR", "BRAIN_SPACE_ID", "RETRIEVAL_MIN_SCORE",
             "RETRIEVAL_MAX_DROP", "RETRIEVAL_MAX_PER_DOC")


class TestConfigBusca(unittest.TestCase):
    def carregar(self, **ambiente):
        limpo = {k: v for k, v in os.environ.items() if k not in VARIAVEIS}
        limpo.update(ambiente)
        with mock.patch.dict(os.environ, limpo, clear=True):
            return config.Settings()

    def test_padroes(self):
        s = self.carregar()
        self.assertEqual(s.index_path, config.BASE_DIR / ".runtime" / "indice-busca.db")
        self.assertEqual(s.vault_dir, config.BASE_DIR / "vault")
        self.assertEqual(s.space_id, "principal")
        self.assertEqual(s.retrieval_min_score, 0.0)
        self.assertEqual(s.retrieval_max_drop, 0.5)
        self.assertEqual(s.retrieval_max_per_doc, 1)

    def test_index_path_relativo_resolve_na_raiz(self):
        s = self.carregar(BRAIN_INDEX_PATH="x/i.db")
        self.assertEqual(s.index_path, config.BASE_DIR / "x" / "i.db")

    def test_vault_dir_relativo_resolve_na_raiz(self):
        s = self.carregar(BRAIN_VAULT_DIR="meu-vault")
        self.assertEqual(s.vault_dir, config.BASE_DIR / "meu-vault")
        self.assertEqual(s.adrs_dir, s.vault_dir / "adrs")
        self.assertEqual(s.systems_dir, s.vault_dir / "systems")

    def test_caminho_absoluto_e_respeitado(self):
        alvo = str(config.BASE_DIR.parent / "outro-vault")
        self.assertEqual(str(self.carregar(BRAIN_VAULT_DIR=alvo).vault_dir), alvo)

    def test_variavel_vazia_vale_o_padrao(self):
        s = self.carregar(BRAIN_VAULT_DIR="", BRAIN_INDEX_PATH="", BRAIN_SPACE_ID="")
        self.assertEqual(s.vault_dir, config.BASE_DIR / "vault")
        self.assertEqual(s.index_path, config.BASE_DIR / ".runtime" / "indice-busca.db")
        self.assertEqual(s.space_id, "principal")

    def test_max_drop_fora_da_faixa_e_erro(self):
        for valor in ("1.5", "-0.1"):
            with self.assertRaises(ValueError, msg=valor):
                self.carregar(RETRIEVAL_MAX_DROP=valor)

    def test_campos_do_banco_vetorial_sairam(self):
        s = self.carregar()
        for campo in ("qdrant_url", "qdrant_collection", "vector_size", "embedding_model", "hash_manifest_path"):
            self.assertFalse(hasattr(s, campo), campo)


if __name__ == "__main__":
    unittest.main()

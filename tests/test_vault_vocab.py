"""Vocabulario do vault e termos desconhecidos da pergunta (spec 2.3, CA-4, CA-6)."""
import os
import tempfile
import unittest
from pathlib import Path

from core.vault_vocab import unknown_entities, vault_vocabulary


class VaultCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vault = Path(tmp.name)
        (self.vault / "a.md").write_text("Integração com a J&T e o Bling.", encoding="utf-8")


class TestUnknownEntities(VaultCase):
    def setUp(self):
        super().setUp()
        self.vocab = vault_vocabulary(self.vault)

    def test_capitalized_word_mid_sentence(self):
        self.assertEqual(unknown_entities("Como a Acme recebe pedidos?", self.vocab), ["Acme"])

    def test_acronym_at_sentence_start_is_checked(self):
        self.assertEqual(unknown_entities("ACME recebe os pedidos?", self.vocab), ["ACME"])

    def test_common_first_word_is_ignored(self):
        self.assertEqual(unknown_entities("Como funciona o fluxo?", self.vocab), [])

    def test_single_capital_after_period_is_ignored(self):
        self.assertEqual(unknown_entities("Pedidos. Acme recebe?", self.vocab), [])

    def test_known_terms_including_ampersand(self):
        self.assertEqual(unknown_entities("O Bling e a J&T falam?", self.vocab), [])

    def test_no_repetition_and_glued_punctuation(self):
        self.assertEqual(unknown_entities("Integração da Acme? (Acme) ACME,", self.vocab), ["Acme"])

    def test_short_tokens_are_ignored(self):
        self.assertEqual(unknown_entities("Qual o Xy?", self.vocab), [])

    def test_accent_is_normalized(self):
        self.assertEqual(unknown_entities("Como a Integracao funciona?", self.vocab), [])

    def test_accented_unknown_returns_unaccented_spelling(self):
        self.assertEqual(unknown_entities("Como a Ácmé recebe?", self.vocab), ["Acme"])

    def test_empty_vocabulary_disables_gate(self):
        self.assertEqual(unknown_entities("Como a Acme recebe?", frozenset()), [])

    def test_lowercase_name_is_known_limit(self):
        self.assertEqual(unknown_entities("como a acme recebe?", self.vocab), [])


class TestVaultVocabulary(VaultCase):
    def test_terms_are_normalized(self):
        vocab = vault_vocabulary(self.vault)
        self.assertIn("integracao", vocab)
        self.assertIn("j&t", vocab)
        self.assertIn("bling", vocab)

    def test_cache_invalidates_on_edit(self):
        vault_vocabulary(self.vault)
        path = self.vault / "a.md"
        stat = path.stat()
        path.write_text("Integração com a Acme agora.", encoding="utf-8")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        self.assertIn("acme", vault_vocabulary(self.vault))

    def test_cache_invalidates_on_new_file(self):
        vault_vocabulary(self.vault)
        (self.vault / "sub").mkdir()
        (self.vault / "sub" / "b.md").write_text("Zeta", encoding="utf-8")
        self.assertIn("zeta", vault_vocabulary(self.vault))

    def test_cache_invalidates_on_delete(self):
        (self.vault / "b.md").write_text("Zeta", encoding="utf-8")
        self.assertIn("zeta", vault_vocabulary(self.vault))
        (self.vault / "b.md").unlink()
        self.assertNotIn("zeta", vault_vocabulary(self.vault))

    def test_unreadable_file_is_skipped(self):
        (self.vault / "ruim.md").write_bytes(b"Zeta \xff\xfe")
        vocab = vault_vocabulary(self.vault)
        self.assertIn("bling", vocab)
        self.assertNotIn("zeta", vocab)

    def test_empty_vault_gives_empty_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(vault_vocabulary(Path(tmp)), frozenset())

    def test_missing_vault_gives_empty_vocabulary(self):
        self.assertEqual(vault_vocabulary(self.vault / "nao-existe"), frozenset())

    def test_two_roots_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp)
            (other / "x.md").write_text("Zeta", encoding="utf-8")
            self.assertIn("zeta", vault_vocabulary(other))
            self.assertNotIn("zeta", vault_vocabulary(self.vault))


if __name__ == "__main__":
    unittest.main()

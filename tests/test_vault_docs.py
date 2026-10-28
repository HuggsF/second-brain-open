"""Resolvedor unico de documentos do vault: nomes, numeros e caminhos relativos seguros."""
import tempfile
import unittest
from pathlib import Path

from config import settings
from core.vault_docs import DocError, resolve_named, resolve_numbered, resolve_relative


class TestVaultDocs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.vault = Path(self._tmp.name)
        self.systems = self.vault / "systems"
        self.adrs = self.vault / "adrs"
        self.systems.mkdir()
        self.adrs.mkdir()
        (self.systems / "sap.md").write_text("x", encoding="utf-8")
        for name in ("ADR-001-x.md", "ADR-003-y.md", "ADR-010-z.md"):
            (self.adrs / name).write_text("x", encoding="utf-8")

    def test_named_rejects_unsafe(self):
        for bad in ["../adrs/x", "..\\x", "c:/kiosk/x", "/etc/x", "a/b", "*", "sa?", "", None]:
            with self.subTest(bad=bad), self.assertRaises(DocError):
                resolve_named(self.systems, bad)

    def test_named_resolves_and_lowercases(self):
        self.assertEqual(resolve_named(self.systems, " SAP "), self.systems / "sap.md")
        self.assertIsNone(resolve_named(self.systems, "nao-existe"))

    def test_numbered_exact_forms(self):
        for ident in ["ADR-003", "adr003", "003", "3"]:
            with self.subTest(ident=ident):
                self.assertEqual(resolve_numbered(self.adrs, ident, "ADR"), [self.adrs / "ADR-003-y.md"])

    def test_numbered_number_without_file_is_empty(self):
        self.assertEqual(resolve_numbered(self.adrs, "7", "ADR"), [])

    def test_numbered_substring_is_sorted(self):
        self.assertEqual(
            [p.name for p in resolve_numbered(self.adrs, "adr", "ADR")],
            ["ADR-001-x.md", "ADR-003-y.md", "ADR-010-z.md"],
        )

    def test_numbered_rejects_wildcards(self):
        for bad in ["*", "[0-9]", "../systems/sap"]:
            with self.subTest(bad=bad), self.assertRaises(DocError):
                resolve_numbered(self.adrs, bad, "ADR")

    def test_relative_rejects_escape(self):
        for bad in ["../x.md", "adrs/../../x.md", "C:/x.md", "\\\\srv\\x.md", "/x.md", ""]:
            with self.subTest(bad=bad), self.assertRaises(DocError):
                resolve_relative(self.vault, bad)

    def test_relative_accepts_backslash(self):
        self.assertEqual(
            resolve_relative(self.vault, "adrs\\ADR-001-x.md"),
            self.vault / "adrs" / "ADR-001-x.md",
        )

    def test_every_real_vault_name_resolves(self):
        for f in settings.systems_dir.glob("*.md"):
            self.assertIsNotNone(resolve_named(settings.systems_dir, f.stem), f.name)
        for f in settings.adrs_dir.glob("ADR-*.md"):
            self.assertEqual(resolve_numbered(settings.adrs_dir, f.name[:7], "ADR"), [f])


if __name__ == "__main__":
    unittest.main()

"""Gate de agnosticismo: o núcleo novo não nomeia a instância."""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS = os.getenv("AGNOSTIC_FORBIDDEN_TERMS", r"(?!x)x")  # set to a regex of instance names to enforce
SCOPES = ("core/protocol", "core/local_tasks", "profiles/example", "fichas", "ingestion")
FILES = ("core/events.py", "mcp_servers/local_tasks_mcp.py", "core/ficha.py", "tests/test_ficha.py",
         "core/indice_texto.py", "core/consulta_texto.py", "core/vault_docs.py", "core/sync_lock.py", "core/vault_vocab.py",
         "core/citations.py", "core/chunker.py", "core/hasher.py", "core/retriever.py", "core/tools.py", "config.py", "cli.py",
         "tests/test_indice_texto.py", "tests/test_consulta_texto.py", "tests/test_vault_docs.py", "tests/test_sync_lock.py",
         "tests/test_vault_vocab.py", "tests/test_citations.py", "tests/test_sync_consistency.py",
         "tests/test_retrieval_contract.py", "tests/test_sem_motor_vetorial.py", "tests/test_busca_cli.py",
         "tests/test_config_busca.py")


class TestAgnosticCore(unittest.TestCase):
    def test_new_core_modules_do_not_name_the_instance(self):
        pattern = re.compile(TERMS, re.IGNORECASE)
        paths = [p for s in SCOPES if (ROOT / s).is_dir() for p in (ROOT / s).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        paths += [ROOT / f for f in FILES if (ROOT / f).is_file()]
        offenders = []
        for p in paths:
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = pattern.search(line)
                if m:
                    offenders.append(f"{p.relative_to(ROOT).as_posix()}:{n}: {m.group(0)}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

"""Guarda da troca do motor de busca: nada do banco vetorial nem de embeddings pelo Ollama volta."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

import cli
from config import settings
from core.indice_texto import IndiceTexto

RAIZ = Path(__file__).resolve().parent.parent
# Pastas ignoradas em qualquer nível.
IGNORAR = {
    ".venv", ".git", ".claude", ".superpowers", ".runtime", "node_modules", ".memory-backups",
    ".frontend-backups", "scratch", "extracted_drive", "extracted_pm3",
}
# Prefixos do caminho relativo à raiz: `data` só na raiz e os relatórios das avaliações.
IGNORAR_PREFIXOS = (("data",), ("evals", "reports"))


def _ignorado(caminho: Path) -> bool:
    partes = caminho.relative_to(RAIZ).parts
    return (
        bool(IGNORAR & set(partes))
        or any(partes[: len(prefixo)] == prefixo for prefixo in IGNORAR_PREFIXOS)
        or any(p.startswith(("extracted_", "downloads_")) for p in partes)
    )


def _arquivos_varridos() -> list[str]:
    return [
        p.relative_to(RAIZ).as_posix()
        for p in RAIZ.rglob("*.py")
        if not _ignorado(p) and p.name != "test_sem_motor_vetorial.py"
    ]


class TestSemMotorVetorial(unittest.TestCase):
    def test_modulos_do_motor_vetorial_nao_existem(self):
        self.assertFalse((RAIZ / "core" / "qdrant_store.py").exists())
        self.assertFalse((RAIZ / "core" / "embeddings.py").exists())
        self.assertFalse((RAIZ / "docker-compose.yml").exists())

    def test_nenhum_modulo_importa_qdrant_client(self):
        padrao = re.compile(r"^\s*(from|import)\s+(qdrant_client|core\.qdrant_store|core\.embeddings)", re.M)
        varridos = _arquivos_varridos()
        for esperado in ("evals/metrics.py", "evals/runner.py", "cli.py", "core/retriever.py", "core/tools.py"):
            self.assertIn(esperado, varridos)
        achados = [
            rel for rel in varridos
            if padrao.search((RAIZ / rel).read_text(encoding="utf-8", errors="ignore"))
        ]
        self.assertEqual(achados, [])

    def test_guarda_ignora_so_data_na_raiz_e_relatorios_das_avaliacoes(self):
        self.assertTrue(_ignorado(RAIZ / "data" / "x.py"))
        self.assertTrue(_ignorado(RAIZ / "evals" / "reports" / "x.py"))
        self.assertFalse(_ignorado(RAIZ / "core" / "data" / "x.py"))
        self.assertFalse(_ignorado(RAIZ / "evals" / "x.py"))

    def test_requirements_sem_qdrant_client(self):
        self.assertNotIn("qdrant-client", (RAIZ / "requirements.txt").read_text(encoding="utf-8"))

    def test_settings_sem_campos_do_motor_antigo(self):
        for campo in ("qdrant_url", "qdrant_collection", "vector_size", "embedding_model",
                      "embed_query_prefix", "embed_document_prefix"):
            self.assertFalse(hasattr(settings, campo), campo)
        self.assertTrue(hasattr(settings, "ollama_url"))
        self.assertTrue(hasattr(settings, "chat_model"))


class TestCliSemMotorVetorial(unittest.TestCase):
    def test_status_mostra_indice_e_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            indice = IndiceTexto(Path(tmp) / "indice.db")
            with patch("cli.IndiceTexto", return_value=indice):
                resultado = CliRunner().invoke(cli.cli, ["status"])
        self.assertEqual(resultado.exit_code, 0, resultado.output)
        self.assertIn("Índice de busca", resultado.output)
        self.assertIn("Vault Markdown", resultado.output)
        self.assertIn("rode 'cli.py sync'", resultado.output)
        self.assertNotIn("Qdrant", resultado.output)

    def test_status_com_indice_mostra_trechos_e_notas(self):
        class Falso:
            integro = True

            def verificar(self):
                return self.integro

            def estatisticas(self):
                return {"points_count": 12, "arquivos": 3, "esquema": "texto-v1",
                        "construido_em": "2026-11-12T10:00:00", "por_categoria": {}}
        with patch("cli.IndiceTexto", return_value=Falso()):
            resultado = CliRunner().invoke(cli.cli, ["status"])
        self.assertEqual(resultado.exit_code, 0, resultado.output)
        self.assertIn("12 trechos", resultado.output)
        self.assertIn("3 notas", resultado.output)

        Falso.integro = False
        with patch("cli.IndiceTexto", return_value=Falso()):
            resultado = CliRunner().invoke(cli.cli, ["status"])
        self.assertEqual(resultado.exit_code, 0, resultado.output)
        texto = " ".join(resultado.output.split())
        self.assertIn("Corrompido", texto)
        self.assertIn("rode 'cli.py sync'", texto)
        self.assertNotIn("12 trechos", resultado.output)

    def test_status_com_indice_corrompido_de_verdade(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "indice.db"
            caminho.write_bytes(b"isto nao e um banco sqlite" * 200)
            with patch("cli.IndiceTexto", return_value=IndiceTexto(caminho)):
                resultado = CliRunner().invoke(cli.cli, ["status"])
        self.assertEqual(resultado.exit_code, 0, resultado.output)
        self.assertIn("Corrompido", resultado.output)

    def test_pull_models_so_tem_chat_model(self):
        runner = CliRunner()
        self.assertEqual(runner.invoke(cli.cli, ["pull-models", "--embed-model", "x"]).exit_code, 2)
        ajuda = runner.invoke(cli.cli, ["pull-models", "--help"])
        self.assertIn("--chat-model", ajuda.output)
        self.assertNotIn("--embed-model", ajuda.output)


if __name__ == "__main__":
    unittest.main()

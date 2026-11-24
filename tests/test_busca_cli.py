"""Comandos de busca do cli sobre um vault temporário: sync, buscar, ask e status, sem serviço nenhum."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

import cli
from config import settings
from core.retriever import GeradorIndisponivel

NOTAS = {
    "systems/portal.md": "# Portal\n\n## Autenticação\n\nO portal autentica clientes com token de sessão renovado a cada hora.\n",
    "systems/estoque.md": "# Estoque\n\n## Reserva\n\nA reserva de estoque expira depois de quinze minutos sem pagamento.\n",
    "domain/fatura.md": "# Fatura\n\n## Fechamento\n\nA fatura mensal fecha no dia dez e vence no dia vinte.\n",
}
RAIZ = Path(__file__).resolve().parent.parent
SINTAXE_FTS = ('"', "*", "(", ")", "AND OR NOT", "NEAR(a b)", "a:b", "", "   ", '"aberta', "col:*", "-", "^")


class Ambiente(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.vault = self.tmp / "vault"
        for rel, texto in NOTAS.items():
            alvo = self.vault / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(texto, encoding="utf-8")
        self.indice = self.tmp / "estado" / "indice.db"
        self.config(vault_dir=self.vault, index_path=self.indice, retrieval_min_score=0.0)

    def config(self, **valores):
        for nome, valor in valores.items():
            troca = mock.patch.object(settings, nome, valor)
            troca.start()
            self.addCleanup(troca.stop)

    def rodar(self, *args):
        resultado = CliRunner().invoke(cli.cli, list(args))
        # exceção que não é SystemExit também dá saída 1 no CliRunner: sem isto, um defeito passaria por recusa
        self.assertTrue(resultado.exception is None or isinstance(resultado.exception, SystemExit),
                        repr(resultado.exception))
        resultado.texto = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", resultado.output).split())
        return resultado

    def sincronizar(self):
        r = self.rodar("sync")
        self.assertEqual(r.exit_code, 0, r.output)

    def gerador(self, funcao):
        troca = mock.patch("core.retriever.gerador_local", funcao)
        troca.start()
        self.addCleanup(troca.stop)


class TestBuscar(Ambiente):
    def test_sync_e_buscar_devolvem_a_nota_certa(self):
        self.sincronizar()
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("systems/estoque.md", r.texto)
        self.assertIn("Reserva", r.texto)
        self.assertNotIn("domain/fatura.md", r.texto)

    def test_buscar_com_filtro_de_categoria(self):
        self.sincronizar()
        r = self.rodar("buscar", "fatura", "--category", "systems")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertNotIn("domain/fatura.md", r.texto)

    def test_buscar_limite_fora_da_faixa_e_erro_de_uso(self):
        self.sincronizar()
        self.assertEqual(self.rodar("buscar", "fatura", "--limite", "0").exit_code, 2)

    def test_buscar_sem_resultado_por_termo_desconhecido(self):
        self.sincronizar()
        r = self.rodar("buscar", "Como funciona o Zarbatron?")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("sem registro no vault", r.texto)
        self.assertIn("zarbatron", r.texto.lower())

    def test_buscar_sem_resultado_abaixo_do_piso(self):
        self.sincronizar()
        self.config(retrieval_min_score=9999.0)
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("relevância mínima", r.texto)
        self.assertNotIn("systems/estoque.md", r.texto)

    def test_buscar_com_indice_vazio(self):
        for rel in NOTAS:
            (self.vault / rel).unlink()
        self.sincronizar()
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("cli.py sync", r.texto)

    def test_buscar_sem_indice_sai_1(self):
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("cli.py sync", r.texto)
        self.assertFalse(self.indice.exists())

    def test_buscar_com_sintaxe_do_fts(self):
        self.sincronizar()
        for pergunta in SINTAXE_FTS:
            with self.subTest(pergunta=pergunta):
                r = self.rodar("buscar", "--", pergunta)
                self.assertEqual(r.exit_code, 0, r.output)
                self.assertNotIn("Traceback", r.output)
                self.assertNotIn("systems/", r.texto)

    def test_buscar_com_indice_que_e_lixo(self):
        self.indice.parent.mkdir(parents=True)
        self.indice.write_bytes(b"isto nao e um banco sqlite" * 200)
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("Corrompido", r.texto)
        self.assertIn("sync --rebuild", r.texto)
        self.assertNotIn("Traceback", r.output)

    def test_buscar_com_indice_de_zero_bytes_e_tratado_como_vazio(self):
        self.indice.parent.mkdir(parents=True)
        self.indice.write_bytes(b"")
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("cli.py sync", r.texto)
        self.assertNotIn("Traceback", r.output)

    def test_buscar_com_pasta_no_lugar_do_indice(self):
        self.indice.mkdir(parents=True)
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("sync --rebuild", r.texto)
        self.assertNotIn("Traceback", r.output)


class TestPrimeiroSync(Ambiente):
    def test_primeiro_sync_com_nota_ilegivel_aborta_e_diz_o_que_fazer(self):
        (self.vault / "systems" / "ruim.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
        r = self.rodar("sync")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("ruim.md", r.texto)
        self.assertIn("nenhum índice foi gravado ou alterado", r.texto)
        self.assertIn("Corrija ou remova", r.texto)
        self.assertNotIn("ficou como estava", r.texto)
        self.assertEqual(self.rodar("buscar", "reserva de estoque").exit_code, 1)

    def test_nota_ilegivel_depois_do_primeiro_sync_falha_sozinha(self):
        self.sincronizar()
        (self.vault / "systems" / "ruim.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
        r = self.rodar("sync")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("Sincronização com falhas", r.texto)
        r = self.rodar("buscar", "reserva de estoque")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("systems/estoque.md", r.texto)


class TestLinhaDeComandoReal(Ambiente):
    """Pelo processo de verdade: o CliRunner não passa pela expansão de curingas do Windows."""

    def processo(self, *args):
        ambiente = dict(os.environ, BRAIN_VAULT_DIR=str(self.vault), BRAIN_INDEX_PATH=str(self.indice),
                        PYTHONIOENCODING="utf-8", NO_COLOR="1")
        return subprocess.run([sys.executable, "cli.py", *args], cwd=str(RAIZ), env=ambiente,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)

    def test_curinga_na_pergunta_nao_vira_lista_de_arquivos(self):
        self.assertEqual(self.processo("sync").returncode, 0)
        for pergunta in ("*", "c*", "?"):
            with self.subTest(pergunta=pergunta):
                r = self.processo("buscar", pergunta)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn("unexpected extra arguments", r.stdout + r.stderr)
                self.assertIn("Nada encontrado", r.stdout)


class TestVault(Ambiente):
    def test_vault_ausente(self):
        self.sincronizar()
        ausente = self.tmp / "nao-existe"
        self.config(vault_dir=ausente)
        for comando in (("sync",), ("buscar", "reserva"), ("ask", "reserva")):
            with self.subTest(comando=comando):
                r = self.rodar(*comando)
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("nao-existe", r.texto)
                self.assertIn("BRAIN_VAULT_DIR", r.texto)
                self.assertNotIn("Traceback", r.output)
        self.assertFalse(ausente.exists())
        r = self.rodar("status")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("Ausente", r.texto)
        self.assertFalse(ausente.exists())

    def test_vault_dir_que_e_arquivo(self):
        arquivo = self.tmp / "vault.txt"
        arquivo.write_text("x", encoding="utf-8")
        self.config(vault_dir=arquivo)
        for comando in (("sync",), ("buscar", "reserva"), ("status",)):
            with self.subTest(comando=comando):
                r = self.rodar(*comando)
                self.assertEqual(r.exit_code, 0 if comando == ("status",) else 1, r.output)
                self.assertNotIn("Traceback", r.output)


class TestStatus(Ambiente):
    def test_status_pronto_mostra_contagens_e_servidor_opcional(self):
        self.sincronizar()
        r = self.rodar("status")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertRegex(r.texto, r"Pronto \S+ \d+ trechos em 3 notas")
        self.assertIn("Servidor de modelos", r.texto)
        self.assertIn("opcional", r.texto)
        self.assertNotIn("Qdrant", r.texto)

    def test_status_com_indice_invalido(self):
        self.indice.parent.mkdir(parents=True)
        self.indice.write_bytes(b"isto nao e um banco sqlite" * 200)
        r = self.rodar("status")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("Corrompido", r.texto)

    def test_status_avisa_sqlite_antigo(self):
        with mock.patch.object(cli.sqlite3, "sqlite_version_info", (3, 40, 0)), \
                mock.patch.object(cli.sqlite3, "sqlite_version", "3.40.0"):
            r = self.rodar("status")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("3.43", r.texto)
        self.assertIn("3.40.0", r.texto)


class TestAsk(Ambiente):
    def test_ask_ok(self):
        self.sincronizar()
        self.gerador(lambda sistema, usuario: "A reserva expira em quinze minutos.")
        r = self.rodar("ask", "reserva de estoque")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("A reserva expira em quinze minutos.", r.texto)
        self.assertIn("systems/estoque.md", r.texto)

    def test_ask_sem_servidor_de_modelos(self):
        self.sincronizar()

        def fora_do_ar(sistema, usuario):
            raise GeradorIndisponivel("ConnectError: conexao recusada")
        self.gerador(fora_do_ar)
        r = self.rodar("ask", "reserva de estoque")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("systems/estoque.md", r.texto)
        self.assertIn("não pôde ser gerada", r.texto)
        for proibido in ("Traceback", "ConnectError"):
            self.assertNotIn(proibido, r.output)

    def test_ask_sem_fontes_sai_0_e_nao_chama_o_gerador(self):
        self.sincronizar()
        chamadas = []
        self.gerador(lambda s, u: chamadas.append(1) or "x")
        r = self.rodar("ask", "zzqx wwyk")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertEqual(chamadas, [])

    def test_ask_sem_indice_sai_1(self):
        r = self.rodar("ask", "reserva de estoque")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("cli.py sync", r.texto)


class TestComandosRemovidos(unittest.TestCase):
    def test_drive_sync_nao_existe(self):
        self.assertEqual(CliRunner().invoke(cli.cli, ["drive-sync"]).exit_code, 2)

    def test_pull_models_sem_embed_model(self):
        self.assertEqual(CliRunner().invoke(cli.cli, ["pull-models", "--embed-model", "x"]).exit_code, 2)


if __name__ == "__main__":
    unittest.main()

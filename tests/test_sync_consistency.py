"""Testes da sincronização vault -> índice de texto (SQLite FTS5)."""
import hashlib
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import pytest

from config import settings
from core.chunker import MarkdownChunker
from core.hasher import calculate_file_hash, diferenca
from core.indice_texto import IndiceTexto, esquema_indice
from core.sync_lock import SyncBusy, sync_lock
from ingestion.sync import ReconstrucaoAbortada, SyncEngine


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


TRES_SECOES = "## S1\n\numbigo alfa\n\n## S2\n\nbeta dois\n\n## S3\n\ngama tres\n"
UMA_SECAO = "## S1\n\ntexto novo omega\n"


@pytest.fixture
def ambiente(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text(TRES_SECOES, encoding="utf-8")
    indice = IndiceTexto(tmp_path / "estado" / "indice.db")
    motor = SyncEngine(lock_path=tmp_path / "estado" / "sync.lock", store=indice, vault_dir=vault)
    return vault, indice, motor


def arquivos_buscados(indice, pergunta):
    return {r["payload"]["file_path"] for r in indice.buscar(pergunta, limit=10)}


# ---- chunker (continua valendo no desenho novo) ---------------------------------------------
class TestChunkBytes(unittest.TestCase):
    def test_crlf_bytes_match_text_mode_reading(self):
        raw = "## S1\r\n\r\ntexto um\r\n".encode("utf-8")
        chunks = MarkdownChunker().chunk_bytes(raw, "a.md")
        self.assertEqual(len(chunks), 1)
        self.assertNotIn("\r", chunks[0]["content"])
        self.assertEqual(chunks[0]["metadata"]["section"], "S1")

    def test_category_is_immediate_parent_like_chunk_file(self):
        chunker = MarkdownChunker()
        cases = {"a.md": "general", "adrs/x.md": "adrs", "architecture/full-cycle/x.md": "full-cycle"}
        for rel, category in cases.items():
            with self.subTest(rel=rel):
                chunks = chunker.chunk_bytes(UMA_SECAO.encode("utf-8"), rel)
                self.assertEqual(chunks[0]["metadata"]["category"], category)
                self.assertEqual(chunks[0]["metadata"]["file_path"], rel)
                self.assertEqual(chunks[0]["metadata"]["doc_title"], "X" if rel != "a.md" else "A")


# ---- diferença vault x manifesto ------------------------------------------------------------
def test_diferenca_classifica_novos_modificados_e_removidos(tmp_path):
    (tmp_path / "igual.md").write_text("x", encoding="utf-8")
    (tmp_path / "mudou.md").write_text("novo", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "novo.md").write_text("n", encoding="utf-8")
    manifesto = {
        "igual.md": calculate_file_hash(tmp_path / "igual.md"),
        "mudou.md": "0" * 64,
        "sumiu.md": "1" * 64,
    }
    novos, modificados, removidos = diferenca(tmp_path, manifesto)
    assert [p.relative_to(tmp_path).as_posix() for p in novos] == ["sub/novo.md"]
    assert [p.name for p in modificados] == ["mudou.md"]
    assert removidos == ["sumiu.md"]


# ---- sync incremental -----------------------------------------------------------------------
def test_primeiro_sync_reconstroi_e_marca(ambiente):
    vault, ix, motor = ambiente
    (vault / "b.md").write_text(UMA_SECAO, encoding="utf-8")
    res = motor.sync_vault(verbose=False)
    assert res["reconstruido"] is True
    assert res["added"] == 2 and res["modified"] == 0 and res["deleted"] == 0
    assert res["failed"] == 0 and res["chunks_indexed"] == 4
    assert set(ix.manifesto()) == {"a.md", "b.md"}
    assert ix.esquema_atual() == esquema_indice()


def test_sync_sem_mudanca_nao_escreve(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    antes = os.stat(ix.caminho).st_mtime_ns
    res = motor.sync_vault(verbose=False)
    assert res == {"added": 0, "modified": 0, "deleted": 0, "chunks_indexed": 0,
                   "failed": 0, "failed_files": [], "reconstruido": False}
    assert os.stat(ix.caminho).st_mtime_ns == antes


def test_nota_nova_modificada_e_removida(ambiente):
    vault, ix, motor = ambiente
    (vault / "b.md").write_text(UMA_SECAO, encoding="utf-8")
    motor.sync_vault(verbose=False)
    assert arquivos_buscados(ix, "omega") == {"b.md"}

    (vault / "c.md").write_text("## S1\n\nzeta nova\n", encoding="utf-8")
    (vault / "a.md").write_text("## S1\n\nsigma trocado\n", encoding="utf-8")
    (vault / "b.md").unlink()
    res = motor.sync_vault(verbose=False)
    assert (res["added"], res["modified"], res["deleted"]) == (1, 1, 1)
    assert res["reconstruido"] is False and res["chunks_indexed"] == 2
    assert arquivos_buscados(ix, "zeta") == {"c.md"}
    assert arquivos_buscados(ix, "sigma") == {"a.md"}
    assert arquivos_buscados(ix, "omega") == set()
    assert arquivos_buscados(ix, "umbigo") == set()
    assert set(ix.manifesto()) == {"a.md", "c.md"}


def test_nota_renomeada_move_o_indice(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    (vault / "a.md").rename(vault / "b.md")
    res = motor.sync_vault(verbose=False)
    assert (res["added"], res["deleted"]) == (1, 1)
    assert set(ix.manifesto()) == {"b.md"} and arquivos_buscados(ix, "umbigo") == {"b.md"}


def test_nota_que_vira_vazia_sai_da_busca_e_nao_volta_como_modificada(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    (vault / "a.md").write_text("---\ntype: nota\nstatus: ativo\n---\n", encoding="utf-8")
    assert motor.sync_vault(verbose=False)["modified"] == 1
    assert motor.sync_vault(verbose=False)["modified"] == 0
    assert arquivos_buscados(ix, "umbigo") == set()
    assert ix.total_trechos() == 0 and "a.md" in ix.manifesto()


def test_nota_ilegivel_nao_toca_o_indice_e_falha(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    (vault / "a.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
    antes = ix.manifesto()
    res = motor.sync_vault(verbose=False)
    assert res["failed"] == 1 and res["failed_files"] == ["a.md"]
    assert ix.manifesto() == antes and ix.total_trechos() == 3
    assert arquivos_buscados(ix, "umbigo") == {"a.md"}


def test_nota_ilegivel_nova_fica_fora_do_manifesto(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    (vault / "ruim.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
    res = motor.sync_vault(verbose=False)
    assert (res["failed"], res["failed_files"]) == (1, ["ruim.md"])
    assert "ruim.md" not in ix.manifesto() and "a.md" in ix.manifesto()


def test_esquema_diferente_reconstroi_sozinho(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    with closing(sqlite3.connect(ix.caminho)) as con:
        con.execute("update meta set valor = 'outro' where chave = 'esquema'")
        con.commit()
    assert ix.esquema_atual() == "outro"
    res = motor.sync_vault(verbose=False)
    assert res["reconstruido"] is True and res["added"] == 1
    assert ix.esquema_atual() == esquema_indice()


def test_indice_corrompido_reconstroi(ambiente):
    vault, ix, motor = ambiente
    ix.caminho.parent.mkdir(parents=True, exist_ok=True)
    ix.caminho.write_bytes(os.urandom(4096))
    res = motor.sync_vault(verbose=False)
    assert res["reconstruido"] is True
    assert arquivos_buscados(ix, "umbigo") == {"a.md"}



def test_indice_com_cabecalho_valido_e_tabelas_corrompidas_reconstroi(ambiente):
    vault, ix, motor = ambiente
    for j in range(20):
        (vault / f"n{j}.md").write_text("## S1\n\n" + "palavra zeta texto " * 200 + "\n", encoding="utf-8")
    motor.sync_vault(verbose=False)
    with closing(sqlite3.connect(ix.caminho)) as con:
        pagina = con.execute("pragma page_size").fetchone()[0]
    tamanho = ix.caminho.stat().st_size
    assert tamanho > 3 * pagina
    with open(ix.caminho, "r+b") as f:
        f.seek(3 * pagina)
        f.write(os.urandom(tamanho - 3 * pagina))
    assert ix.esquema_atual() == esquema_indice()  # o sync não percebe pelo esquema
    (vault / "nova.md").write_text(UMA_SECAO, encoding="utf-8")
    res = motor.sync_vault(verbose=False)
    assert res["reconstruido"] is True and res["added"] == 22
    assert arquivos_buscados(ix, "omega") == {"nova.md"}
    assert arquivos_buscados(ix, "umbigo") == {"a.md"}
    assert motor.sync_vault(verbose=False)["reconstruido"] is False


def test_vault_sem_mudanca_e_lixo_nas_ultimas_paginas_reconstroi_uma_vez(ambiente):
    vault, ix, motor = ambiente
    (vault / "a.md").unlink()
    for j in range(20):
        secoes = "".join(f"## S{i}\n\n" + f"palavra zeta texto {j} {i} " * 20 + "\n\n" for i in range(5))
        (vault / f"n{j}.md").write_text(secoes, encoding="utf-8")
    motor.sync_vault(verbose=False)
    total = ix.total_trechos()
    with closing(sqlite3.connect(ix.caminho)) as con:
        pagina = con.execute("pragma page_size").fetchone()[0]
    tamanho = ix.caminho.stat().st_size
    assert tamanho > 6 * pagina
    with open(ix.caminho, "r+b") as f:
        f.seek(tamanho - 4 * pagina)
        f.write(os.urandom(4 * pagina))
    # o defeito: contagem e esquema normais, busca vazia, vault igual ao manifesto
    assert ix.total_trechos() == total == 100 and len(ix.manifesto()) == 20
    assert ix.esquema_atual() == esquema_indice() and arquivos_buscados(ix, "zeta") == set()
    res = motor.sync_vault(verbose=False)
    assert res["reconstruido"] is True and res["added"] == 20
    assert arquivos_buscados(ix, "zeta") and ix.total_trechos() == 100
    assert motor.sync_vault(verbose=False) == {
        "added": 0, "modified": 0, "deleted": 0, "chunks_indexed": 0,
        "failed": 0, "failed_files": [], "reconstruido": False,
    }


def test_edicao_entre_diferenca_e_leitura_grava_os_bytes_novos(ambiente):  # INV-N05
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    (vault / "a.md").write_text("## S1\n\nprimeira edicao\n", encoding="utf-8")
    real = diferenca

    def diferenca_e_edita(*args, **kwargs):
        resultado = real(*args, **kwargs)
        (vault / "a.md").write_text(UMA_SECAO, encoding="utf-8")
        return resultado

    with mock.patch("ingestion.sync.diferenca", side_effect=diferenca_e_edita):
        motor.sync_vault(verbose=False)
    assert ix.manifesto()["a.md"] == sha256((vault / "a.md").read_bytes())
    assert arquivos_buscados(ix, "omega") == {"a.md"}
    assert motor.sync_vault(verbose=False)["modified"] == 0


def test_hash_do_manifesto_e_o_dos_bytes_fatiados(ambiente):  # INV-N05
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    lidos = {}
    real = motor.chunker.chunk_bytes

    def espia(raw, rel_path, *args, **kwargs):
        lidos[rel_path] = raw
        # edição concorrente: o arquivo muda no disco enquanto o sync fatia
        (vault / rel_path).write_text(UMA_SECAO, encoding="utf-8")
        return real(raw, rel_path, *args, **kwargs)

    (vault / "a.md").write_text("## S1\n\nedicao lida\n", encoding="utf-8")
    with mock.patch.object(motor.chunker, "chunk_bytes", side_effect=espia):
        motor.sync_vault(verbose=False)
    esperado = sha256(lidos["a.md"])
    assert ix.manifesto()["a.md"] == esperado
    with closing(sqlite3.connect(ix.caminho)) as con:
        hashes = {r[0] for r in con.execute("select doc_sha256 from trechos where file_path = 'a.md'")}
    assert hashes == {esperado}
    # o arquivo no disco já é outro: o próximo sync o percebe
    assert motor.sync_vault(verbose=False)["modified"] == 1


def test_trechos_levam_hash_e_espaco_do_perfil(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    with closing(sqlite3.connect(ix.caminho)) as con:
        linhas = con.execute("select doc_sha256, space_id from trechos").fetchall()
    assert len(linhas) == 3
    assert {(h, s) for h, s in linhas} == {(ix.manifesto()["a.md"], settings.space_id)}


def test_espaco_vem_das_configuracoes(ambiente):
    vault, ix, motor = ambiente
    with mock.patch.object(settings, "space_id", "outro"):
        motor.sync_vault(verbose=False)
    assert ix.total_trechos("outro") == 3 and ix.total_trechos(settings.space_id) == 0


def test_sync_ocupado_levanta_syncbusy(ambiente):
    vault, ix, motor = ambiente
    with sync_lock(motor.lock_path):
        with pytest.raises(SyncBusy):
            motor.sync_vault(verbose=False)
    assert not ix.caminho.exists()


def test_rebuild_tambem_respeita_o_lock(ambiente):
    vault, ix, motor = ambiente
    with sync_lock(motor.lock_path):
        for chamada in (motor.rebuild,):
            with pytest.raises(SyncBusy):
                chamada(verbose=False)


# ---- reconstrução ---------------------------------------------------------------------------
def test_rebuild_devolve_arquivos_trechos_e_esquema(ambiente):
    vault, ix, motor = ambiente
    (vault / "b.md").write_text(UMA_SECAO, encoding="utf-8")
    res = motor.rebuild(verbose=False)
    assert res == {"files": 2, "chunks": 4, "esquema": esquema_indice()}
    assert ix.esquema_atual() == esquema_indice() and ix.total_trechos() == 4


def test_rebuild_aborta_com_nota_ilegivel_e_preserva(ambiente):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    antes = ix.manifesto()
    (vault / "ruim.md").write_bytes(b"## S1\n\ntexto \xff\xfe invalido\n")
    with pytest.raises(ReconstrucaoAbortada) as e:
        motor.rebuild(verbose=False)
    assert e.value.arquivos == ["ruim.md"]
    assert ix.manifesto() == antes and ix.total_trechos() == 3


def test_sync_que_reconstroi_sozinho_aborta_com_nota_ilegivel(ambiente):
    vault, ix, motor = ambiente
    (vault / "ruim.md").write_bytes(b"\xff\xfe")
    with pytest.raises(ReconstrucaoAbortada) as e:
        motor.sync_vault(verbose=False)
    assert e.value.arquivos == ["ruim.md"]
    assert not ix.caminho.exists() or ix.manifesto() == {}


def test_rebuild_de_indice_corrompido(ambiente):
    vault, ix, motor = ambiente
    ix.caminho.parent.mkdir(parents=True, exist_ok=True)
    ix.caminho.write_bytes(os.urandom(2048))
    assert motor.rebuild(verbose=False)["files"] == 1
    assert arquivos_buscados(ix, "umbigo") == {"a.md"}


def test_sync_depois_do_rebuild_nao_faz_nada(ambiente):
    vault, ix, motor = ambiente
    motor.rebuild(verbose=False)
    res = motor.sync_vault(verbose=False)
    assert (res["added"], res["modified"], res["deleted"], res["reconstruido"]) == (0, 0, 0, False)


def test_vault_vazio_reconstroi_indice_vazio(ambiente):
    vault, ix, motor = ambiente
    (vault / "a.md").unlink()
    assert motor.rebuild(verbose=False) == {"files": 0, "chunks": 0, "esquema": esquema_indice()}
    assert ix.manifesto() == {} and ix.total_trechos() == 0


def test_pasta_do_vault_inexistente_e_erro_e_preserva_o_indice(ambiente, tmp_path):
    vault, ix, motor = ambiente
    motor.sync_vault(verbose=False)
    antes = (ix.manifesto(), ix.total_trechos())
    motor.vault_dir = tmp_path / "nao-existe"
    for chamada in (motor.sync_vault, motor.rebuild):
        with pytest.raises(FileNotFoundError, match="Pasta do vault não encontrada"):
            chamada(verbose=False)
        assert (ix.manifesto(), ix.total_trechos()) == antes


def test_vault_que_e_arquivo_e_erro_mesmo_sem_indice(ambiente, tmp_path):
    vault, ix, motor = ambiente
    arquivo = tmp_path / "vault.txt"
    arquivo.write_text("x", encoding="utf-8")
    motor.vault_dir = arquivo
    with pytest.raises(FileNotFoundError, match="Pasta do vault não encontrada"):
        motor.sync_vault(verbose=False)
    assert not ix.caminho.exists()


def test_motor_padrao_usa_o_indice_e_o_vault_das_configuracoes(tmp_path):
    with mock.patch.object(settings, "index_path", tmp_path / "padrao.db"):
        motor = SyncEngine(lock_path=tmp_path / "sync.lock")
    assert motor.vault_dir == settings.vault_dir
    assert isinstance(motor.store, IndiceTexto)


class TestCli(unittest.TestCase):
    """cli.py sync: reconstrução, --yes ignorado e mensagens de erro."""

    SYNC_OK = {"added": 1, "modified": 2, "deleted": 3, "chunks_indexed": 4, "failed": 0,
               "failed_files": [], "reconstruido": False}
    REBUILD_OK = {"files": 8, "chunks": 9, "esquema": "abc123"}

    def setUp(self):
        import importlib
        import importlib.util
        import sys
        import types

        import click
        from click.testing import CliRunner

        # cli.py importa scripts.sanitize no fim do modulo; se ele nao existe neste checkout,
        # um stub (so durante o teste) deixa o grupo carregar. sys.modules e restaurado no fim.
        modules = mock.patch.dict(sys.modules)
        modules.start()
        self.addCleanup(modules.stop)
        sys.modules.pop("cli", None)
        try:
            real_sanitize = importlib.util.find_spec("scripts.sanitize") is not None
        except ImportError:
            real_sanitize = False
        if not real_sanitize:
            stub = types.ModuleType("scripts.sanitize")
            stub.sanitize_cmd = click.Command("sanitize", callback=lambda: None)
            sys.modules["scripts.sanitize"] = stub
        cli_module = importlib.import_module("cli")

        self.cli = cli_module.cli
        self.runner = CliRunner()
        patcher = mock.patch("ingestion.sync.SyncEngine")
        self.engine = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.engine.sync_vault.return_value = dict(self.SYNC_OK)
        self.engine.rebuild.return_value = dict(self.REBUILD_OK)

    def invoke(self, *args):
        result = self.runner.invoke(self.cli, ["sync", *args])
        # o console do cli e forcado a terminal: remove as sequencias ANSI antes de comparar
        result.output_text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        return result

    def test_sync_simples_imprime_painel_e_sai_0(self):
        result = self.invoke()
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.assertIn("Sincronizando o Vault...", result.output_text)
        self.assertIn("Sincronização Concluída", result.output_text)
        self.engine.sync_vault.assert_called_once()
        self.engine.rebuild.assert_not_called()

    def test_cli_rebuild_nao_exige_yes(self):
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.engine.rebuild.assert_called_once_with(verbose=True)
        self.assertIn("Reconstruindo o índice do Vault...", result.output_text)
        for valor in ("Arquivos: 8", "Blocos: 9", "Esquema: abc123"):
            self.assertIn(valor, result.output_text)
        for proibida in ("Coleção", "alias", "Qdrant", "vetorial"):
            self.assertNotIn(proibida, result.output_text)

    def test_cli_yes_e_aceito_e_ignorado(self):
        result = self.invoke("--rebuild", "--yes")
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.engine.rebuild.assert_called_once_with(verbose=True)
        result = self.invoke("--yes")
        self.assertEqual(result.exit_code, 0, result.output_text)
        self.engine.sync_vault.assert_called_once()

    def test_cli_sync_com_falha_sai_1(self):
        self.engine.sync_vault.return_value = dict(self.SYNC_OK, failed=2, failed_files=["a.md", "b.md"])
        result = self.invoke()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Sincronização com falhas", result.output_text)

    def test_cli_reconstrucao_abortada_sai_1_e_lista_os_arquivos(self):
        for args in ((), ("--rebuild",)):
            with self.subTest(args=args):
                erro = ReconstrucaoAbortada(["ruim.md", "sub/outra.md"])
                self.engine.sync_vault.side_effect = erro
                self.engine.rebuild.side_effect = erro
                result = self.invoke(*args)
                self.assertEqual(result.exit_code, 1, result.output_text)
                self.assertIn("ruim.md", result.output_text)
                self.assertIn("sub/outra.md", result.output_text)
                self.assertNotIn("Erro ao sincronizar", result.output_text)

    def test_mensagem_de_lock_ocupado(self):
        self.engine.sync_vault.side_effect = SyncBusy()
        self.engine.rebuild.side_effect = SyncBusy()
        for args in ((), ("--rebuild",)):
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.exit_code, 1)
                self.assertIn("Outro sync está em andamento.", result.output_text)

    def test_erro_generico_mantem_mensagem_e_sai_1(self):
        self.engine.rebuild.side_effect = RuntimeError("disco cheio")
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Erro ao sincronizar:", result.output_text)
        self.assertIn("disco cheio", result.output_text)

    def test_reconcile_nao_existe(self):
        result = self.invoke("--reconcile")
        self.assertEqual(result.exit_code, 2)
        self.engine.rebuild.assert_not_called()

    def test_vault_ausente_diz_onde_procurou_e_como_apontar(self):
        self.engine.sync_vault.side_effect = FileNotFoundError("Pasta do vault não encontrada: /tmp/nao-existe")
        result = self.invoke()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("nao-existe", result.output_text)
        self.assertIn("BRAIN_VAULT_DIR", result.output_text)
        self.assertNotIn("Traceback", result.output_text)

    def test_drive_sync_nao_existe(self):
        result = self.runner.invoke(self.cli, ["drive-sync"])
        self.assertEqual(result.exit_code, 2)

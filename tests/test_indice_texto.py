import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from config import settings
from core import indice_texto
from core.indice_texto import IndiceIndisponivel, IndiceTexto, esquema_indice


def _chunk(rel, i, texto, **meta):
    metadata = {
        "file_path": rel,
        "doc_title": "Titulo",
        "section": "Secao",
        "category": "systems",
        "chunk_index": i,
        "line_start": 1,
        "line_end": 5,
        "doc_sha256": "d",
        "space_id": "principal",
    }
    metadata.update(meta)
    return {"id": f"{rel}#{i}", "content": f"# Titulo\n## Secao\n\n{texto}", "metadata": metadata}


def test_substituir_grava_trechos_e_hash_juntos(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.substituir_arquivo("a.md", "h1", [_chunk("a.md", 0, "um"), _chunk("a.md", 1, "dois")])
    assert ix.manifesto() == {"a.md": "h1"} and ix.total_trechos() == 2


def test_substituir_troca_os_trechos_antigos(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.substituir_arquivo("a.md", "h1", [_chunk("a.md", 0, "um"), _chunk("a.md", 1, "dois")])
    ix.substituir_arquivo("a.md", "h2", [_chunk("a.md", 0, "tres")])
    assert ix.total_trechos() == 1 and ix.manifesto() == {"a.md": "h2"}
    with closing(sqlite3.connect(tmp_path / "i.db")) as con:
        assert con.execute("select count(*) from trechos_fts_docsize").fetchone()[0] == 1


def test_nota_vazia_fica_no_manifesto_sem_trechos(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.substituir_arquivo("a.md", "h", [])
    assert ix.manifesto() == {"a.md": "h"} and ix.total_trechos() == 0


def test_remover_apaga_trechos_e_manifesto(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.substituir_arquivo("a.md", "h1", [_chunk("a.md", 0, "um")])
    ix.substituir_arquivo("b.md", "h2", [_chunk("b.md", 0, "dois")])
    ix.remover_arquivo("a.md")
    assert ix.manifesto() == {"b.md": "h2"} and ix.total_trechos() == 1


def test_total_por_espaco(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.substituir_arquivo("a.md", "h1", [_chunk("a.md", 0, "um"), _chunk("a.md", 1, "dois")])
    ix.substituir_arquivo("b.md", "h2", [_chunk("b.md", 0, "tres", space_id="outro")])
    assert ix.total_trechos("principal") == 2
    assert ix.total_trechos("outro") == 1
    assert ix.total_trechos() == 3


def test_reconstruir_grava_esquema_e_data(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    r = ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")]), ("b.md", "h2", [])])
    assert r == {"files": 2, "chunks": 1} and ix.esquema_atual() == esquema_indice()
    assert ix.versao().startswith(esquema_indice() + "@")


def test_reconstruir_falha_no_meio_preserva_o_anterior(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])

    def itens():
        yield ("b.md", "h2", [_chunk("b.md", 0, "dois")])
        raise RuntimeError("quebra")

    with pytest.raises(RuntimeError):
        ix.reconstruir(itens())
    assert ix.manifesto() == {"a.md": "h1"} and ix.total_trechos() == 1


def _sql_fts(caminho):
    with closing(sqlite3.connect(caminho)) as con:
        return con.execute("select sql from sqlite_master where name = 'trechos_fts'").fetchone()[0]


def test_reconstruir_recria_as_tabelas_com_o_tokenizador_novo(tmp_path, monkeypatch):
    p = tmp_path / "i.db"
    ix = IndiceTexto(p)
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])
    assert "remove_diacritics 2" in _sql_fts(p)
    antes = esquema_indice()
    monkeypatch.setattr(indice_texto, "TOKENIZADOR", "unicode61 remove_diacritics 0")
    assert esquema_indice() != antes
    ix.reconstruir([("b.md", "h2", [_chunk("b.md", 0, "dois")])])
    assert "unicode61 remove_diacritics 0" in _sql_fts(p)
    assert ix.esquema_atual() == esquema_indice()
    assert ix.manifesto() == {"b.md": "h2"} and ix.total_trechos() == 1


def test_reconstrucao_que_falha_depois_do_drop_preserva_tabelas_e_dados(tmp_path, monkeypatch):
    p = tmp_path / "i.db"
    ix = IndiceTexto(p)
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])
    sql_antes, esquema_antes = _sql_fts(p), ix.esquema_atual()
    monkeypatch.setattr(indice_texto, "TOKENIZADOR", "unicode61 remove_diacritics 0")

    def itens():
        yield ("b.md", "h2", [_chunk("b.md", 0, "dois")])
        raise RuntimeError("quebra")

    with pytest.raises(RuntimeError, match="quebra"):
        ix.reconstruir(itens())
    assert _sql_fts(p) == sql_antes and ix.esquema_atual() == esquema_antes
    assert ix.manifesto() == {"a.md": "h1"} and ix.total_trechos() == 1
    assert [h["payload"]["file_path"] for h in ix.buscar("titulo")] == ["a.md"]


def test_leitor_ve_o_indice_anterior_durante_a_reconstrucao(tmp_path):
    caminho = tmp_path / "i.db"
    ix = IndiceTexto(caminho)
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])
    vistos = {}

    def itens():
        leitor = IndiceTexto(caminho)
        vistos["total"] = leitor.total_trechos()
        vistos["manifesto"] = leitor.manifesto()
        yield ("b.md", "h2", [_chunk("b.md", 0, "dois"), _chunk("b.md", 1, "tres")])

    ix.reconstruir(itens())
    assert vistos == {"total": 1, "manifesto": {"a.md": "h1"}}
    assert ix.total_trechos() == 2 and ix.manifesto() == {"b.md": "h2"}


def test_arquivo_ausente_e_indice_vazio(tmp_path):
    ix = IndiceTexto(tmp_path / "nao-existe.db")
    assert ix.total_trechos() == 0 and ix.manifesto() == {} and ix.esquema_atual() is None and ix.versao() == "vazio"
    assert not (tmp_path / "nao-existe.db").exists()


def test_arquivo_corrompido_le_como_vazio_e_escrita_recria(tmp_path):
    p = tmp_path / "i.db"
    p.write_bytes(os.urandom(4096))
    ix = IndiceTexto(p)
    assert ix.total_trechos() == 0 and ix.manifesto() == {}
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])
    assert ix.total_trechos() == 1
    assert (tmp_path / "i.db.corrompido").exists()


def _indice_com_trechos(p):
    ix = IndiceTexto(p)
    ix.reconstruir([
        (f"n{j}.md", "h", [_chunk(f"n{j}.md", i, f"palavra zeta texto {j} {i} " * 20) for i in range(5)])
        for j in range(20)
    ])
    return ix


def _tamanho_de_pagina(p):
    with closing(sqlite3.connect(p)) as con:
        return con.execute("pragma page_size").fetchone()[0]


def _confere_recuperacao(ix, p):
    assert ix.buscar("zeta") == []
    ix.total_trechos()
    ix.manifesto()
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "omega")])])
    assert [h["payload"]["file_path"] for h in ix.buscar("omega")] == ["a.md"]
    assert ix.esquema_atual() == esquema_indice()
    assert Path(str(p) + ".corrompido").exists()


def test_cabecalho_valido_e_resto_lixo_le_vazio_e_reconstroi(tmp_path):
    p = tmp_path / "i.db"
    ix = _indice_com_trechos(p)
    pagina, tamanho = _tamanho_de_pagina(p), p.stat().st_size
    assert tamanho > 3 * pagina
    with open(p, "r+b") as f:
        f.seek(3 * pagina)
        f.write(os.urandom(tamanho - 3 * pagina))
    _confere_recuperacao(ix, p)


def test_arquivo_truncado_pela_metade_le_vazio_e_reconstroi(tmp_path):
    p = tmp_path / "i.db"
    ix = _indice_com_trechos(p)
    with open(p, "r+b") as f:
        f.truncate(p.stat().st_size // 2)
    _confere_recuperacao(ix, p)


def _sobrescreve_ultimas_paginas(p, paginas=4):
    """Lixo nas últimas `paginas` páginas do arquivo, sem conexão aberta (cenário do defeito)."""
    pagina, tamanho = _tamanho_de_pagina(p), p.stat().st_size
    assert tamanho > (paginas + 2) * pagina
    with open(p, "r+b") as f:
        f.seek(tamanho - paginas * pagina)
        f.write(os.urandom(paginas * pagina))


# ---- prova de integridade ---------------------------------------------------------------
def test_verificar_acusa_lixo_nas_ultimas_paginas_que_a_leitura_esconde(tmp_path):
    p = tmp_path / "i.db"
    ix = _indice_com_trechos(p)
    _sobrescreve_ultimas_paginas(p)
    # o defeito: contagem e esquema normais, busca vazia em silêncio
    assert len(ix.manifesto()) == 20 and ix.total_trechos() == 100
    assert ix.esquema_atual() == esquema_indice() and ix.buscar("zeta") == []
    assert ix.verificar() is False


def test_verificar_indice_integro(tmp_path):
    ix = _indice_com_trechos(tmp_path / "i.db")
    assert ix.verificar() is True


def test_verificar_arquivo_ausente_nao_cria(tmp_path):
    p = tmp_path / "nao-existe.db"
    assert IndiceTexto(p).verificar() is True
    assert list(tmp_path.iterdir()) == []


def test_verificar_cabecalho_valido_e_resto_lixo(tmp_path):
    p = tmp_path / "i.db"
    ix = _indice_com_trechos(p)
    pagina, tamanho = _tamanho_de_pagina(p), p.stat().st_size
    with open(p, "r+b") as f:
        f.seek(3 * pagina)
        f.write(os.urandom(tamanho - 3 * pagina))
    assert ix.verificar() is False


def test_verificar_arquivo_truncado(tmp_path):
    p = tmp_path / "i.db"
    ix = _indice_com_trechos(p)
    with open(p, "r+b") as f:
        f.truncate(p.stat().st_size // 2)
    assert ix.verificar() is False


def test_verificar_arquivo_que_nao_e_banco(tmp_path):
    p = tmp_path / "i.db"
    p.write_bytes(os.urandom(4096))
    assert IndiceTexto(p).verificar() is False


def test_verificar_erro_que_nao_e_de_corrupcao_propaga(tmp_path, monkeypatch):
    ix = _indice_com_trechos(tmp_path / "i.db")

    def travado():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ix, "_conectar_leitura", travado)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        ix.verificar()


def test_verificar_nao_altera_o_arquivo(tmp_path):
    p = tmp_path / "i.db"
    ix = _indice_com_trechos(p)
    antes = p.read_bytes()
    assert ix.verificar() is True
    assert p.read_bytes() == antes


def test_arquivo_que_nao_e_indice_e_preservado_ao_lado(tmp_path):
    p = tmp_path / "i.db"
    original = "Isto é um arquivo de texto qualquer, não um índice.\n" * 50
    p.write_text(original, encoding="utf-8")
    ix = IndiceTexto(p)
    ix.substituir_arquivo("a.md", "h1", [_chunk("a.md", 0, "um")])
    assert (tmp_path / "i.db.corrompido").read_text(encoding="utf-8") == original
    assert ix.manifesto() == {"a.md": "h1"}


def test_corrompido_anterior_e_substituido(tmp_path):
    p = tmp_path / "i.db"
    (tmp_path / "i.db.corrompido").write_text("velho", encoding="utf-8")
    p.write_text("novo lixo " * 100, encoding="utf-8")
    IndiceTexto(p).reconstruir([])
    assert (tmp_path / "i.db.corrompido").read_text(encoding="utf-8") == "novo lixo " * 100


def test_corrompido_em_uso_da_erro_claro(tmp_path, monkeypatch):
    p = tmp_path / "i.db"
    p.write_text("lixo " * 1000, encoding="utf-8")

    def em_uso(*_a, **_k):
        raise PermissionError(13, "O arquivo já está sendo usado por outro processo")

    monkeypatch.setattr(indice_texto.os, "replace", em_uso)
    with pytest.raises(indice_texto.IndiceCorrompidoEmUso, match="corrompido.*em uso") as info:
        IndiceTexto(p).reconstruir([])
    assert "lixo" not in str(info.value)
    assert p.read_text(encoding="utf-8") == "lixo " * 1000


def test_eh_corrupcao():
    for mensagem in ("file is not a database", "database disk image is malformed",
                     "vtable constructor failed: trechos_fts"):
        assert indice_texto.eh_corrupcao(sqlite3.DatabaseError(mensagem))
    assert not indice_texto.eh_corrupcao(sqlite3.OperationalError("database is locked"))
    assert not indice_texto.eh_corrupcao(RuntimeError("database disk image is malformed"))


def test_erro_que_nao_e_de_corrupcao_propaga_na_reconstrucao(tmp_path, monkeypatch):
    p = tmp_path / "i.db"
    ix = IndiceTexto(p)
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])

    def travado():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ix, "_conectar", travado)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        ix.reconstruir([])
    assert not (tmp_path / "i.db.corrompido").exists()


def test_estatisticas(tmp_path):
    ix = IndiceTexto(tmp_path / "i.db")
    ix.reconstruir([
        ("a.md", "h1", [_chunk("a.md", 0, "um"), _chunk("a.md", 1, "dois")]),
        ("b.md", "h2", [_chunk("b.md", 0, "tres", category="adrs")]),
    ])
    est = ix.estatisticas()
    assert est["points_count"] == 3
    assert est["arquivos"] == 2
    assert est["esquema"] == esquema_indice()
    assert est["por_categoria"] == {"systems": 2, "adrs": 1}
    from datetime import datetime
    assert datetime.fromisoformat(est["construido_em"]).utcoffset().total_seconds() == 0


def test_esquema_muda_com_o_tamanho_do_trecho(monkeypatch):
    antes = esquema_indice()
    monkeypatch.setattr(settings, "chunk_size", settings.chunk_size + 1)
    assert esquema_indice() != antes
    assert len(antes) == 12


def test_fts5_disponivel():
    from core.indice_texto import ddl

    with closing(sqlite3.connect(":memory:")) as con:
        con.executescript(ddl())
        con.execute("select count(*) from trechos_fts").fetchone()


class _ConexaoQueFalhaNaDdl:
    def __init__(self, real, erro):
        self._real, self._erro = real, erro

    def executescript(self, _sql):
        raise self._erro

    def __getattr__(self, nome):
        return getattr(self._real, nome)


def test_erro_que_nao_e_de_corrupcao_propaga_na_leitura(tmp_path, monkeypatch):
    p = tmp_path / "i.db"
    ix = IndiceTexto(p)
    ix.reconstruir([("a.md", "h1", [_chunk("a.md", 0, "um")])])

    def travado():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ix, "_conectar", travado)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        ix.total_trechos()
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        ix.manifesto()


def test_ddl_sem_fts5_vira_indice_indisponivel(tmp_path, monkeypatch):
    ix = IndiceTexto(tmp_path / "i.db")
    original = ix._conectar
    monkeypatch.setattr(
        ix, "_conectar",
        lambda: _ConexaoQueFalhaNaDdl(original(), sqlite3.OperationalError("no such module: fts5")),
    )
    with pytest.raises(IndiceIndisponivel, match=sqlite3.sqlite_version):
        ix.substituir_arquivo("a.md", "h", [])


def test_outro_erro_operacional_na_ddl_nao_e_convertido(tmp_path, monkeypatch):
    ix = IndiceTexto(tmp_path / "i.db")
    original = ix._conectar
    monkeypatch.setattr(
        ix, "_conectar",
        lambda: _ConexaoQueFalhaNaDdl(original(), sqlite3.OperationalError("database is locked")),
    )
    with pytest.raises(sqlite3.OperationalError, match="locked") as info:
        ix.substituir_arquivo("a.md", "h", [])
    assert not isinstance(info.value, IndiceIndisponivel)


# ---- busca ------------------------------------------------------------------------------
def _nota(rel, titulo, secao, trechos, **meta):
    return [
        _chunk(rel, i, t, doc_title=titulo, section=secao, file_path=rel, **meta)
        for i, t in enumerate(trechos)
    ]


@pytest.fixture
def ix(tmp_path):
    ix = IndiceTexto(tmp_path / "busca.db")
    notas = {
        "rules/regra-006.md": _nota(
            "rules/regra-006.md", "Regra de devolucao", "Corpo",
            ["A devolução de reserva vencida exige conferir o registro antes de repetir."],
            category="rules", bounded_context="atendimento",
        ),
        "systems/central-pedidos-verificacao.md": _nota(
            "systems/central-pedidos-verificacao.md", "Verificacao previa", "Visao geral",
            ["Descreve a checagem feita antes do envio de cada pedido."],
            category="systems",
        ),
        "systems/alfa.md": _nota(
            "systems/alfa.md", "Fila de pedidos", "Visao geral",
            ["Texto qualquer sobre outro assunto."], category="systems",
        ),
        "systems/beta.md": _nota(
            "systems/beta.md", "Outro assunto", "Visao geral",
            ["A fila de pedidos aparece só aqui, no corpo."], category="systems",
        ),
        "domain/gama.md": _nota(
            "domain/gama.md", "Reservador de salas", "Resumo",
            ["O reservador marca a sala do evento."], category="domain", space_id="outro",
        ),
        "domain/multi.md": _nota(
            "domain/multi.md", "Notas de lote", "Resumo",
            [f"Lote {i} com palavra zeta repetida zeta." for i in range(5)], category="domain",
        ),
        "domain/solo1.md": _nota("domain/solo1.md", "Primeira", "Resumo", ["zeta no corpo."], category="domain"),
        "domain/solo2.md": _nota("domain/solo2.md", "Segunda", "Resumo", ["zeta no corpo."], category="domain"),
    }
    for rel, chunks in notas.items():
        ix.substituir_arquivo(rel, "h", chunks)
    return ix


def test_busca_acha_pelo_corpo_e_devolve_o_payload(ix):
    hits = ix.buscar("devolução de reserva vencida", limit=3)
    assert hits[0]["payload"]["file_path"] == "rules/regra-006.md"
    assert set(hits[0]["payload"]) >= {
        "chunk_id", "content", "doc_title", "section", "category",
        "line_start", "line_end", "doc_sha256", "space_id",
    }
    assert hits[0]["score"] > 0 and hits == sorted(hits, key=lambda h: -h["score"])


def test_titulo_pesa_mais_que_corpo(ix):
    hits = ix.buscar("fila pedidos", limit=4)
    caminhos = [h["payload"]["file_path"] for h in hits]
    assert caminhos.index("systems/alfa.md") < caminhos.index("systems/beta.md")


def test_caminho_e_pesquisavel(ix):
    hits = ix.buscar("central pedidos verificacao", limit=3)
    assert hits[0]["payload"]["file_path"] == "systems/central-pedidos-verificacao.md"


def test_acento_e_caixa_nao_importam(ix):
    hits = ix.buscar("DEVOLUCAO", limit=5)
    assert "rules/regra-006.md" in [h["payload"]["file_path"] for h in hits]


def test_radical_casa_variacoes(ix):
    hits = ix.buscar("reservas", limit=5)
    assert "domain/gama.md" in [h["payload"]["file_path"] for h in hits]


def test_um_trecho_por_nota(ix):
    hits = ix.buscar("zeta", limit=3, per_doc=1)
    caminhos = [h["payload"]["file_path"] for h in hits]
    assert len(hits) == 3 and len(set(caminhos)) == 3


def test_per_doc_limita_trechos_por_nota_e_notas_por_limit(ix):
    hits = ix.buscar("zeta", limit=2, per_doc=2)
    caminhos = [h["payload"]["file_path"] for h in hits]
    assert len(set(caminhos)) <= 2
    assert all(caminhos.count(c) <= 2 for c in caminhos)
    assert hits == sorted(hits, key=lambda h: -h["score"])


def test_sem_per_doc_devolve_trechos_da_mesma_nota(ix):
    hits = ix.buscar("zeta", limit=5)
    caminhos = [h["payload"]["file_path"] for h in hits]
    assert len(hits) == 5 and caminhos.count("domain/multi.md") >= 2


def test_filtro_de_espaco_categoria_e_contexto(ix):
    def caminhos(**filtros):
        return {h["payload"]["file_path"] for h in ix.buscar("reservador reserva", limit=10, **filtros)}

    assert caminhos(space_id="outro") == {"domain/gama.md"}
    assert caminhos(category="rules") == {"rules/regra-006.md"}
    assert caminhos(bounded_context="atendimento") == {"rules/regra-006.md"}
    assert caminhos(space_id="principal", category="rules") == {"rules/regra-006.md"}
    assert caminhos(space_id="outro", category="rules") == set()


def test_pergunta_sem_termos_devolve_vazio_sem_consultar(ix, monkeypatch):
    def nao_deve_ler(*a, **k):
        raise AssertionError("tocou o banco")

    monkeypatch.setattr(ix, "_ler", nao_deve_ler)
    assert ix.buscar("de para o") == []


def test_indice_ausente_devolve_vazio(tmp_path):
    assert IndiceTexto(tmp_path / "nao-existe.db").buscar("nota") == []


def test_sintaxe_do_fts_na_pergunta_nao_levanta(ix):
    for entrada in ['"', '*', 'NEAR(nota fila)', 'titulo:nota', '-nota', '(nota OR', 'nota OR', "nota'; drop table trechos;--"]:
        ix.buscar(entrada)
    assert ix.total_trechos() > 0


def test_campo_opcional_nulo_nao_entra_no_payload(ix):
    por_caminho = {h["payload"]["file_path"]: h["payload"] for h in ix.buscar("devolução reservador", limit=5)}
    assert por_caminho["rules/regra-006.md"]["bounded_context"] == "atendimento"
    assert "bounded_context" not in por_caminho["domain/gama.md"]
    assert "related" not in por_caminho["domain/gama.md"]


def test_erro_que_nao_e_de_corrupcao_propaga_na_busca(ix, monkeypatch):
    def bloqueado(self):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(IndiceTexto, "_conectar", bloqueado)
    with pytest.raises(sqlite3.OperationalError):
        ix.buscar("nota")

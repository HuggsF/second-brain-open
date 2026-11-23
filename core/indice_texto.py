"""Índice de busca textual em SQLite (tabelas comuns + FTS5) do vault.

Esta classe cuida do esquema, da escrita, da leitura de estado e da busca BM25 por colunas.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import settings
from core.consulta_texto import expressao_match

VERSAO_SQL = 1
TOKENIZADOR = "unicode61 remove_diacritics 2"
COLUNAS_FTS = ["titulo", "secao", "caminho", "corpo"]
PESOS = (4.0, 2.0, 3.0, 1.0)  # título, seção, caminho, corpo
CANDIDATOS = 400

def ddl() -> str:
    """DDL do índice, montada na hora com o `TOKENIZADOR` vigente."""
    return f"""
create table if not exists meta (chave text primary key, valor text not null);
create table if not exists arquivos (file_path text primary key, sha256 text not null);
create table if not exists trechos (
  id integer primary key,
  chunk_id text not null unique,
  file_path text not null,
  space_id text not null,
  doc_sha256 text not null,
  doc_title text, section text, category text,
  chunk_index integer, line_start integer, line_end integer,
  status text, doc_type text, related text, bounded_context text, entities text,
  content text not null
);
create index if not exists trechos_arquivo on trechos(file_path);
create virtual table if not exists trechos_fts using fts5(
  titulo, secao, caminho, corpo,
  content='', contentless_delete=1, tokenize="{TOKENIZADOR}"
);
"""


def _instrucoes_ddl() -> list[str]:
    """A DDL instrução por instrução, para `execute` dentro de uma transação aberta."""
    return [i.strip() for i in ddl().split(";") if i.strip()]


_DROPS = (
    "drop table if exists trechos_fts",
    "drop index if exists trechos_arquivo",
    "drop table if exists trechos",
    "drop table if exists arquivos",
    "drop table if exists meta",
)

_COLUNAS_TRECHO = (
    "chunk_id", "file_path", "space_id", "doc_sha256", "doc_title", "section", "category",
    "chunk_index", "line_start", "line_end", "status", "doc_type", "related",
    "bounded_context", "entities", "content",
)


_OPCIONAIS = ("status", "doc_type", "related", "bounded_context", "entities")
_CAMPOS_PAYLOAD = (
    "chunk_id", "content", "file_path", "doc_title", "section", "category",
    "chunk_index", "line_start", "line_end", "doc_sha256", "space_id",
)

# Arquivo de índice corrompido: a escrita põe o arquivo de lado e reconstrói do zero.
_MARCAS_ARQUIVO_CORROMPIDO = ("not a database", "malformed", "vtable constructor failed")
# Na leitura, tabela ou coluna ausente também é índice ilegível: devolve vazio.
_MARCAS_CORRUPCAO = (*_MARCAS_ARQUIVO_CORROMPIDO, "no such table", "no such column")
_MARCAS_SEM_FTS5 = ("fts5", "contentless_delete", "no such module")
SUFIXO_CORROMPIDO = ".corrompido"


class IndiceIndisponivel(RuntimeError):
    """SQLite sem FTS5 ou sem `contentless_delete`."""


class IndiceCorrompidoEmUso(RuntimeError):
    """Índice corrompido que não pôde ser posto de lado porque outro processo o tem aberto."""


def eh_corrupcao(exc: BaseException) -> bool:
    """Erro do SQLite que indica arquivo de índice corrompido (e não, por exemplo, lock)."""
    return isinstance(exc, sqlite3.DatabaseError) and any(
        m in str(exc).lower() for m in _MARCAS_ARQUIVO_CORROMPIDO
    )


def _repetivel(itens: Iterable):
    """Permite percorrer `itens` de novo do início sem pedir de novo o que o gerador já deu."""
    lidos, fonte = [], iter(itens)

    def percorrer():
        yield from list(lidos)
        for item in fonte:
            lidos.append(item)
            yield item

    return percorrer


def _desfazer(con: sqlite3.Connection) -> None:
    """Rollback que não esconde o erro original (transação já desfeita ou arquivo ilegível)."""
    try:
        if con.in_transaction:
            con.execute("rollback")
    except sqlite3.Error:
        pass


def esquema_indice() -> str:
    carga = json.dumps([VERSAO_SQL, TOKENIZADOR, COLUNAS_FTS, settings.chunk_size, settings.chunk_overlap])
    return hashlib.sha256(carga.encode("utf-8")).hexdigest()[:12]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texto(valor):
    if valor is None:
        return None
    if isinstance(valor, (list, tuple, dict)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor)


def _linha_trecho(chunk: dict) -> tuple:
    meta = chunk.get("metadata", {})
    valores = {**meta, "chunk_id": chunk["id"], "content": chunk["content"]}
    return tuple(
        valores.get(c) if c in ("chunk_index", "line_start", "line_end") else _texto(valores.get(c))
        for c in _COLUNAS_TRECHO
    )


def _corpo(conteudo: str) -> str:
    partes = conteudo.split("\n\n", 1)
    return partes[1] if len(partes) == 2 else conteudo


class IndiceTexto:
    def __init__(self, caminho: Path | None = None):
        self.caminho = Path(caminho) if caminho is not None else Path(settings.index_path)

    # ---- conexão ----------------------------------------------------------------------
    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.caminho, timeout=30, isolation_level=None)
        try:
            con.execute("pragma journal_mode=wal")
            con.execute("pragma busy_timeout=30000")
        except BaseException:
            con.close()
            raise
        return con

    def _conectar_leitura(self) -> sqlite3.Connection:
        """Conexão só de leitura (`mode=ro`): não escreve no arquivo principal nem o cria."""
        return sqlite3.connect(f"{self.caminho.resolve().as_uri()}?mode=ro", uri=True, timeout=30)

    def _por_de_lado(self) -> None:
        """Renomeia o arquivo corrompido para `<nome>.corrompido` e apaga só `-wal` e `-shm`.

        Nunca apaga o arquivo principal: se o caminho apontar por engano para outro arquivo,
        ele fica preservado ao lado.
        """
        destino = Path(str(self.caminho) + SUFIXO_CORROMPIDO)
        try:
            os.replace(self.caminho, destino)
            for sufixo in ("-wal", "-shm"):
                Path(str(self.caminho) + sufixo).unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise IndiceCorrompidoEmUso(
                f"O índice de busca em {self.caminho} está corrompido e em uso por outro processo; "
                "feche os processos que o usam (API, MCP, outro sync) e rode o sync de novo."
            ) from exc

    def _abrir_escrita(self) -> sqlite3.Connection:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        for tentativa in (1, 2):
            try:
                con = self._conectar()
            except sqlite3.DatabaseError as exc:
                if tentativa == 1 and "not a database" in str(exc):
                    self._por_de_lado()
                    continue
                raise
            try:
                con.executescript(ddl())
            except sqlite3.OperationalError as exc:
                con.close()
                if not eh_corrupcao(exc) and any(m in str(exc).lower() for m in _MARCAS_SEM_FTS5):
                    raise IndiceIndisponivel(
                        f"SQLite {sqlite3.sqlite_version} sem FTS5 com contentless_delete: {exc}"
                    ) from exc
                raise
            except sqlite3.DatabaseError as exc:
                con.close()
                if tentativa == 1 and "not a database" in str(exc):
                    self._por_de_lado()
                    continue
                raise
            return con
        raise RuntimeError("inalcançável")  # pragma: no cover

    def _ler(self, consulta, padrao):
        """Executa `consulta(con)` em leitura; índice ausente ou ilegível devolve `padrao`."""
        if not self.caminho.exists():
            return padrao
        try:
            with closing(self._conectar()) as con:
                return consulta(con)
        except sqlite3.DatabaseError as exc:
            if any(m in str(exc).lower() for m in _MARCAS_CORRUPCAO):
                return padrao
            raise

    # ---- escrita ----------------------------------------------------------------------
    @staticmethod
    def _garantir_meta(con: sqlite3.Connection) -> None:
        if con.execute("select 1 from meta where chave = 'esquema'").fetchone() is None:
            con.execute("insert into meta values ('esquema', ?)", (esquema_indice(),))
            con.execute("insert or replace into meta values ('construido_em', ?)", (_agora(),))

    @staticmethod
    def _apagar_arquivo(con: sqlite3.Connection, rel_path: str) -> None:
        ids = [r[0] for r in con.execute("select id from trechos where file_path = ?", (rel_path,))]
        for i in ids:
            con.execute("delete from trechos_fts where rowid = ?", (i,))
        con.execute("delete from trechos where file_path = ?", (rel_path,))
        con.execute("delete from arquivos where file_path = ?", (rel_path,))

    @staticmethod
    def _inserir_arquivo(con: sqlite3.Connection, rel_path: str, sha256: str, chunks: list[dict]) -> int:
        con.execute("insert into arquivos values (?, ?)", (rel_path, sha256))
        marcas = ", ".join("?" for _ in _COLUNAS_TRECHO)
        for chunk in chunks:
            linha = _linha_trecho(chunk)
            cur = con.execute(
                f"insert into trechos ({', '.join(_COLUNAS_TRECHO)}) values ({marcas})", linha
            )
            valores = dict(zip(_COLUNAS_TRECHO, linha))
            con.execute(
                "insert into trechos_fts (rowid, titulo, secao, caminho, corpo) values (?, ?, ?, ?, ?)",
                (
                    cur.lastrowid,
                    valores["doc_title"] or "",
                    valores["section"] or "",
                    re.sub(r"[/\-_.]", " ", valores["file_path"] or ""),
                    _corpo(valores["content"]),
                ),
            )
        return len(chunks)

    def substituir_arquivo(self, rel_path: str, sha256: str, chunks: list[dict]) -> None:
        with closing(self._abrir_escrita()) as con:
            con.execute("begin immediate")
            try:
                self._garantir_meta(con)
                self._apagar_arquivo(con, rel_path)
                self._inserir_arquivo(con, rel_path, sha256, chunks)
                con.execute("commit")
            except BaseException:
                _desfazer(con)
                raise

    def remover_arquivo(self, rel_path: str) -> None:
        with closing(self._abrir_escrita()) as con:
            con.execute("begin immediate")
            try:
                self._garantir_meta(con)
                self._apagar_arquivo(con, rel_path)
                con.execute("commit")
            except BaseException:
                _desfazer(con)
                raise

    def reconstruir(self, itens: Iterable[tuple[str, str, list[dict]]]) -> dict:
        """Troca o índice inteiro numa transação.

        Arquivo corrompido: põe o arquivo de lado e tenta uma segunda vez do zero, com os mesmos
        itens; na segunda falha, o erro propaga.
        """
        percorrer = _repetivel(itens)
        for tentativa in (1, 2):
            try:
                return self._reconstruir_uma_vez(percorrer())
            except sqlite3.DatabaseError as exc:
                if tentativa == 2 or not eh_corrupcao(exc):
                    raise
                self._por_de_lado()
        raise RuntimeError("inalcançável")  # pragma: no cover

    def _reconstruir_uma_vez(self, itens: Iterable[tuple[str, str, list[dict]]]) -> dict:
        arquivos = trechos = 0
        with closing(self._abrir_escrita()) as con:
            con.execute("begin immediate")
            try:
                # Recria as tabelas na mesma transação: tokenizador, colunas e DDL novos
                # valem já nesta reconstrução, e o leitor vê o índice anterior até o commit.
                for instrucao in (*_DROPS, *_instrucoes_ddl()):
                    con.execute(instrucao)
                con.execute("insert into meta values ('esquema', ?)", (esquema_indice(),))
                con.execute("insert into meta values ('construido_em', ?)", (_agora(),))
                for rel_path, sha256, chunks in itens:
                    trechos += self._inserir_arquivo(con, rel_path, sha256, chunks)
                    arquivos += 1
                con.execute("commit")
            except BaseException:
                _desfazer(con)
                raise
        return {"files": arquivos, "chunks": trechos}

    # ---- leitura ----------------------------------------------------------------------
    def verificar(self) -> bool:
        """Prova de integridade do arquivo (`pragma quick_check`), sem escrever nele.

        Arquivo ausente -> `True` (nada a verificar). Corrupção (resultado diferente de "ok" ou
        erro que `eh_corrupcao` reconhece) -> `False`. Outro erro (por exemplo lock) propaga.
        As leituras comuns tratam corrupção como índice vazio; esta prova é o que a distingue.
        """
        if not self.caminho.exists():
            return True
        try:
            with closing(self._conectar_leitura()) as con:
                return con.execute("pragma quick_check").fetchall() == [("ok",)]
        except sqlite3.DatabaseError as exc:
            if eh_corrupcao(exc):
                return False
            raise

    def manifesto(self) -> dict[str, str]:
        return self._ler(lambda c: dict(c.execute("select file_path, sha256 from arquivos")), {})

    def _meta(self, chave: str) -> str | None:
        def consulta(con):
            linha = con.execute("select valor from meta where chave = ?", (chave,)).fetchone()
            return linha[0] if linha else None

        return self._ler(consulta, None)

    def esquema_atual(self) -> str | None:
        return self._meta("esquema")

    def total_trechos(self, space_id: str | None = None) -> int:
        def consulta(con):
            if space_id is None:
                return con.execute("select count(*) from trechos").fetchone()[0]
            return con.execute("select count(*) from trechos where space_id = ?", (space_id,)).fetchone()[0]

        return self._ler(consulta, 0)

    def estatisticas(self) -> dict:
        def consulta(con):
            por_categoria = {
                (cat or ""): n
                for cat, n in con.execute(
                    "select category, count(*) from trechos group by category order by count(*) desc, category"
                )
            }
            return {
                "points_count": con.execute("select count(*) from trechos").fetchone()[0],
                "arquivos": con.execute("select count(*) from arquivos").fetchone()[0],
                "esquema": (con.execute("select valor from meta where chave='esquema'").fetchone() or [None])[0],
                "construido_em": (
                    con.execute("select valor from meta where chave='construido_em'").fetchone() or [None]
                )[0],
                "por_categoria": por_categoria,
            }

        vazio = {"points_count": 0, "arquivos": 0, "esquema": None, "construido_em": None, "por_categoria": {}}
        return self._ler(consulta, vazio)

    def versao(self) -> str:
        esquema, quando = self._meta("esquema"), self._meta("construido_em")
        if esquema is None:
            return "vazio"
        return f"{esquema}@{quando}"

    # ---- busca ------------------------------------------------------------------------
    def buscar(
        self,
        pergunta: str,
        limit: int = 4,
        category: str | None = None,
        bounded_context: str | None = None,
        space_id: str | None = None,
        per_doc: int | None = None,
    ) -> list[dict]:
        expressao = expressao_match(pergunta)
        if expressao is None:
            return []
        filtros, parametros = [], [*PESOS, expressao]
        for coluna, valor in (("space_id", space_id), ("category", category), ("bounded_context", bounded_context)):
            if valor is not None:
                filtros.append(f"and t.{coluna} = ?")
                parametros.append(valor)
        parametros.append(CANDIDATOS)
        colunas = ", ".join(f"t.{c}" for c in (*_CAMPOS_PAYLOAD, *_OPCIONAIS))
        sql = (
            f"select -bm25(trechos_fts, ?, ?, ?, ?) as score, {colunas} "
            "from trechos_fts join trechos t on t.id = trechos_fts.rowid "
            f"where trechos_fts match ? {' '.join(filtros)} order by score desc limit ?"
        )
        linhas = self._ler(lambda con: con.execute(sql, parametros).fetchall(), [])
        nomes = (*_CAMPOS_PAYLOAD, *_OPCIONAIS)
        resultado, por_nota = [], {}
        for linha in linhas:
            payload = {
                n: v for n, v in zip(nomes, linha[1:]) if v is not None or n not in _OPCIONAIS
            }
            if per_doc is None:
                if len(resultado) >= limit:
                    break
            else:
                caminho = payload["file_path"]
                if caminho not in por_nota and len(por_nota) >= limit:
                    continue
                if por_nota.get(caminho, 0) >= per_doc:
                    continue
                por_nota[caminho] = por_nota.get(caminho, 0) + 1
            resultado.append({"score": float(linha[0]), "payload": payload})
        return resultado

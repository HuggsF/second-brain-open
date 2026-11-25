"""Plano de geração: o que gerar por trilha e fase (função pura sobre a demanda)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.triagem import PROXIMA_FASE, erros_triagem, exigidos_da_fase

_COM_PAGINA = {
    "visao": "visao", "cronograma": "cronograma", "historias": "historias",
    "casos_de_uso": "casos-de-uso", "rnf": "rnf", "telas": "telas",
}

_PRODUTO_VALIDO = re.compile(r"^[a-z0-9-]+$")

_SEMPRE_RECALCULADOS = frozenset({"rastreio"})


@dataclass(frozen=True)
class ItemDeGeracao:
    artefato: str
    template: str | None
    caminho: str | None
    usa_ia: bool


def _item(artefato: str, produto: str, demanda_id: str) -> ItemDeGeracao | None:
    if artefato in _COM_PAGINA:
        nome = _COM_PAGINA[artefato]
        return ItemDeGeracao(artefato, f"{nome}@1",
                             f"{produto}/demandas/{demanda_id.lower()}/{nome}.mdx", True)
    if artefato == "regras":
        return ItemDeGeracao("regras", "regras@1", None, True)
    if artefato in ("plano_de_testes", "rastreio"):
        return ItemDeGeracao(artefato, None, None, False)
    return None  # triagem, teste_reproducao, evidence, aceite_area: não são gerados


def plano(demanda) -> list[ItemDeGeracao]:
    artefatos = demanda.artefacts or {}
    triagem = artefatos.get("triagem")
    if triagem is None:
        return [ItemDeGeracao("triagem", "triagem@1", None, True)]
    if not isinstance(triagem, dict) or erros_triagem(triagem):
        return []
    fase = getattr(demanda.phase, "value", demanda.phase)
    if fase not in PROXIMA_FASE:
        return []
    exigidos = exigidos_da_fase(triagem, fase)
    produto = triagem.get("produto")
    pendentes = [n for n in exigidos if n not in artefatos]
    if any(n in _COM_PAGINA for n in pendentes) and not (
            isinstance(produto, str) and _PRODUTO_VALIDO.fullmatch(produto)):
        raise ValueError(f"triagem sem produto válido: {produto!r}")
    itens = []
    for nome in exigidos:
        # rastreio is deterministic and not a page: recalculated on every run.
        if nome in artefatos and nome not in _SEMPRE_RECALCULADOS:
            continue
        item = _item(nome, produto, demanda.id)
        if item is not None:
            itens.append(item)
    return itens

"""Catálogo de produtos do perfil e guia de triagem.

Um produto é o slug que a triagem de uma demanda escolhe. Neste repositório o slug é o de uma ficha
(`fichas/<slug>/`), que é onde os rascunhos da demanda são gravados.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

SLUG_PRODUTO_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ProdutosInvalidos(ValueError):
    """O `produtos.yaml` não pôde ser lido como catálogo."""


@dataclass(frozen=True)
class Produto:
    """`descricao` e `pistas` orientam quem faz a triagem (pessoa ou modelo); `testes_rastreio` é o
    padrão de arquivos que um verificador de rastreio leria, quando houver um."""
    slug: str
    descricao: str
    pistas: tuple[str, ...] = ()
    testes_rastreio: Optional[str] = None


def _texto(valor, onde: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ProdutosInvalidos(f"produtos.yaml {onde}: esperado um texto não vazio")
    return valor.strip()


def _produto(slug, cfg) -> Produto:
    if not isinstance(slug, str) or not SLUG_PRODUTO_RE.match(slug):
        raise ProdutosInvalidos(f"produtos.yaml {slug!r}: slug só com letras minúsculas, números e hífen")
    if not isinstance(cfg, dict):
        raise ProdutosInvalidos(f"produtos.yaml {slug}: esperado um mapeamento")
    pistas = cfg.get("pistas") or ()
    if not isinstance(pistas, (list, tuple)) or not all(isinstance(p, str) for p in pistas):
        raise ProdutosInvalidos(f"produtos.yaml {slug}.pistas: esperada uma lista de textos")
    testes = cfg.get("testes_rastreio")
    # `repositorio` (onde um agente trabalharia) é aceito e ignorado aqui.
    return Produto(slug, _texto(cfg.get("descricao"), f"{slug}.descricao"), tuple(pistas),
                   _texto(testes, f"{slug}.testes_rastreio") if testes is not None else None)


def ler_produtos(caminho: Path) -> dict[str, Produto]:
    """Catálogo de um `produtos.yaml` (mapa de slug para produto); arquivo ausente é catálogo vazio."""
    caminho = Path(caminho)
    if not caminho.is_file():
        return {}
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ProdutosInvalidos(f"produtos.yaml ilegível: {exc}") from exc
    if dados is None:
        return {}
    if not isinstance(dados, dict):
        raise ProdutosInvalidos("produtos.yaml: esperado um mapeamento de slug para produto")
    return {slug: _produto(slug, cfg) for slug, cfg in dados.items()}


def ler_guia_triagem(caminho: Path) -> str:
    """Texto que orienta o rascunho da triagem; arquivo ausente é texto vazio."""
    caminho = Path(caminho)
    return caminho.read_text(encoding="utf-8").strip() if caminho.is_file() else ""

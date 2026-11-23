"""Transforma a pergunta do usuário numa expressão de busca do SQLite FTS5."""
from __future__ import annotations

import re

PALAVRAS_VAZIAS: frozenset[str] = frozenset(
    "a o e de da do das dos em no na nos nas um uma para por com que como "
    "qual quais se ao aos os as ou é ser foi são mais entre sobre quando onde quem".split()
)

_PADRAO_TOKEN = re.compile(r"[0-9a-zà-ÿ_]+")


def termos(pergunta: str) -> list[str]:
    """Termos da pergunta: minúsculos, 3+ caracteres, sem palavras vazias, sem repetição."""
    vistos: list[str] = []
    for token in _PADRAO_TOKEN.findall(pergunta.lower()):
        if len(token) >= 3 and token not in PALAVRAS_VAZIAS and token not in vistos:
            vistos.append(token)
    return vistos


def expressao_match(pergunta: str) -> str | None:
    """Expressão MATCH do FTS5 (termos entre aspas unidos por OR) ou None sem termos."""
    partes = []
    for termo in termos(pergunta):
        if len(termo) >= 6 and not any(c.isdigit() for c in termo):
            partes.append(f'"{termo[:-2]}"*')
        else:
            partes.append(f'"{termo}"')
    return " OR ".join(partes) if partes else None

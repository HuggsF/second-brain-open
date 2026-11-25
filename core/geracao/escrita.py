"""Escrita de rascunhos no repositório de documentação: nunca sobrescreve."""
from __future__ import annotations

from pathlib import Path

from core.docs_registry import pagina_path


def escrever(root: Path, rel: str, conteudo: str) -> str:
    destino = pagina_path(root, rel)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(destino, "x", encoding="utf-8", newline="\n") as f:
            f.write(conteudo)
    except FileExistsError:
        return "pulado"
    return "gerado"

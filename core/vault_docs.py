"""Resolvedor unico de documentos do vault.

Toda leitura de arquivo do vault por nome, numero ou caminho relativo passa por aqui.
As funcoes validam a entrada e devolvem caminhos dentro do diretorio de origem; nenhuma
le conteudo (a leitura fica com o chamador).
"""
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

__all__ = ["DocError", "resolve_named", "resolve_numbered", "resolve_relative"]

_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_IDENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}")


class DocError(ValueError):
    """Nome, identificador ou caminho invalido; a mensagem e segura para o usuario."""


def _contained(path: Path, base: Path) -> bool:
    return path.resolve().is_relative_to(base.resolve())


def resolve_named(directory: Path, name: str, suffix: str = ".md") -> Path | None:
    """Arquivo `<name><suffix>` direto em `directory`, ou None se nao existir."""
    if not isinstance(name, str):
        raise DocError("nome invalido")
    clean = name.strip().lower()
    if not _NAME_RE.fullmatch(clean):
        raise DocError("nome invalido")
    candidate = directory / f"{clean}{suffix}"
    if not _contained(candidate, directory) or not candidate.is_file():
        return None
    return candidate


def resolve_numbered(directory: Path, identifier: str, prefix: str) -> list[Path]:
    """Documentos numerados (`<prefix>-NNN-*.md`) que casam com `identifier`.

    Identificador numerico (`ADR-003`, `adr003`, `003`, `3`) devolve o arquivo daquele numero
    ou lista vazia. Qualquer outro devolve os arquivos cujo nome contem o texto, em ordem.
    """
    if not isinstance(identifier, str):
        raise DocError("identificador invalido")
    clean = identifier.strip()
    if not _IDENT_RE.fullmatch(clean):
        raise DocError("identificador invalido")
    number = re.fullmatch(rf"(?:{re.escape(prefix)}-?)?0*(\d{{1,4}})", clean, re.IGNORECASE)
    if number:
        found = directory.glob(f"{prefix}-{int(number.group(1)):03d}-*.md")
    else:
        needle = clean.lower()
        found = (p for p in directory.glob("*.md") if needle in p.name.lower())
    return sorted(p for p in found if p.is_file() and _contained(p, directory))


def resolve_relative(root: Path, rel_path: str) -> Path | None:
    """Arquivo em `root` por caminho relativo (aceita `\\` ou `/`), ou None se nao existir."""
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise DocError("caminho invalido")
    raw = rel_path.strip()
    normalized = raw.replace("\\", "/")
    if (
        PurePosixPath(normalized).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or PureWindowsPath(normalized).is_absolute()
        or PureWindowsPath(normalized).drive
        or ".." in normalized.split("/")
    ):
        raise DocError("caminho invalido")
    candidate = root.joinpath(*[part for part in normalized.split("/") if part])
    if not _contained(candidate, root) or not candidate.is_file():
        return None
    return candidate

"""Vocabulario do vault e termos da pergunta que o vault nao conhece.

Termo = sequencia `[a-z0-9_&]+` depois de remover acentos e dobrar maiusculas.
"""
import re
import unicodedata

__all__ = ["normalize_terms"]

_TERM = re.compile(r"[a-z0-9_&]+")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_terms(text: str) -> tuple[str, ...]:
    """Termos do texto, sem acento e em minusculas, na ordem em que aparecem."""
    return tuple(_TERM.findall(_strip_accents(text).casefold()))

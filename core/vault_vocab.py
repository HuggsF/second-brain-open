"""Vocabulario do vault e termos da pergunta que o vault nao conhece.

Termo = sequencia `[a-z0-9_&]+` depois de remover acentos e dobrar maiusculas. O vocabulario fica em
cache por raiz e e refeito quando muda o conjunto (caminho, tamanho, mtime_ns) dos `.md`.
"""
import re
import unicodedata
from pathlib import Path

__all__ = ["normalize_terms", "unknown_entities", "vault_vocabulary"]

_TERM = re.compile(r"[a-z0-9_&]+")
_TOKEN = re.compile(r"[A-Za-z0-9_&]+")
_SENTENCE_END = frozenset(".?!:")
_MIN_LENGTH = 3

_cache: dict[Path, tuple[frozenset, frozenset[str]]] = {}


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_terms(text: str) -> tuple[str, ...]:
    """Termos do texto, sem acento e em minusculas, na ordem em que aparecem."""
    return tuple(_TERM.findall(_strip_accents(text).casefold()))


def _signature(root: Path, files: list[Path]) -> frozenset:
    entries = set()
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.add((path.relative_to(root).as_posix(), stat.st_size, stat.st_mtime_ns))
    return frozenset(entries)


def vault_vocabulary(vault_dir: Path) -> frozenset[str]:
    """Todos os termos dos `.md` do vault; arquivo ilegivel nao contribui. Vault ausente: vazio."""
    root = Path(vault_dir).resolve()
    if not root.is_dir():
        return frozenset()
    files = sorted(root.rglob("*.md"))
    signature = _signature(root, files)
    cached = _cache.get(root)
    if cached is not None and cached[0] == signature:
        return cached[1]
    terms: set[str] = set()
    for path in files:
        try:
            terms.update(normalize_terms(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    vocabulary = frozenset(terms)
    _cache[root] = (signature, vocabulary)
    return vocabulary


def unknown_entities(question: str, vocabulary: frozenset[str]) -> list[str]:
    """Nomes proprios da pergunta ausentes do vocabulario, na ordem e sem repeticao.

    Conta o token com 2+ maiusculas em qualquer posicao, ou com maiuscula inicial fora do inicio de
    frase (inicio do texto ou depois de `.`, `?`, `!`, `:`). Vocabulario vazio desliga a verificacao.
    """
    if not vocabulary:
        return []
    text = _strip_accents(question)
    found: list[str] = []
    seen: set[str] = set()
    previous_end = None
    for match in _TOKEN.finditer(text):
        token = match.group()
        initial = previous_end is None or any(ch in _SENTENCE_END for ch in text[previous_end:match.start()])
        previous_end = match.end()
        uppercase = sum(1 for ch in token if ch.isupper())
        proper = uppercase >= 2 or (token[0].isupper() and not initial)
        folded = token.casefold()
        if not proper or len(token) < _MIN_LENGTH or folded in vocabulary or folded in seen:
            continue
        seen.add(folded)
        found.append(token)
    return found

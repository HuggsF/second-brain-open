"""Contrato de citacao da recuperacao vetorial.

Funcoes puras: selecionam trechos (piso de relevancia e diversidade por documento), montam
citacoes verificaveis (documento, linhas, hash, versao desatualizada) e produzem os avisos de
lacuna. O vault so e lido para calcular o hash atual de cada documento citado.
"""
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from core.vault_docs import DocError, resolve_relative

__all__ = ["Citation", "build_citations", "gaps_for", "select_hits"]

GAP_EMPTY_INDEX = "Índice vazio ou indisponível para este espaço."
GAP_NO_EVIDENCE = "Nenhum trecho atinge a relevância mínima; não há evidência no vault para esta consulta."
GAP_STALE = "Há citações de versão anterior do documento; rode o sync."
GAP_UNKNOWN_ENTITY = "Termo(s) sem registro no vault: {terms}; não há evidência para esta consulta."


@dataclass(frozen=True)
class Citation:
    document: str
    section: str
    line_start: int | None
    line_end: int | None
    sha256: str | None
    score: float
    stale: bool


def select_hits(hits: list[dict], *, min_score: float, max_drop: float, max_per_doc: int, limit: int,
                unknown: Sequence[str] = ()) -> list[dict]:
    """Aplica piso de relevancia, diversidade por documento e corte; `hits` ja vem por score decrescente.

    `unknown` (termos da pergunta ausentes do vault) nao vazio: nenhum trecho e selecionado.
    """
    if unknown or not hits or limit <= 0:
        return []
    top = hits[0]["score"]
    if top < min_score:
        return []
    floor = max(min_score, top - max_drop)
    per_doc: dict[str, int] = {}
    selected: list[dict] = []
    for hit in hits:
        if hit["score"] < floor:
            continue
        doc = hit["payload"].get("file_path")
        if per_doc.get(doc, 0) >= max_per_doc:
            continue
        per_doc[doc] = per_doc.get(doc, 0) + 1
        selected.append(hit)
        if len(selected) >= limit:
            break
    return selected


def _current_sha256(vault_dir: Path, document: str) -> str | None:
    """SHA-256 dos bytes do arquivo atual; None se o caminho for recusado, ausente ou ilegivel."""
    try:
        path = resolve_relative(vault_dir, document)
    except DocError:
        return None
    if path is None:
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def build_citations(hits: list[dict], vault_dir: Path) -> list[Citation]:
    """Uma citacao por hit, na ordem de entrada; `stale` quando o arquivo mudou, sumiu ou nao tem hash gravado."""
    current: dict[str, str | None] = {}
    citations: list[Citation] = []
    for hit in hits:
        payload = hit["payload"]
        document = payload.get("file_path")
        if document not in current:
            current[document] = _current_sha256(vault_dir, document)
        indexed = payload.get("doc_sha256")
        now = current[document]
        citations.append(
            Citation(
                document=document,
                section=payload.get("section") or "",
                line_start=payload.get("line_start"),
                line_end=payload.get("line_end"),
                sha256=indexed,
                score=hit["score"],
                stale=indexed is None or now is None or now != indexed,
            )
        )
    return citations


def gaps_for(citations: list[Citation], top_score: float | None, min_score: float, *, space_has_points: bool = False,
             unknown: Sequence[str] = ()) -> list[str]:
    """Avisos de lacuna: termo sem registro no vault, indice vazio, sem evidencia acima do piso, ou
    citacoes de versao anterior. O termo sem registro tem precedencia sobre os demais.

    `space_has_points` distingue indice realmente vazio (o espaco nao tem nenhum ponto) de busca
    filtrada sem resultado (o espaco tem pontos mas o filtro extra descartou tudo).
    """
    if unknown:
        return [GAP_UNKNOWN_ENTITY.format(terms=", ".join(unknown))]
    if not citations:
        if top_score is None:
            return [GAP_NO_EVIDENCE] if space_has_points else [GAP_EMPTY_INDEX]
        return [GAP_NO_EVIDENCE] if top_score < min_score else []
    return [GAP_STALE] if any(c.stale for c in citations) else []

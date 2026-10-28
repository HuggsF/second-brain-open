"""Avaliacao real da recuperacao vetorial: recall nos positivos e negativos sem fonte, por piso.

`collect` consulta o indice uma vez por pergunta (hits brutos, sem piso); `grid` reaplica
`core.citations.select_hits` offline para cada par (min_score, max_drop); `suggest` escolhe o par.
"""
from pathlib import Path

import yaml

from config import settings
from core.citations import select_hits

__all__ = ["DEFAULT_DROPS", "DEFAULT_MINS", "collect", "grid", "load_cases", "suggest"]

DEFAULT_MINS = [0.55, 0.60, 0.65, 0.70, 0.75]
DEFAULT_DROPS = [0.05, 0.10, 0.15, 0.20]


def load_cases(path: Path) -> tuple[list[dict], list[str]]:
    """Positivos (casos com `prompt` e `expected_sources`) e negativos (lista `negatives`) do dataset."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    positives = [
        case for case in data.get("cases") or []
        if case.get("prompt") and case.get("expected_sources")
    ]
    negatives = [str(prompt) for prompt in data.get("negatives") or [] if prompt]
    return positives, negatives


def _raw_hits(retriever, prompt: str, k: int) -> list[dict]:
    result = retriever.query(prompt, limit=k * 3, apply_floor=False)
    return [{"file_path": source["file_path"], "score": source["score"]} for source in result["sources"]]


def collect(retriever, positives: list[dict], negatives: list[str], k: int = 5) -> dict:
    """Hits brutos (por score decrescente) de cada pergunta; `k * 3` deixa a diversidade ainda preencher `k`."""
    return {
        "positives": [
            {"prompt": case["prompt"], "expected": list(case["expected_sources"]),
             "hits": _raw_hits(retriever, case["prompt"], k)}
            for case in positives
        ],
        "negatives": [{"prompt": prompt, "hits": _raw_hits(retriever, prompt, k)} for prompt in negatives],
    }


def _select(hits: list[dict], *, min_score: float, max_drop: float, k: int) -> list[str]:
    wrapped = [{"score": hit["score"], "payload": {"file_path": hit["file_path"]}} for hit in hits]
    selected = select_hits(
        wrapped, min_score=min_score, max_drop=max_drop,
        max_per_doc=settings.retrieval_max_per_doc, limit=k,
    )
    return [hit["payload"]["file_path"] for hit in selected]


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def grid(collected: dict, mins: list[float], drops: list[float], k: int = 5) -> list[dict]:
    """Por par (min_score, max_drop): recall@k dos positivos e fracao de negativos sem nenhuma fonte."""
    positives, negatives = collected["positives"], collected["negatives"]
    rows = []
    for min_score in mins:
        for max_drop in drops:
            recalls = []
            for case in positives:
                found = {_norm(f) for f in _select(case["hits"], min_score=min_score, max_drop=max_drop, k=k)}
                expected = [_norm(e) for e in case["expected"]]
                recalls.append(sum(1 for e in expected if e in found) / len(expected))
            cleared = [not _select(case["hits"], min_score=min_score, max_drop=max_drop, k=k) for case in negatives]
            rows.append({
                "min_score": min_score,
                "max_drop": max_drop,
                "recall_at_k": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
                "negatives_cleared": sum(cleared) / len(cleared) if cleared else 1.0,
            })
    return rows


def suggest(rows: list[dict]) -> dict | None:
    """Par que limpa todos os negativos com maior recall (empate: menor min_score, depois menor max_drop)."""
    candidates = [row for row in rows if row["negatives_cleared"] == 1.0]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (-row["recall_at_k"], row["min_score"], row["max_drop"]))

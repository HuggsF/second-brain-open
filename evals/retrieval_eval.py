"""Avaliacao real da recuperacao vetorial: recall nos positivos e negativos sem fonte, por piso.

`collect` consulta o indice uma vez por pergunta (hits brutos, sem piso) e anota os termos que o vault
nao conhece; `grid` reaplica `core.citations.select_hits` offline para cada par (min_score, max_drop),
com ou sem o gate de entidade; `suggest` escolhe o par.
"""
from pathlib import Path

import yaml

from config import settings
from core.citations import select_hits
from core.vault_vocab import unknown_entities, vault_vocabulary

__all__ = ["DEFAULT_DROPS", "DEFAULT_MINS", "collect", "grid", "known_limits_metric", "load_cases",
           "load_known_limits", "suggest"]

DEFAULT_MINS = [0.55, 0.60, 0.65, 0.70, 0.75]
DEFAULT_DROPS = [0.05, 0.10, 0.15, 0.20]


def _read(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _prompts(items) -> list[str]:
    """Perguntas de uma lista de negativos: string antiga ou registro com `prompt`."""
    prompts = []
    for item in items or []:
        prompt = item.get("prompt") if isinstance(item, dict) else item
        if prompt:
            prompts.append(str(prompt))
    return prompts


def load_cases(path: Path) -> tuple[list[dict], list[str]]:
    """Positivos (casos com `prompt` e `expected_sources`) e negativos (lista `negatives`) do dataset."""
    data = _read(path)
    positives = [
        case for case in data.get("cases") or []
        if case.get("prompt") and case.get("expected_sources")
    ]
    return positives, _prompts(data.get("negatives"))


def load_known_limits(path: Path) -> list[str]:
    """Perguntas de `known_limit_negatives`: medidas a parte, fora da escolha do piso."""
    return _prompts(_read(path).get("known_limit_negatives"))


def _raw_hits(retriever, prompt: str, k: int) -> list[dict]:
    result = retriever.query(prompt, limit=k * 3, apply_floor=False)
    return [{"file_path": source["file_path"], "score": source["score"]} for source in result["sources"]]


def collect(retriever, positives: list[dict], negatives: list[str], k: int = 5,
            known_limits: list[str] | None = None, vocabulary: frozenset[str] | None = None) -> dict:
    """Hits brutos (por score decrescente) e termos desconhecidos de cada pergunta.

    `k * 3` deixa a diversidade ainda preencher `k`. Sem `vocabulary`, usa o vault do proprio retriever.
    """
    if vocabulary is None:
        vocabulary = vault_vocabulary(retriever.vault_dir)

    def case(prompt: str) -> dict:
        return {"prompt": prompt, "hits": _raw_hits(retriever, prompt, k),
                "unknown": unknown_entities(prompt, vocabulary)}

    return {
        "positives": [
            {**case(item["prompt"]), "expected": list(item["expected_sources"])}
            for item in positives
        ],
        "negatives": [case(prompt) for prompt in negatives],
        "known_limits": [case(prompt) for prompt in known_limits or []],
    }


def _select(hits: list[dict], *, min_score: float, max_drop: float, k: int,
            unknown: list[str] = ()) -> list[str]:
    wrapped = [{"score": hit["score"], "payload": {"file_path": hit["file_path"]}} for hit in hits]
    selected = select_hits(
        wrapped, min_score=min_score, max_drop=max_drop,
        max_per_doc=settings.retrieval_max_per_doc, limit=k, unknown=unknown,
    )
    return [hit["payload"]["file_path"] for hit in selected]


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def grid(collected: dict, mins: list[float], drops: list[float], k: int = 5, gate: bool = False) -> list[dict]:
    """Por par (min_score, max_drop): recall@k dos positivos e fracao de negativos sem nenhuma fonte.

    Com `gate`, pergunta com termo desconhecido (`unknown`) nao seleciona nenhum trecho.
    """
    positives, negatives = collected["positives"], collected["negatives"]

    def chosen(case: dict, min_score: float, max_drop: float) -> list[str]:
        unknown = (case.get("unknown") or []) if gate else []
        return _select(case["hits"], min_score=min_score, max_drop=max_drop, k=k, unknown=unknown)

    rows = []
    for min_score in mins:
        for max_drop in drops:
            recalls = []
            for case in positives:
                found = {_norm(f) for f in chosen(case, min_score, max_drop)}
                expected = [_norm(e) for e in case["expected"]]
                recalls.append(sum(1 for e in expected if e in found) / len(expected))
            cleared = [not chosen(case, min_score, max_drop) for case in negatives]
            rows.append({
                "min_score": min_score,
                "max_drop": max_drop,
                "recall_at_k": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
                "negatives_cleared": sum(cleared) / len(cleared) if cleared else 1.0,
            })
    return rows


def known_limits_metric(collected: dict, *, min_score: float, max_drop: float, k: int, basis: str) -> dict:
    """Fracao dos negativos de limite conhecido que ficam sem fonte no par dado (com o gate).

    `basis`: `suggested` (par sugerido pela grade) ou `provisional` (piso atual, sem sugestao).
    """
    cases = collected.get("known_limits") or []
    without = sum(
        1 for case in cases
        if not _select(case["hits"], min_score=min_score, max_drop=max_drop, k=k, unknown=case.get("unknown") or [])
    )
    return {"count": len(cases), "without_sources": without,
            "fraction_without_sources": without / len(cases) if cases else 0.0,
            "min_score": min_score, "max_drop": max_drop, "basis": basis}


def suggest(rows: list[dict]) -> dict | None:
    """Par que limpa todos os negativos com maior recall (empate: menor min_score, depois menor max_drop)."""
    candidates = [row for row in rows if row["negatives_cleared"] == 1.0]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (-row["recall_at_k"], row["min_score"], row["max_drop"]))

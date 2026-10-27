"""Métricas de avaliação para o Compound AI System."""
from typing import List, Set, Dict, Any


def compute_source_recall(retrieved_sources: List[str], expected_sources: List[str]) -> Dict[str, float]:
    """Calcula Precision, Recall e F1-Score da recuperação de fontes no Vault."""
    if not expected_sources:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    # Normaliza caminhos (remove extensão e barras invertidas)
    def clean(s: str) -> str:
        return s.replace("\\", "/").rstrip("/").replace(".md", "").lower()

    retrieved_set: Set[str] = {clean(s) for s in retrieved_sources if s}
    expected_set: Set[str] = {clean(s) for s in expected_sources if s}

    true_positives = len(retrieved_set.intersection(expected_set))
    precision = true_positives / len(retrieved_set) if retrieved_set else 0.0
    recall = true_positives / len(expected_set) if expected_set else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "found_count": true_positives,
        "expected_count": len(expected_set),
    }


def compute_composite_score(recall: float, gates_passed: int, gates_total: int) -> float:
    """Calcula o Composite Score final (0 a 100) ponderando RAG e Quality Gates."""
    gate_rate = (gates_passed / gates_total) if gates_total > 0 else 1.0
    # Peso: 40% Recall de fontes do Vault + 60% Aprovação nos Quality Gates
    score = (recall * 0.4 + gate_rate * 0.6) * 100.0
    return round(score, 1)

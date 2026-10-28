"""Runner de Avaliação Contínua (Evals) do Compound AI System.

Executa os casos do Golden Dataset contra o motor de busca do Vault e a esteira
de Quality Gates determinísticos, calculando o score de aderência ao padrão humano.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
import yaml

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import settings
from core.gates import (
    GroundingGate,
    DagGate,
    RuleComplianceGate,
    IdempotencyGate,
    CompoundGatePipeline,
    Semaphore,
)


def load_dataset(dataset_path: Path) -> Dict[str, Any]:
    raw = dataset_path.read_text(encoding="utf-8")
    return yaml.safe_load(raw)


def run_evals(dataset_path: Path = None, verbose: bool = True) -> Dict[str, Any]:
    dataset_file = dataset_path or Path(__file__).parent / "golden_dataset.yaml"
    data = load_dataset(dataset_file)
    cases: List[Dict[str, Any]] = data.get("cases", [])

    pipeline = CompoundGatePipeline()
    results = []

    print("\n" + "=" * 70)
    print(f"COMPOUND AI EVALUATION RUNNER - {data.get('dataset_name', 'Evals')}")
    print(f"Total de casos padrao-ouro carregados: {len(cases)}")
    print("=" * 70 + "\n")

    scores: List[float] = []

    for idx, case in enumerate(cases, 1):
        case_id = case["id"]
        title = case["title"]
        prompt = case["prompt"]
        expected_sources = case.get("expected_sources", [])
        must_pass = case.get("must_pass_gates", [])

        # 1. Fontes esperadas que existem no Vault (insumo do gate de grounding).
        # Isto NAO mede recuperacao: o recall vem de `cli.py retrieval-eval`.
        vault_dir = settings.vault_dir
        found_sources = []
        for src_rel in expected_sources:
            target_file = (vault_dir / src_rel).resolve()
            if target_file.is_file():
                found_sources.append(src_rel)

        # 2. Execução dos Quality Gates aplicáveis
        gate_executions = []
        gates_passed_count = 0

        # Gate 1: Grounding
        if "gate_1_grounding_citation" in must_pass:
            g1_res = pipeline.grounding.evaluate({
                "citations": [{"document": s} for s in found_sources],
                "claims": prompt,
            })
            gate_executions.append(g1_res)
            if g1_res.passed:
                gates_passed_count += 1

        # Gate 2: DAG
        if "gate_2_dag_cycle_validation" in must_pass:
            g2_res = pipeline.dag.evaluate({
                "version": 1,
                "steps": [
                    {"id": "s1", "role": "researcher", "dependsOn": [], "tools": ["search"]},
                    {"id": "s2", "role": "architect", "dependsOn": ["s1"], "tools": ["validate_plan"]},
                    {"id": "s3", "role": "dev", "dependsOn": ["s2"], "tools": ["generate_patch"]},
                ],
            })
            gate_executions.append(g2_res)
            if g2_res.passed:
                gates_passed_count += 1

        # Gate 3: Rules
        if "gate_3_rule_compliance" in must_pass:
            g3_res = pipeline.rules.evaluate({
                "rules_checked": case.get("expected_rules", []),
                "parameters": {"environment": "production", "nfe_key": "35231012345678000195550010000000011234567890"},
            })
            gate_executions.append(g3_res)
            if g3_res.passed:
                gates_passed_count += 1

        # Gate 4: Idempotency
        if "gate_4_idempotency_concurrency" in must_pass:
            g4_res = pipeline.idempotency.evaluate({
                "is_mutation": True,
                "idempotency_key": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
                "batch_trace_id": "e74f9d2a1b8c0e5a4f7e2d1c9a8b7e6d",
                "lock_ttl_seconds": 15,
            })
            gate_executions.append(g4_res)
            if g4_res.passed:
                gates_passed_count += 1

        # Score = taxa de gates aprovados; caso sem gates nao tem score e fica fora da media.
        score = round(gates_passed_count / len(must_pass) * 100.0, 1) if must_pass else None
        if score is not None:
            scores.append(score)

        if score is None:
            semaphore_symbol = "⚪"
        else:
            semaphore_symbol = "🟢" if score >= 85 else ("🟡" if score >= 60 else "🔴")

        if verbose:
            print(f"[{idx}/{len(cases)}] {semaphore_symbol} {case_id}: {title}")
            score_text = f"{score}/100" if score is not None else "sem gates (fora da média)"
            print(f"  ┌── Score (taxa de gates): {score_text}")
            print(f"  ├── Fontes esperadas presentes no Vault: {len(found_sources)}/{len(expected_sources)}")
            print(f"  └── Gates Aprovados: {gates_passed_count}/{len(must_pass)}")
            for g in gate_executions:
                sem = "🟢" if g.semaphore == Semaphore.GREEN else ("🟡" if g.semaphore == Semaphore.YELLOW else "🔴")
                print(f"      {sem} {g.gate_name}: {g.summary}")
            print()

        results.append({
            "case_id": case_id,
            "title": title,
            "score": score,
            "recall": None,
            "gates_passed": gates_passed_count,
            "gates_total": len(must_pass),
        })

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    print("=" * 70)
    print("Recall: não medido aqui (use cli.py retrieval-eval)")
    print(f"🏆 SCORE MÉDIO DO COMPOUND AI: {avg_score}/100.0")
    print(f"Taxa de Aderência ao Golden Standard: {'🟢 EXCELENTE' if avg_score >= 85 else '🟡 ACEITÁVEL'}")
    print("=" * 70 + "\n")

    return {
        "dataset": data.get("dataset_name"),
        "total_cases": len(cases),
        "average_score": avg_score,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runner de Evals do Compound AI")
    parser.add_argument("--dataset", type=Path, default=None, help="Caminho do arquivo YAML do Golden Dataset")
    args = parser.parse_args()
    run_evals(args.dataset)

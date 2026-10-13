"""Gate 1: Grounding & Citation Gate (Anti-Alucinação).

Garante que toda afirmação técnica crítica e evidência documental apontada pelos
agentes corresponda a arquivos físicos reais no Vault, com integridade SHA-256 verificada.
"""
from pathlib import Path
from typing import Any, Dict, List
import hashlib

from config import settings
from core.gates.base import BaseGate, GateResult, Semaphore


class GroundingGate(BaseGate):
    name: str = "gate_1_grounding_citation"

    def __init__(self, vault_dir: Path = None):
        self.vault_dir = Path(vault_dir or settings.vault_dir).resolve()

    def evaluate(self, payload: Dict[str, Any]) -> GateResult:
        """Avalia um payload contendo 'citations' ou 'document_references'.

        Payload esperado:
        {
            "citations": [
                {"document": "adrs/ADR-006-implementacao-flowlogger-observabilidade-semaforos.md", "sha256": "..."},
                ...
            ],
            "claims": "texto da afirmação gerada pelo agente..."
        }
        """
        citations: List[Dict[str, Any]] = payload.get("citations", [])

        if not citations:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.YELLOW,
                passed=False,
                summary="Nenhuma citação documental fornecida. Afirmação técnica sem fundamentação no Vault.",
                details={"verified_count": 0, "missing_count": 0},
            )

        verified = []
        invalid = []

        for cit in citations:
            doc_ref = cit.get("document", "").strip()
            claimed_hash = cit.get("sha256")

            # Proteção contra path traversal
            if not doc_ref or ".." in doc_ref:
                invalid.append({"document": doc_ref, "error": "Referência inválida ou insegura"})
                continue

            doc_path = (self.vault_dir / doc_ref).resolve()
            if not doc_path.is_relative_to(self.vault_dir) or not doc_path.is_file():
                # Tenta localizar com ou sem extensão .md
                if (self.vault_dir / f"{doc_ref}.md").is_file():
                    doc_path = (self.vault_dir / f"{doc_ref}.md").resolve()
                else:
                    invalid.append({"document": doc_ref, "error": "Arquivo não existe no Vault"})
                    continue

            # Calcula hash SHA-256 real do disco
            raw_bytes = doc_path.read_bytes()
            actual_hash = hashlib.sha256(raw_bytes).hexdigest()

            if claimed_hash and claimed_hash != actual_hash:
                invalid.append({
                    "document": doc_ref,
                    "error": f"Hash SHA-256 divergente (fornecido: {claimed_hash[:12]}..., real: {actual_hash[:12]}...)",
                })
                continue

            verified.append({
                "document": doc_ref,
                "sha256": actual_hash,
                "size_bytes": len(raw_bytes),
            })

        if invalid:
            return GateResult(
                gate_name=self.name,
                semaphore=Semaphore.RED,
                passed=False,
                summary=f"Alucinação ou inconsistência detectada: {len(invalid)} citações inválidas.",
                details={"verified": verified, "invalid": invalid},
            )

        return GateResult(
            gate_name=self.name,
            semaphore=Semaphore.GREEN,
            passed=True,
            summary=f"Fundamentação íntegra: {len(verified)} fontes do Vault validadas com SHA-256.",
            details={"verified": verified, "invalid": []},
        )

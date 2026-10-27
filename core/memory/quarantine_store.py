"""Zona de Quarentena de Memória (Memory Quarantine Layer).

Evita o envenenamento de memória (Memory Drift / Data Poisoning).
Qualquer documento, regra ou artefato sintetizado por agentes é gravado aqui
em quarentena e só é promovido ao Vault principal mediante aprovação humana
e validação pelos Quality Gates.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import datetime
import json
import hashlib

from config import settings


@dataclass
class QuarantineItem:
    candidate_id: str
    target_vault_path: str
    author_agent: str
    title: str
    content: str
    sha256: str
    gate_results: Dict[str, Any]
    status: str  # "PENDING_REVIEW" | "PROMOTED" | "REJECTED"
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QuarantineStore:
    def __init__(self, quarantine_dir: Path = None):
        self.quarantine_dir = Path(quarantine_dir or (settings.base_dir / ".runtime" / "quarantine")).resolve()
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def deposit(
        self,
        target_vault_path: str,
        author_agent: str,
        title: str,
        content: str,
        gate_results: Dict[str, Any] = None,
    ) -> QuarantineItem:
        """Deposita uma nova memória na zona de quarentena."""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        candidate_id = f"quarantine_{content_hash[:12]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        item = QuarantineItem(
            candidate_id=candidate_id,
            target_vault_path=target_vault_path,
            author_agent=author_agent,
            title=title,
            content=content,
            sha256=content_hash,
            gate_results=gate_results or {},
            status="PENDING_REVIEW",
            created_at=now,
        )

        item_file = self.quarantine_dir / f"{candidate_id}.json"
        item_file.write_text(json.dumps(item.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return item

    def list_pending(self) -> List[QuarantineItem]:
        """Lista todos os itens em quarentena aguardando aprovação humana."""
        items = []
        for f in sorted(self.quarantine_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") == "PENDING_REVIEW":
                    items.append(QuarantineItem(**data))
            except Exception:
                continue
        return items

    def promote_to_vault(self, candidate_id: str, reviewer: str = "human_full_cycle") -> Path:
        """Promove um item da quarentena para o Vault oficial."""
        item_file = self.quarantine_dir / f"{candidate_id}.json"
        if not item_file.is_file():
            raise FileNotFoundError(f"Item de quarentena '{candidate_id}' não encontrado.")

        data = json.loads(item_file.read_text(encoding="utf-8"))
        target_rel = data["target_vault_path"]
        vault_file = (settings.vault_dir / target_rel).resolve()

        if not vault_file.is_relative_to(settings.vault_dir.resolve()):
            raise ValueError(f"Caminho alvo inseguro: {target_rel}")

        # Grava no Vault com segurança
        vault_file.parent.mkdir(parents=True, exist_ok=True)
        vault_file.write_text(data["content"], encoding="utf-8")

        # Atualiza status na quarentena
        data["status"] = "PROMOTED"
        data["promoted_by"] = reviewer
        data["promoted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        item_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return vault_file

    def purge_quarantine(self) -> int:
        """Purga todos os itens de quarentena (sem tocar no Vault)."""
        count = 0
        for f in self.quarantine_dir.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
        return count

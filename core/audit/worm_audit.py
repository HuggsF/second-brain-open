"""WORM Audit Trail com Hash-Chain Merkle.

Sprint 4 (Gap G8 — Plano de Convergência AI-OS + MoE):
Implementa imutabilidade WORM (Write-Once Read-Many) sobre o audit trail
usando encadeamento de hashes SHA-256 (hash-chain).

Cada registro de auditoria inclui o hash do registro anterior,
formando uma cadeia verificável de integridade. Qualquer alteração
ou remoção de um registro quebra a cadeia e é detectável via
`verify_chain()`.

Componentes:
  - AuditRecord: dataclass com campos obrigatórios + prev_hash + hash
  - WORMAuditLog: append-only log com hash-chain em arquivo JSONL
  - verify_chain(): verifica integridade de toda a cadeia

Integra com:
  - core/events.py (events.jsonl): cada record() pode gerar audit entry
  - core/evidence_store.py (evidence.db): referências cruzadas via trace_id

Thread-safe via threading.Lock para writes (reads são idempotentes).
"""

import hashlib
import os
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Hash do bloco gênesis (nenhum registro anterior)
GENESIS_HASH = "0" * 64


@dataclass
class AuditRecord:
    """Um registro individual na cadeia WORM.

    Attributes:
        sequence: Número sequencial do registro (0-indexed).
        timestamp: ISO 8601 timestamp.
        event_type: Tipo do evento (ex: "gate.dlp_input", "mission.start").
        actor: Quem gerou o evento (persona_id ou "system").
        trace_id: W3C trace_id da operação.
        payload_hash: SHA-256 do payload original (não armazena payload).
        prev_hash: Hash do registro anterior na cadeia.
        record_hash: SHA-256 deste registro (calculado sobre todos os campos).
        metadata: Campos extras opcionais.
    """
    sequence: int
    timestamp: str
    event_type: str
    actor: str
    trace_id: str
    payload_hash: str
    prev_hash: str
    record_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Calcula o SHA-256 deste registro (excluindo record_hash)."""
        canonical = json.dumps({
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "trace_id": self.trace_id,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "metadata": self.metadata,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "trace_id": self.trace_id,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditRecord":
        return cls(
            sequence=data["sequence"],
            timestamp=data["timestamp"],
            event_type=data["event_type"],
            actor=data["actor"],
            trace_id=data["trace_id"],
            payload_hash=data["payload_hash"],
            prev_hash=data["prev_hash"],
            record_hash=data.get("record_hash", ""),
            metadata=data.get("metadata", {}),
        )


def hash_payload(payload: Any) -> str:
    """SHA-256 do payload (serializado como JSON canônico)."""
    if payload is None:
        canonical = ""
    elif isinstance(payload, str):
        canonical = payload
    else:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WORMAuditLog:
    """Append-only audit log com hash-chain SHA-256.

    O log é persistido como JSONL (uma linha JSON por registro).
    Cada novo registro referencia o hash do anterior, formando
    uma cadeia Merkle linear verificável.

    Args:
        path: Caminho do arquivo JSONL do audit log.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._last_hash: str = GENESIS_HASH
        self._sequence: int = 0

        # Reconstrói estado a partir do arquivo existente
        self._rebuild_state()

    def _rebuild_state(self) -> None:
        """Lê o arquivo existente e reconstrói last_hash e sequence."""
        if not self.path.exists():
            return
        try:
            text = self.path.read_text(encoding="utf-8")
            for line in text.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    self._last_hash = record.get("record_hash", GENESIS_HASH)
                    self._sequence = record.get("sequence", 0) + 1
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            pass

    def append(
        self,
        event_type: str,
        actor: str,
        trace_id: str,
        payload: Any = None,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        """Adiciona um registro à cadeia WORM.

        Returns:
            O AuditRecord criado com hash calculado.
        """
        from core.tracing import now_iso

        with self._lock:
            ts = timestamp or now_iso()
            p_hash = hash_payload(payload)

            record = AuditRecord(
                sequence=self._sequence,
                timestamp=ts,
                event_type=event_type,
                actor=actor,
                trace_id=trace_id,
                payload_hash=p_hash,
                prev_hash=self._last_hash,
                metadata=metadata or {},
            )
            record.record_hash = record.compute_hash()

            # Persistir (append-only, WORM)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

            self._last_hash = record.record_hash
            self._sequence += 1

            return record

    @property
    def last_hash(self) -> str:
        """Hash do último registro (ou GENESIS_HASH se vazio)."""
        with self._lock:
            return self._last_hash

    @property
    def length(self) -> int:
        """Número de registros na cadeia."""
        with self._lock:
            return self._sequence

    def read_all(self) -> List[AuditRecord]:
        """Lê todos os registros do log."""
        records = []
        if not self.path.exists():
            return records
        text = self.path.read_text(encoding="utf-8")
        for line in text.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                records.append(AuditRecord.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return records


@dataclass
class VerificationResult:
    """Resultado da verificação de integridade da cadeia."""
    valid: bool
    total_records: int
    verified_records: int
    first_broken_at: Optional[int] = None  # sequence number onde falhou
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "total_records": self.total_records,
            "verified_records": self.verified_records,
            "first_broken_at": self.first_broken_at,
            "error": self.error,
        }


def verify_chain(records: List[AuditRecord]) -> VerificationResult:
    """Verifica a integridade da hash-chain.

    Valida:
    1. Sequência contínua (0, 1, 2, ...)
    2. prev_hash aponta para o record_hash anterior (ou GENESIS_HASH no primeiro)
    3. record_hash é recalculável e bate com o armazenado

    Args:
        records: Lista de AuditRecord em ordem sequencial.

    Returns:
        VerificationResult com o status da verificação.
    """
    if not records:
        return VerificationResult(valid=True, total_records=0, verified_records=0)

    prev_hash = GENESIS_HASH
    for i, record in enumerate(records):
        # 1. Sequência contínua
        if record.sequence != i:
            return VerificationResult(
                valid=False,
                total_records=len(records),
                verified_records=i,
                first_broken_at=i,
                error=f"sequência quebrada: esperado {i}, encontrado {record.sequence}",
            )

        # 2. prev_hash correto
        if record.prev_hash != prev_hash:
            return VerificationResult(
                valid=False,
                total_records=len(records),
                verified_records=i,
                first_broken_at=record.sequence,
                error=f"prev_hash inválido no registro {record.sequence}",
            )

        # 3. record_hash verificável
        computed = record.compute_hash()
        if record.record_hash != computed:
            return VerificationResult(
                valid=False,
                total_records=len(records),
                verified_records=i,
                first_broken_at=record.sequence,
                error=f"record_hash adulterado no registro {record.sequence}",
            )

        prev_hash = record.record_hash

    return VerificationResult(
        valid=True,
        total_records=len(records),
        verified_records=len(records),
    )

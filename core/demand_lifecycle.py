"""
Demand Lifecycle Layer — SQLite persistence + phase state-machine.

Manages the full lifecycle of demands (DEM-XXX) through eight phases:
    INTAKE → SPIKE → SPEC → DEV → REVIEW → DONE
    + BLOCKED  (any active → blocked → origin)
    + CANCELLED (any open → terminal)

Additional features (v2):
    - BLOCKED phase with origin tracking and metadata (waiting_on, next_action, follow_up_at)
    - CANCELLED terminal phase with reason/actor
    - Rework flag on REVIEW → DEV transitions
    - days_in_current_phase computed property

Some transitions are automatic; others require explicit human-in-the-loop
(HITL) approval.  Every phase change emits a structured event dict that can
be forwarded to SSE consumers.

Usage::

    from core.demand_lifecycle import DemandLifecycleService, Phase

    svc = DemandLifecycleService()          # opens / creates .runtime/demands.db
    dem = svc.create_demand("Fix login", "Login button 404s", source="slack", priority="high")
    evt = svc.transition(dem.id, Phase.SPIKE, actor="classifier-agent", reason="auto-classified")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.docs_registry import DocsRegistryError, docs_root, page_status, pagina_path, regras_aprovadas
from core.triagem import (AGUARDANDO, PROXIMA_FASE, Trilha, artefatos_exigidos, erros_rastreio,
                          erros_triagem)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase enum & transition rules
# ---------------------------------------------------------------------------

class Phase(str, Enum):
    """Eight-phase lifecycle of a demand (v2)."""

    INTAKE = "intake"
    SPIKE = "spike"
    SPEC = "spec"
    DEV = "dev"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


# Mapping: source_phase → set of allowed target phases.
# "any → intake" is handled separately (always allowed).
# v2: added BLOCKED (from active phases), CANCELLED (from any open phase),
#     and REVIEW→DEV (rework).
_VALID_TRANSITIONS: Dict[Phase, set[Phase]] = {
    Phase.INTAKE: {Phase.SPIKE, Phase.CANCELLED},
    Phase.SPIKE:  {Phase.SPEC, Phase.BLOCKED, Phase.CANCELLED},
    Phase.SPEC:   {Phase.DEV, Phase.BLOCKED, Phase.CANCELLED},
    Phase.DEV:    {Phase.REVIEW, Phase.BLOCKED, Phase.CANCELLED},
    Phase.REVIEW: {Phase.DONE, Phase.DEV, Phase.BLOCKED, Phase.CANCELLED},
    # BLOCKED can return to any active phase (validated dynamically via origin_phase)
    Phase.BLOCKED: {Phase.SPIKE, Phase.SPEC, Phase.DEV, Phase.REVIEW, Phase.CANCELLED},
    # Terminal phases: no outgoing transitions
    Phase.DONE:      set(),
    Phase.CANCELLED: set(),
}

# Phases from which a demand can be BLOCKED.
_BLOCKABLE_PHASES: set[Phase] = {Phase.SPIKE, Phase.SPEC, Phase.DEV, Phase.REVIEW}

# Transitions that require human-in-the-loop approval.
_HITL_GATES: set[tuple[Phase, Phase]] = {
    (Phase.SPIKE, Phase.SPEC),
    (Phase.SPEC, Phase.DEV),
    (Phase.REVIEW, Phase.DONE),
}


# ---------------------------------------------------------------------------
# Artefact templates & required artefacts per gate
# ---------------------------------------------------------------------------

ARTEFACT_TEMPLATES: Dict[str, dict] = {
    "spike": {
        "objective": "",
        "findings": [],
        "risks": [],
        "recommendation": "",
        "estimated_effort": "",
        "decision": "",       # "proceed" | "pivot" | "cancel"
        "author": "",
        "completed_at": "",
    },
    "user_stories": [
        {
            "id": "US-001",
            "as_a": "",
            "i_want": "",
            "so_that": "",
            "acceptance_criteria": [],
            "priority": "medium",
        }
    ],
    "acceptance_criteria": {
        "functional": [],
        "non_functional": [],
        "edge_cases": [],
    },
    "evidence": {
        "test_results": [],
        "screenshots": [],
        "logs": [],
        "reviewer_notes": "",
        "approved_by": "",
        "approved_at": "",
    },
}

# Gates per track: the artefacts required by a transition come
# from the approved ``triagem`` artefact via ``core.triagem.artefatos_exigidos``.
# Transitions a track may gate; without a valid triagem they ask for it.
_GATED_TRANSITIONS: set[tuple[Phase, Phase]] = {
    (Phase.INTAKE, Phase.SPIKE),
    (Phase.SPIKE, Phase.SPEC),
    (Phase.SPEC, Phase.DEV),
    (Phase.REVIEW, Phase.DONE),
}

# Artefacts that are a page of the documentation repository (relative path or
# {"pagina": rel, ...}); the gate checks that the page exists and is not a
# draft (``status: proposta``).
_PAGE_ARTEFACTS = ("visao", "cronograma", "historias", "telas", "casos_de_uso", "rnf")


def _pagina_rel(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and isinstance(value.get("pagina"), str):
        return value["pagina"].strip()
    return ""


def _regras_rels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [r.strip() for r in value if isinstance(r, str) and r.strip()]


def _gate(origem: Phase, destino: Phase, artefacts: dict,
          produtos: Optional[frozenset] = None) -> tuple[list[str], list[str], str]:
    """Return ``(required, missing, detail)`` for the transition origem -> destino.

    ``produtos`` is the profile's product catalog; ``None`` skips the product check.
    """
    par = (origem, destino)
    if par not in _GATED_TRANSITIONS:
        return [], [], ""
    triagem = artefacts.get("triagem")
    # Every gate needs a valid triagem approved by the manager: the track only
    # counts once approved, and it can be replaced after intake.
    if not isinstance(triagem, dict) or not triagem:
        return ["triagem"], ["triagem"], "triagem ausente"
    erros = erros_triagem(triagem, produtos)
    if erros:
        return ["triagem"], ["triagem"], "; ".join(erros)
    if par == (Phase.INTAKE, Phase.SPIKE):
        return ["triagem"], [], ""
    trilha = Trilha(triagem["trilha"])
    required = artefatos_exigidos(
        trilha, origem.value, destino.value,
        bool(triagem.get("t1")), bool(triagem.get("t2")), bool(triagem.get("t3")),
        bool(triagem.get("mais_de_uma_sprint")),
    )
    produto, erro_produto = None, ""
    if par == (Phase.REVIEW, Phase.DONE) and trilha == Trilha.COMPLETA and triagem.get("t1"):
        # The rules may lose approval during dev: check them again at delivery,
        # and the trace file must be the one of the rules' product.
        required = [*required, "regras"]
        produtos = sorted({rel.split("/")[0] for rel in _regras_rels(artefacts.get("regras"))})
        if len(produtos) == 1:
            produto = produtos[0]
        elif len(produtos) > 1:
            erro_produto = (f"rastreio: regras de produtos diferentes ({', '.join(produtos)}); "
                            "a demanda tem de ficar num produto só")
    missing: list[str] = []
    paginas: list[tuple[str, str]] = []
    erros_conteudo: list[str] = []
    for key in required:
        value = artefacts.get(key)
        if not value:
            missing.append(key)
        elif key == "rastreio":
            erros = erros_rastreio(Path(str(value)), produto=produto)
            if erro_produto:
                erros = [erro_produto, *erros]
            if erros:
                missing.append(key)
                erros_conteudo += erros
        elif key == "regras":
            rels = _regras_rels(value)
            if not rels:
                missing.append(key)
            paginas += [(key, rel) for rel in rels]
        elif key in _PAGE_ARTEFACTS:
            rel = _pagina_rel(value)
            if not rel:
                missing.append(key)
                continue
            if key == "visao" and not (
                isinstance(value, dict) and str(value.get("aprovada_por") or "").strip()
            ):
                missing.append("visao:aprovada_por")
            paginas.append((key, rel))
    detalhe = "; ".join(erros_conteudo)
    if not paginas:
        return required, missing, detalhe
    try:
        root = docs_root()
        regras_existentes: list[str] = []
        for key, rel in paginas:
            if not pagina_path(root, rel).is_file():
                missing.append(f"{key}:{rel}")
            elif key == "regras":
                regras_existentes.append(rel)
            elif page_status(root, rel).get("status") == "proposta":
                # A generated draft opens no gate: a person validates it first
                # (status validada/aprovada); a page without status predates drafts.
                missing.append(f"{key}:{rel}:proposta")
        missing += [f"regras:{rel}" for rel in regras_aprovadas(root, regras_existentes)]
    except DocsRegistryError as exc:
        return required, missing + ["docs_repo"], "; ".join([*erros_conteudo, str(exc)])
    return required, missing, detalhe


def _triagem_sem_troca(demand_id: str, atual: Any, nova: Any) -> Any:
    """Refuse a triagem write that changes the chosen track or its downgrade log.

    The track, once chosen, and the ``rebaixamentos`` log change only through
    ``rebaixar_trilha`` (reason and author recorded). A write without
    ``rebaixamentos`` keeps the stored log.
    """
    atual = atual if isinstance(atual, dict) else {}
    trilha_atual = str(atual.get("trilha") or "")
    trilha_nova = str(nova.get("trilha") or "") if isinstance(nova, dict) else ""
    if trilha_atual and trilha_nova != trilha_atual:
        raise ValueError(
            f"{demand_id}: a trilha {trilha_atual!r} nao pode ser trocada por "
            f"{trilha_nova or 'vazia'!r} na triagem; use rebaixar_trilha "
            "(cli.py demanda trilha) com motivo"
        )
    if not isinstance(nova, dict):
        return nova
    registro = atual.get("rebaixamentos") or []
    if "rebaixamentos" not in nova:
        return {**nova, "rebaixamentos": registro}
    if (nova.get("rebaixamentos") or []) != registro:
        raise ValueError(
            f"{demand_id}: rebaixamentos so mudam por rebaixar_trilha; "
            "envie a triagem sem o campo ou com o registro atual"
        )
    return nova


# ---------------------------------------------------------------------------
# Demand dataclass
# ---------------------------------------------------------------------------

@dataclass
class Demand:
    """Canonical representation of a demand record.

    Attributes:
        id:             Unique identifier (``DEM-001``, ``DEM-042``, …).
        title:          Short human-readable title.
        description:    Longer description / acceptance context.
        source:         Origin channel (``slack``, ``jira``, ``manual``, …).
        priority:       Priority label (``low``, ``medium``, ``high``, ``critical``).
        phase:          Current lifecycle phase.
        classification: Free-form dict produced by the classifier agent.
        artefacts:      Keyed artefacts produced during lifecycle
                        (``spike``, ``user_stories``, ``acceptance_criteria``, ``evidence``).
        agent_history:  Chronological list of agent actions on this demand.
        created_at:     ISO-8601 creation timestamp.
        updated_at:     ISO-8601 last-update timestamp.
    """

    id: str
    title: str
    description: str
    source: str
    priority: str
    phase: Phase
    classification: dict = field(default_factory=dict)
    artefacts: dict = field(default_factory=dict)
    agent_history: list = field(default_factory=list)
    blocked_metadata: Optional[dict] = None
    cancel_metadata: Optional[dict] = None
    rework: bool = False
    rework_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    @property
    def days_in_current_phase(self) -> float:
        """Calculate days since the last phase change (updated_at)."""
        if not self.updated_at:
            return 0.0
        try:
            updated = datetime.fromisoformat(self.updated_at)
            now = datetime.now(timezone.utc)
            delta = now - updated
            return round(delta.total_seconds() / 86400, 1)
        except (ValueError, TypeError):
            return 0.0

    @property
    def phase_age_badge(self) -> str:
        """Return a color badge based on days in current phase.

        Returns:
            One of ``green``, ``yellow``, ``red``.
        """
        days = self.days_in_current_phase
        if days < 2:
            return "green"
        elif days <= 5:
            return "yellow"
        else:
            return "red"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DemandNotFoundError(Exception):
    """Raised when a demand id does not exist in the database."""


class InvalidTransitionError(Exception):
    """Raised when a requested phase transition is not allowed."""


class MissingArtefactError(Exception):
    """Raised when a phase transition requires artefacts that are missing."""

    def __init__(self, demand_id: str, missing: list[str], transition: str, detail: str = ""):
        self.demand_id = demand_id
        self.missing = missing
        self.transition = transition
        self.detail = detail
        super().__init__(
            f"Cannot transition {demand_id} ({transition}): "
            f"missing required artefacts: {', '.join(missing)}"
            + (f" ({detail})" if detail else "")
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DemandLifecycleService:
    """Thread-safe service that persists demands in SQLite and enforces the
    phase state-machine.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to ``.runtime/demands.db`` relative to the
                 project root (two levels up from this file's ``core/`` dir).
    """

    # -- construction / schema ------------------------------------------------

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent
            db_path = project_root / ".runtime" / "demands.db"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._gancho_fase: Optional[Callable[[str, str], None]] = None
        self._produtos: Optional[frozenset] = None
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        """SQLite file of this service (the steps table lives in the same file)."""
        return self._db_path

    # -- phase hook -----------------------------------------------------------

    def set_gancho_fase(self, cb: Optional[Callable[[str, str], None]]) -> None:
        """Register ``cb(demand_id, phase)``, called after a demand enters a phase.

        It runs after the commit and outside ``self._lock`` (so it may read and
        write the demand), on creation (``intake``) and on every successful
        ``transition``/``unblock_demand``. Its exceptions are logged and swallowed:
        the hook never undoes nor breaks the phase change. ``None`` removes it.
        """
        self._gancho_fase = cb

    def set_produtos(self, slugs) -> None:
        """Catalog of products the triage may name; ``None`` turns the check off."""
        self._produtos = None if slugs is None else frozenset(slugs)

    def _avisar_fase(self, demand_id: str, phase: Phase) -> None:
        cb = self._gancho_fase
        if cb is None:
            return
        try:
            cb(demand_id, phase.value)
        except Exception:
            logger.exception("gancho de fase falhou para %s (%s)", demand_id, phase.value)

    # -- internal helpers -----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Return a new connection with row-factory set to ``sqlite3.Row``."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        """Create the ``demands`` table if it does not exist.

        v2 adds: blocked_metadata, cancel_metadata, rework, rework_count columns.
        Existing databases are migrated automatically via ALTER TABLE.
        """
        ddl = """
        CREATE TABLE IF NOT EXISTS demands (
            id               TEXT PRIMARY KEY,
            title            TEXT    NOT NULL,
            description      TEXT    NOT NULL DEFAULT '',
            source           TEXT    NOT NULL DEFAULT '',
            priority         TEXT    NOT NULL DEFAULT 'medium',
            status           TEXT    NOT NULL DEFAULT 'open',
            phase            TEXT    NOT NULL DEFAULT 'intake',
            classification   JSON    NOT NULL DEFAULT '{}',
            artefacts        JSON    NOT NULL DEFAULT '{}',
            agent_history    JSON    NOT NULL DEFAULT '[]',
            blocked_metadata JSON             DEFAULT NULL,
            cancel_metadata  JSON             DEFAULT NULL,
            rework           INTEGER NOT NULL DEFAULT 0,
            rework_count     INTEGER NOT NULL DEFAULT 0,
            created_at       TEXT    NOT NULL,
            updated_at       TEXT    NOT NULL
        );
        """
        # v2 migration columns for existing databases
        _v2_migrations = [
            "ALTER TABLE demands ADD COLUMN blocked_metadata JSON DEFAULT NULL",
            "ALTER TABLE demands ADD COLUMN cancel_metadata  JSON DEFAULT NULL",
            "ALTER TABLE demands ADD COLUMN rework           INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE demands ADD COLUMN rework_count     INTEGER NOT NULL DEFAULT 0",
        ]
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(ddl)
                # Attempt v2 column migrations (silently ignore if columns exist)
                for migration in _v2_migrations:
                    try:
                        conn.execute(migration)
                    except Exception:
                        pass  # column already exists
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _now() -> str:
        """Return the current UTC time as an ISO-8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def _row_to_demand(self, row: sqlite3.Row) -> Demand:
        """Convert a database row into a :class:`Demand` instance."""
        # v2: safely read new columns (may be absent in older DBs)
        keys = row.keys()
        blocked_raw = row["blocked_metadata"] if "blocked_metadata" in keys else None
        cancel_raw = row["cancel_metadata"] if "cancel_metadata" in keys else None
        rework_val = row["rework"] if "rework" in keys else 0
        rework_cnt = row["rework_count"] if "rework_count" in keys else 0

        return Demand(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            source=row["source"],
            priority=row["priority"],
            phase=Phase(row["phase"]),
            classification=json.loads(row["classification"]),
            artefacts=json.loads(row["artefacts"]),
            agent_history=json.loads(row["agent_history"]),
            blocked_metadata=json.loads(blocked_raw) if blocked_raw else None,
            cancel_metadata=json.loads(cancel_raw) if cancel_raw else None,
            rework=bool(rework_val),
            rework_count=rework_cnt or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _next_id(self, conn: sqlite3.Connection) -> str:
        """Generate the next sequential ``DEM-XXX`` id.

        Reads the current max numeric suffix from the table and increments.
        Thread-safety is guaranteed by the caller holding ``self._lock``.
        """
        cur = conn.execute(
            "SELECT id FROM demands ORDER BY ROWID DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            return "DEM-001"
        last_num = int(row["id"].split("-")[1])
        return f"DEM-{last_num + 1:03d}"

    # -- public API -----------------------------------------------------------

    def create_demand(
        self,
        title: str,
        description: str = "",
        source: str = "",
        priority: str = "medium",
        tags: Optional[List[str]] = None,
    ) -> Demand:
        """Create a new demand in the INTAKE phase.

        Args:
            title:       Short human-readable title.
            description: Longer description / acceptance context.
            source:      Origin channel (``slack``, ``jira``, ``manual``).
            priority:    Priority label.
            tags:        Optional list of tags (stored in ``classification.tags``).

        Returns:
            The newly created :class:`Demand`.
        """
        now = self._now()
        classification: dict = {}
        if tags:
            classification["tags"] = tags

        with self._lock:
            conn = self._connect()
            try:
                demand_id = self._next_id(conn)
                conn.execute(
                    """
                    INSERT INTO demands
                        (id, title, description, source, priority, status,
                         phase, classification, artefacts, agent_history,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'open', 'intake', ?, '{}', '[]', ?, ?)
                    """,
                    (
                        demand_id,
                        title,
                        description,
                        source,
                        priority,
                        json.dumps(classification),
                        now,
                        now,
                    ),
                )
                conn.commit()
                demand = Demand(
                    id=demand_id,
                    title=title,
                    description=description,
                    source=source,
                    priority=priority,
                    phase=Phase.INTAKE,
                    classification=classification,
                    artefacts={},
                    agent_history=[],
                    created_at=now,
                    updated_at=now,
                )
            finally:
                conn.close()
        self._avisar_fase(demand.id, Phase.INTAKE)
        return demand

    def get_demand(self, demand_id: str) -> Optional[Demand]:
        """Fetch a single demand by id.

        Returns:
            The :class:`Demand` if found, otherwise ``None``.
        """
        conn = self._connect()
        try:
            cur = conn.execute("SELECT * FROM demands WHERE id = ?", (demand_id,))
            row = cur.fetchone()
            return self._row_to_demand(row) if row else None
        finally:
            conn.close()

    def pendencias(self, demand_id: str) -> list[str]:
        """What the gate of the next transition still misses (same check as ``transition``).

        Empty for a phase without a next one or for a transition without a gate.
        """
        demand = self.get_demand(demand_id)
        if demand is None:
            raise DemandNotFoundError(f"Demand {demand_id} not found")
        destino = PROXIMA_FASE.get(demand.phase.value)
        if destino is None:
            return []
        return _gate(demand.phase, Phase(destino), demand.artefacts or {}, self._produtos)[1]

    def list_demands(
        self, phase: Optional[Phase] = None, limit: int = 50
    ) -> List[Demand]:
        """List demands, optionally filtered by phase.

        Args:
            phase: If given, return only demands in this phase.
            limit: Maximum number of rows to return (default 50).

        Returns:
            List of :class:`Demand` ordered by creation date descending.
        """
        conn = self._connect()
        try:
            if phase is not None:
                cur = conn.execute(
                    "SELECT * FROM demands WHERE phase = ? ORDER BY created_at DESC LIMIT ?",
                    (phase.value, limit),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM demands ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            return [self._row_to_demand(row) for row in cur.fetchall()]
        finally:
            conn.close()

    # -- state machine --------------------------------------------------------

    def transition(
        self,
        demand_id: str,
        target_phase: Phase,
        actor: str = "system",
        reason: str = "",
        rework_reason: str = "",
    ) -> tuple[Demand, Dict[str, Any]]:
        """Move a demand to *target_phase* if the transition is valid.

        Args:
            demand_id:      The ``DEM-XXX`` identifier.
            target_phase:   Desired destination phase.
            actor:          Who/what initiated the transition.
            reason:         Free-text justification.
            rework_reason:  Required when transitioning REVIEW → DEV (rework).

        Returns:
            A tuple ``(updated_demand, event_dict)`` where *event_dict* is a
            structured payload suitable for SSE broadcast.

        Raises:
            DemandNotFoundError:    If *demand_id* does not exist.
            InvalidTransitionError: If the transition is not allowed.
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT * FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                current_phase = Phase(row["phase"])

                # Validate transition
                if target_phase == Phase.INTAKE:
                    # "any → intake" is always valid (reset / reopen)
                    pass
                elif target_phase in _VALID_TRANSITIONS.get(current_phase, set()):
                    pass
                else:
                    raise InvalidTransitionError(
                        f"Cannot transition {demand_id} from "
                        f"{current_phase.value} to {target_phase.value}"
                    )

                # BLOCKED → unblock: validate target matches origin_phase
                if current_phase == Phase.BLOCKED and target_phase not in (Phase.INTAKE, Phase.CANCELLED):
                    blocked_raw = row["blocked_metadata"] if "blocked_metadata" in row.keys() else None
                    blocked_meta = json.loads(blocked_raw) if blocked_raw else {}
                    origin = (blocked_meta or {}).get("origin_phase")
                    if not origin:
                        # Without a recorded origin the unblock could skip gates
                        raise InvalidTransitionError(
                            f"Cannot unblock {demand_id} to {target_phase.value}: "
                            f"no origin phase recorded (only intake or cancelled allowed)"
                        )
                    if Phase(origin) != target_phase:
                        raise InvalidTransitionError(
                            f"Cannot unblock {demand_id} to {target_phase.value}: "
                            f"must return to origin phase '{origin}'"
                        )

                requires_hitl = (current_phase, target_phase) in _HITL_GATES
                is_rework = (current_phase == Phase.REVIEW and target_phase == Phase.DEV)

                # Gate enforcement: artefacts required by the approved track
                _, missing, detail = _gate(
                    current_phase, target_phase, json.loads(row["artefacts"]), self._produtos
                )
                if missing:
                    raise MissingArtefactError(
                        demand_id,
                        missing,
                        f"{current_phase.value}->{target_phase.value}",
                        detail,
                    )

                now = self._now()

                # Append to agent_history
                history: list = json.loads(row["agent_history"])
                action_label = f"phase_transition:{current_phase.value}->{target_phase.value}"
                if is_rework:
                    action_label = f"rework:{current_phase.value}->{target_phase.value}"
                history.append(
                    {
                        "agent_id": actor,
                        "action": action_label,
                        "details": rework_reason if is_rework else reason,
                        "ts": now,
                    }
                )

                # Build SQL updates
                keys = row.keys()
                rework_count = row["rework_count"] if "rework_count" in keys else 0

                if is_rework:
                    rework_count = (rework_count or 0) + 1
                    conn.execute(
                        """
                        UPDATE demands
                           SET phase = ?, updated_at = ?, agent_history = ?,
                               rework = 1, rework_count = ?
                         WHERE id = ?
                        """,
                        (target_phase.value, now, json.dumps(history),
                         rework_count, demand_id),
                    )
                elif target_phase == Phase.BLOCKED:
                    # Blocking is done via block_demand(), but handle bare transition
                    # too, recording the origin so the unblock returns to it.
                    blocked_metadata = {
                        "origin_phase": current_phase.value,
                        "waiting_on": "",
                        "aguardando": "",
                        "next_action": "",
                        "follow_up_at": "",
                        "blocked_since": now,
                        "blocked_by": actor,
                    }
                    conn.execute(
                        """
                        UPDATE demands
                           SET phase = ?, updated_at = ?, agent_history = ?,
                               blocked_metadata = ?
                         WHERE id = ?
                        """,
                        (target_phase.value, now, json.dumps(history),
                         json.dumps(blocked_metadata), demand_id),
                    )
                else:
                    # Clear rework flag on any forward transition (but keep count)
                    conn.execute(
                        """
                        UPDATE demands
                           SET phase = ?, updated_at = ?, agent_history = ?,
                               rework = 0
                         WHERE id = ?
                        """,
                        (target_phase.value, now, json.dumps(history), demand_id),
                    )

                # Clear blocked_metadata when unblocking
                if current_phase == Phase.BLOCKED:
                    conn.execute(
                        "UPDATE demands SET blocked_metadata = NULL WHERE id = ?",
                        (demand_id,),
                    )

                conn.commit()

                demand = self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )

                event: Dict[str, Any] = {
                    "event_type": "demand.phase_changed",
                    "demand_id": demand_id,
                    "from_phase": current_phase.value,
                    "to_phase": target_phase.value,
                    "actor": actor,
                    "requires_hitl": requires_hitl,
                    "is_rework": is_rework,
                }
            finally:
                conn.close()
        self._avisar_fase(demand_id, target_phase)
        return demand, event

    # -- blocking & cancellation (v2) -----------------------------------------

    def block_demand(
        self,
        demand_id: str,
        waiting_on: str,
        next_action: str = "",
        follow_up_at: str = "",
        actor: str = "system",
        reason: str = "",
        aguardando: str = "",
    ) -> tuple[Demand, Dict[str, Any]]:
        """Block a demand, recording who/what it's waiting on.

        The demand must be in an active phase (SPIKE, SPEC, DEV, REVIEW).
        The origin phase is stored so that :meth:`unblock_demand` can
        return the demand to the correct phase.

        Args:
            demand_id:    The ``DEM-XXX`` identifier.
            waiting_on:   Free-text description of the blocker.
            next_action:  What needs to happen to unblock.
            follow_up_at: ISO-8601 date/time for follow-up reminder.
            actor:        Who initiated the block.
            reason:       Additional context.
            aguardando:   Closed category of the blocker (``core.triagem.AGUARDANDO``).

        Returns:
            A tuple ``(updated_demand, event_dict)``.

        Raises:
            DemandNotFoundError:    If *demand_id* does not exist.
            InvalidTransitionError: If the demand is not in a blockable phase.
            ValueError:             If *aguardando* is not one of ``AGUARDANDO``.
        """
        if aguardando and aguardando not in AGUARDANDO:
            raise ValueError(
                f"aguardando invalido: {aguardando!r} (use um de: {', '.join(AGUARDANDO)})"
            )
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT * FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                current_phase = Phase(row["phase"])
                if current_phase not in _BLOCKABLE_PHASES:
                    raise InvalidTransitionError(
                        f"Cannot block {demand_id}: phase '{current_phase.value}' "
                        f"is not blockable (must be one of: "
                        f"{', '.join(p.value for p in _BLOCKABLE_PHASES)})"
                    )

                now = self._now()
                blocked_metadata = {
                    "origin_phase": current_phase.value,
                    "waiting_on": waiting_on,
                    "aguardando": aguardando,
                    "next_action": next_action,
                    "follow_up_at": follow_up_at,
                    "blocked_since": now,
                    "blocked_by": actor,
                }

                history: list = json.loads(row["agent_history"])
                history.append({
                    "agent_id": actor,
                    "action": f"blocked:{current_phase.value}->blocked",
                    "details": reason or f"Aguardando: {waiting_on}",
                    "ts": now,
                })

                conn.execute(
                    """
                    UPDATE demands
                       SET phase = 'blocked', updated_at = ?,
                           agent_history = ?, blocked_metadata = ?
                     WHERE id = ?
                    """,
                    (now, json.dumps(history),
                     json.dumps(blocked_metadata), demand_id),
                )
                conn.commit()

                demand = self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )

                event: Dict[str, Any] = {
                    "event_type": "demand.blocked",
                    "demand_id": demand_id,
                    "from_phase": current_phase.value,
                    "to_phase": "blocked",
                    "waiting_on": waiting_on,
                    "actor": actor,
                }
                return demand, event
            finally:
                conn.close()

    def unblock_demand(
        self,
        demand_id: str,
        actor: str = "system",
        reason: str = "",
    ) -> tuple[Demand, Dict[str, Any]]:
        """Unblock a demand, returning it to its origin phase.

        Args:
            demand_id: The ``DEM-XXX`` identifier.
            actor:     Who resolved the blocker.
            reason:    Free-text explanation.

        Returns:
            A tuple ``(updated_demand, event_dict)``.

        Raises:
            DemandNotFoundError:    If *demand_id* does not exist.
            InvalidTransitionError: If the demand is not currently blocked.
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT * FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                current_phase = Phase(row["phase"])
                if current_phase != Phase.BLOCKED:
                    raise InvalidTransitionError(
                        f"Cannot unblock {demand_id}: not currently blocked "
                        f"(phase is '{current_phase.value}')"
                    )

                keys = row.keys()
                blocked_raw = row["blocked_metadata"] if "blocked_metadata" in keys else None
                if not blocked_raw:
                    raise InvalidTransitionError(
                        f"Cannot unblock {demand_id}: no blocked_metadata found"
                    )

                blocked_meta = json.loads(blocked_raw)
                origin_phase = Phase(blocked_meta["origin_phase"])

                now = self._now()
                history: list = json.loads(row["agent_history"])
                history.append({
                    "agent_id": actor,
                    "action": f"unblocked:blocked->{origin_phase.value}",
                    "details": reason,
                    "ts": now,
                })

                conn.execute(
                    """
                    UPDATE demands
                       SET phase = ?, updated_at = ?,
                           agent_history = ?, blocked_metadata = NULL
                     WHERE id = ?
                    """,
                    (origin_phase.value, now, json.dumps(history), demand_id),
                )
                conn.commit()

                demand = self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )

                event: Dict[str, Any] = {
                    "event_type": "demand.unblocked",
                    "demand_id": demand_id,
                    "from_phase": "blocked",
                    "to_phase": origin_phase.value,
                    "actor": actor,
                }
            finally:
                conn.close()
        self._avisar_fase(demand_id, origin_phase)
        return demand, event

    def cancel_demand(
        self,
        demand_id: str,
        reason: str,
        actor: str = "system",
    ) -> tuple[Demand, Dict[str, Any]]:
        """Cancel a demand. This is a terminal transition.

        Can be called from any phase except DONE and CANCELLED.

        Args:
            demand_id: The ``DEM-XXX`` identifier.
            reason:    Why the demand is being cancelled (required).
            actor:     Who cancelled it.

        Returns:
            A tuple ``(updated_demand, event_dict)``.

        Raises:
            DemandNotFoundError:    If *demand_id* does not exist.
            InvalidTransitionError: If the demand is already terminal.
            ValueError:             If *reason* is empty.
        """
        if not reason or not reason.strip():
            raise ValueError("Cancel reason is required")

        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT * FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                current_phase = Phase(row["phase"])
                if current_phase in (Phase.DONE, Phase.CANCELLED):
                    raise InvalidTransitionError(
                        f"Cannot cancel {demand_id}: already in terminal "
                        f"phase '{current_phase.value}'"
                    )

                now = self._now()
                cancel_metadata = {
                    "reason": reason.strip(),
                    "cancelled_by": actor,
                    "cancelled_at": now,
                    "from_phase": current_phase.value,
                }

                history: list = json.loads(row["agent_history"])
                history.append({
                    "agent_id": actor,
                    "action": f"cancelled:{current_phase.value}->cancelled",
                    "details": reason,
                    "ts": now,
                })

                conn.execute(
                    """
                    UPDATE demands
                       SET phase = 'cancelled', status = 'cancelled',
                           updated_at = ?, agent_history = ?,
                           cancel_metadata = ?, blocked_metadata = NULL
                     WHERE id = ?
                    """,
                    (now, json.dumps(history),
                     json.dumps(cancel_metadata), demand_id),
                )
                conn.commit()

                demand = self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )

                event: Dict[str, Any] = {
                    "event_type": "demand.cancelled",
                    "demand_id": demand_id,
                    "from_phase": current_phase.value,
                    "to_phase": "cancelled",
                    "reason": reason,
                    "actor": actor,
                }
                return demand, event
            finally:
                conn.close()

    # -- triagem ---------------------------------------------------------------

    def rebaixar_trilha(
        self, demand_id: str, nova: Trilha, motivo: str, actor: str
    ) -> Demand:
        """Change the demand's track, recording reason and author.

        Raises:
            ValueError:          If *motivo* is empty, *nova* is not a track,
                                 or the demand has no triagem.
            DemandNotFoundError: If *demand_id* does not exist.
        """
        if not motivo or not motivo.strip():
            raise ValueError("Rebaixar a trilha exige motivo")
        nova = Trilha(nova)
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM demands WHERE id = ?", (demand_id,)
                ).fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")
                artefacts: dict = json.loads(row["artefacts"])
                triagem = artefacts.get("triagem")
                if not isinstance(triagem, dict):
                    raise ValueError(f"{demand_id} nao tem triagem para rebaixar")
                de = str(triagem.get("trilha") or "")
                now = self._now()
                triagem["trilha"] = nova.value
                # The manager who changes the track approves the new one.
                triagem["aprovada_por"] = actor
                triagem["aprovada_em"] = now
                triagem.setdefault("rebaixamentos", []).append(
                    {"de": de, "para": nova.value, "motivo": motivo.strip(),
                     "autor": actor, "em": now}
                )
                history: list = json.loads(row["agent_history"])
                history.append({
                    "agent_id": actor,
                    "action": f"rebaixar_trilha:{de}->{nova.value}",
                    "details": motivo.strip(),
                    "ts": now,
                })
                conn.execute(
                    "UPDATE demands SET artefacts = ?, agent_history = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(artefacts), json.dumps(history), now, demand_id),
                )
                conn.commit()
                return self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )
            finally:
                conn.close()

    # -- classification -------------------------------------------------------

    def update_description(self, demand_id: str, description: str) -> Demand:
        """Replace the demand's description (e.g. the request text fetched later from the source).

        Raises:
            DemandNotFoundError: If *demand_id* does not exist.
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE demands SET description = ?, updated_at = ? WHERE id = ?",
                    (description, self._now(), demand_id),
                )
                if cur.rowcount == 0:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")
                conn.commit()
                return self._row_to_demand(
                    conn.execute("SELECT * FROM demands WHERE id = ?", (demand_id,)).fetchone()
                )
            finally:
                conn.close()

    def update_classification(
        self, demand_id: str, updates: Dict[str, Any]
    ) -> Demand:
        """Merge *updates* into the demand's classification dict.

        Args:
            demand_id: The ``DEM-XXX`` identifier.
            updates:   Key-value pairs to merge (shallow) into the existing
                       classification JSON.

        Returns:
            The updated :class:`Demand`.

        Raises:
            DemandNotFoundError: If *demand_id* does not exist.
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT classification FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                classification: dict = json.loads(row["classification"])
                classification.update(updates)
                now = self._now()

                conn.execute(
                    "UPDATE demands SET classification = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(classification), now, demand_id),
                )
                conn.commit()

                return self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )
            finally:
                conn.close()

    # -- artefacts & history --------------------------------------------------

    def update_artefact(
        self, demand_id: str, artefact_type: str, content: Any
    ) -> Demand:
        """Store or overwrite an artefact on a demand.

        Args:
            demand_id:     The ``DEM-XXX`` identifier.
            artefact_type: Key name (``spike``, ``user_stories``,
                           ``acceptance_criteria``, ``evidence``, …).
            content:       Artefact payload (string, dict, list, …).

        Returns:
            The updated :class:`Demand`.

        Raises:
            DemandNotFoundError: If *demand_id* does not exist.
            ValueError:          If a ``triagem`` write changes a track already
                                 chosen or rewrites ``rebaixamentos`` (both go
                                 only through :meth:`rebaixar_trilha`).
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT artefacts FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                artefacts: dict = json.loads(row["artefacts"])
                if artefact_type == "triagem":
                    content = _triagem_sem_troca(demand_id, artefacts.get("triagem"), content)
                artefacts[artefact_type] = content
                now = self._now()

                conn.execute(
                    "UPDATE demands SET artefacts = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(artefacts), now, demand_id),
                )
                conn.commit()

                return self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )
            finally:
                conn.close()

    def add_agent_action(
        self,
        demand_id: str,
        agent_id: str,
        action: str,
        details: str = "",
    ) -> Demand:
        """Append an action entry to the demand's agent history.

        Args:
            demand_id: The ``DEM-XXX`` identifier.
            agent_id:  Identifier of the agent performing the action.
            action:    Short verb/label for the action.
            details:   Optional free-text details.

        Returns:
            The updated :class:`Demand`.

        Raises:
            DemandNotFoundError: If *demand_id* does not exist.
        """
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "SELECT agent_history FROM demands WHERE id = ?", (demand_id,)
                )
                row = cur.fetchone()
                if row is None:
                    raise DemandNotFoundError(f"Demand {demand_id} not found")

                history: list = json.loads(row["agent_history"])
                history.append(
                    {
                        "agent_id": agent_id,
                        "action": action,
                        "details": details,
                        "ts": self._now(),
                    }
                )
                now = self._now()

                conn.execute(
                    "UPDATE demands SET agent_history = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(history), now, demand_id),
                )
                conn.commit()

                return self._row_to_demand(
                    conn.execute(
                        "SELECT * FROM demands WHERE id = ?", (demand_id,)
                    ).fetchone()
                )
            finally:
                conn.close()

    def get_demands_by_agent(self, agent_id: str) -> List[Demand]:
        """Return all demands where *agent_id* appears in the agent history.

        This performs a JSON substring search (``LIKE '%"agent_id": …%'``).
        For the expected data volumes (hundreds of demands) this is efficient
        enough without a separate index table.

        Args:
            agent_id: The agent identifier to search for.

        Returns:
            List of matching :class:`Demand` objects.
        """
        conn = self._connect()
        try:
            # Use json_each for correctness if available; fall back to LIKE.
            # SQLite ships json1 by default since 3.38 (2022-02).
            pattern = f'%"agent_id": "{agent_id}"%'
            cur = conn.execute(
                "SELECT * FROM demands WHERE agent_history LIKE ? ORDER BY created_at DESC",
                (pattern,),
            )
            return [self._row_to_demand(row) for row in cur.fetchall()]
        finally:
            conn.close()
    # -- artefact helpers -----------------------------------------------------

    @staticmethod
    def get_artefact_template(artefact_type: str) -> Any:
        """Return a deep copy of the template for *artefact_type*.

        Args:
            artefact_type: One of ``spike``, ``user_stories``,
                           ``acceptance_criteria``, ``evidence``.

        Returns:
            A fresh template dict/list that can be filled in and passed to
            :meth:`update_artefact`.

        Raises:
            KeyError: If *artefact_type* is not a known template.
        """
        import copy
        if artefact_type not in ARTEFACT_TEMPLATES:
            raise KeyError(
                f"Unknown artefact type: {artefact_type}. "
                f"Known: {list(ARTEFACT_TEMPLATES.keys())}"
            )
        return copy.deepcopy(ARTEFACT_TEMPLATES[artefact_type])

    def validate_artefacts(
        self, demand_id: str, target_phase: Phase
    ) -> Dict[str, Any]:
        """Check whether a demand has the required artefacts for a transition.

        Does NOT perform the transition — only validates.

        Args:
            demand_id:    The ``DEM-XXX`` identifier.
            target_phase: The phase the caller intends to transition to.

        Returns:
            A dict with keys ``valid`` (bool), ``missing`` (list of str),
            ``required`` (list of str), and ``existing`` (list of str).

        Raises:
            DemandNotFoundError: If *demand_id* does not exist.
        """
        dem = self.get_demand(demand_id)
        if dem is None:
            raise DemandNotFoundError(f"Demand {demand_id} not found")

        required, missing, detail = _gate(dem.phase, target_phase, dem.artefacts or {}, self._produtos)
        existing = list(dem.artefacts.keys()) if dem.artefacts else []

        return {
            "valid": len(missing) == 0,
            "missing": missing,
            "required": required,
            "existing": existing,
            "detail": detail,
        }


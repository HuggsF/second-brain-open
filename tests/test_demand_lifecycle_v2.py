"""
Tests for Demand Lifecycle v2 — State Machine extensions.

Covers:
  - BLOCKED phase: block, unblock, origin-phase enforcement
  - CANCELLED phase: cancel from any open phase, terminal enforcement
  - Rework flag: REVIEW→DEV with rework_reason
  - Days-in-current-phase & phase_age_badge computed properties
  - Edge cases: double-cancel, cancel from DONE, unblock non-blocked
"""

import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Ensure we can import core modules
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.demand_lifecycle import (
    DemandLifecycleService,
    Phase,
    Demand,
    DemandNotFoundError,
    InvalidTransitionError,
    MissingArtefactError,
)


TRIAGEM_LEVE = {
    "t1": False, "t2": False, "t3": False, "t4": True,
    "trilha": "leve", "aprovada_por": "gestor", "aprovada_em": "2026-11-09",
    "criterios_de_aceite": ["x"], "rebaixamentos": [], "mais_de_uma_sprint": False,
}


def _to_spike(svc, dem_id):
    """Grava a triagem aprovada (trilha leve) e avança INTAKE -> SPIKE."""
    svc.update_artefact(dem_id, "triagem", dict(TRIAGEM_LEVE))
    return svc.transition(dem_id, Phase.SPIKE, actor="test")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(tmp_path):
    """Create a DemandLifecycleService backed by a temp SQLite DB."""
    db = tmp_path / "test_demands.db"
    return DemandLifecycleService(db_path=db)


@pytest.fixture
def demand_in_dev(svc):
    """Create a demand and advance it to DEV phase."""
    dem = svc.create_demand("Test demand", "desc", source="test", priority="high")
    _to_spike(svc, dem.id)
    # Trilha leve: spike->spec e spec->dev nao exigem artefato
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.transition(dem.id, Phase.DEV, actor="test")
    return svc.get_demand(dem.id)


@pytest.fixture
def demand_in_review(svc, demand_in_dev):
    """Create a demand and advance it to REVIEW phase."""
    svc.transition(demand_in_dev.id, Phase.REVIEW, actor="test")
    return svc.get_demand(demand_in_dev.id)


# ---------------------------------------------------------------------------
# 1. BLOCKED phase tests
# ---------------------------------------------------------------------------

class TestBlocked:
    """Tests for blocking and unblocking demands."""

    def test_block_from_dev(self, svc, demand_in_dev):
        """DEV → BLOCKED with metadata should store origin_phase."""
        dem, evt = svc.block_demand(
            demand_in_dev.id,
            waiting_on="Resposta do aval de TI sobre API portal",
            next_action="Cobrar por email",
            follow_up_at="2026-11-10T10:00:00Z",
            actor="gestor-demandas",
        )
        assert dem.phase == Phase.BLOCKED
        assert dem.blocked_metadata is not None
        assert dem.blocked_metadata["origin_phase"] == "dev"
        assert dem.blocked_metadata["waiting_on"] == "Resposta do aval de TI sobre API portal"
        assert dem.blocked_metadata["next_action"] == "Cobrar por email"
        assert evt["event_type"] == "demand.blocked"
        assert evt["from_phase"] == "dev"

    def test_block_from_spike(self, svc):
        """SPIKE → BLOCKED should work."""
        dem = svc.create_demand("Spike test", source="test")
        _to_spike(svc, dem.id)
        blocked, evt = svc.block_demand(dem.id, waiting_on="Dependência externa", actor="gestor-demandas")
        assert blocked.phase == Phase.BLOCKED
        assert blocked.blocked_metadata["origin_phase"] == "spike"

    def test_block_from_spec(self, svc):
        """SPEC → BLOCKED should work."""
        dem = svc.create_demand("Spec test", source="test")
        _to_spike(svc, dem.id)
        svc.transition(dem.id, Phase.SPEC, actor="test")
        blocked, _ = svc.block_demand(dem.id, waiting_on="Aguardando PO", actor="gestor-demandas")
        assert blocked.phase == Phase.BLOCKED
        assert blocked.blocked_metadata["origin_phase"] == "spec"

    def test_block_from_review(self, svc, demand_in_review):
        """REVIEW → BLOCKED should work."""
        blocked, _ = svc.block_demand(demand_in_review.id, waiting_on="Code review pendente", actor="gestor-demandas")
        assert blocked.phase == Phase.BLOCKED
        assert blocked.blocked_metadata["origin_phase"] == "review"

    def test_cannot_block_intake(self, svc):
        """INTAKE → BLOCKED should fail (not a blockable phase)."""
        dem = svc.create_demand("Intake test", source="test")
        with pytest.raises(InvalidTransitionError, match="not blockable"):
            svc.block_demand(dem.id, waiting_on="anything", actor="gestor-demandas")

    def test_cannot_block_done(self, svc, demand_in_review):
        """DONE → BLOCKED should fail."""
        svc.update_artefact(demand_in_review.id, "evidence", {"test_results": ["pass"]})
        svc.transition(demand_in_review.id, Phase.DONE, actor="test")
        with pytest.raises(InvalidTransitionError, match="not blockable"):
            svc.block_demand(demand_in_review.id, waiting_on="anything", actor="gestor-demandas")

    def test_unblock_returns_to_origin(self, svc, demand_in_dev):
        """BLOCKED → origin_phase (DEV) should work via unblock."""
        svc.block_demand(demand_in_dev.id, waiting_on="Teste", actor="gestor-demandas")
        unblocked, evt = svc.unblock_demand(demand_in_dev.id, actor="gestor-demandas", reason="Resolvido")
        assert unblocked.phase == Phase.DEV
        assert unblocked.blocked_metadata is None
        assert evt["event_type"] == "demand.unblocked"
        assert evt["to_phase"] == "dev"

    def test_spike_blocked_spike_roundtrip(self, svc):
        """SPIKE → BLOCKED → SPIKE roundtrip."""
        dem = svc.create_demand("Roundtrip", source="test")
        _to_spike(svc, dem.id)
        svc.block_demand(dem.id, waiting_on="Decisão", actor="gestor-demandas")
        unblocked, _ = svc.unblock_demand(dem.id, actor="gestor-demandas")
        assert unblocked.phase == Phase.SPIKE

    def test_unblock_nonblocked_fails(self, svc, demand_in_dev):
        """Unblocking a demand that isn't blocked should fail."""
        with pytest.raises(InvalidTransitionError, match="not currently blocked"):
            svc.unblock_demand(demand_in_dev.id, actor="gestor-demandas")

    def test_blocked_transition_wrong_origin_fails(self, svc, demand_in_dev):
        """BLOCKED → wrong phase (not origin) via transition() should fail."""
        svc.block_demand(demand_in_dev.id, waiting_on="Teste", actor="gestor-demandas")
        # Try to transition to SPEC (origin was DEV)
        with pytest.raises(InvalidTransitionError, match="must return to origin phase"):
            svc.transition(demand_in_dev.id, Phase.SPEC, actor="gestor-demandas")

    def test_blocked_history_recorded(self, svc, demand_in_dev):
        """Blocking should append to agent_history."""
        svc.block_demand(demand_in_dev.id, waiting_on="Teste", actor="gestor-demandas")
        dem = svc.get_demand(demand_in_dev.id)
        blocked_entries = [h for h in dem.agent_history if "blocked" in h.get("action", "")]
        assert len(blocked_entries) >= 1


# ---------------------------------------------------------------------------
# 2. CANCELLED phase tests
# ---------------------------------------------------------------------------

class TestCancelled:
    """Tests for cancelling demands."""

    def test_cancel_from_intake(self, svc):
        """INTAKE → CANCELLED with reason."""
        dem = svc.create_demand("Cancel me", source="test")
        cancelled, evt = svc.cancel_demand(dem.id, reason="Duplicata", actor="gestor-demandas")
        assert cancelled.phase == Phase.CANCELLED
        assert cancelled.cancel_metadata is not None
        assert cancelled.cancel_metadata["reason"] == "Duplicata"
        assert cancelled.cancel_metadata["from_phase"] == "intake"
        assert evt["event_type"] == "demand.cancelled"

    def test_cancel_from_dev(self, svc, demand_in_dev):
        """DEV → CANCELLED should work."""
        cancelled, _ = svc.cancel_demand(demand_in_dev.id, reason="Prioridade mudou", actor="gestor-demandas")
        assert cancelled.phase == Phase.CANCELLED
        assert cancelled.cancel_metadata["from_phase"] == "dev"

    def test_cancel_from_blocked(self, svc, demand_in_dev):
        """BLOCKED → CANCELLED should work."""
        svc.block_demand(demand_in_dev.id, waiting_on="Teste", actor="gestor-demandas")
        cancelled, _ = svc.cancel_demand(demand_in_dev.id, reason="Bloqueio sem resolução", actor="gestor-demandas")
        assert cancelled.phase == Phase.CANCELLED
        assert cancelled.blocked_metadata is None  # cleared on cancel

    def test_cancel_from_done_fails(self, svc, demand_in_review):
        """DONE → CANCELLED should fail (terminal phase)."""
        svc.update_artefact(demand_in_review.id, "evidence", {"test_results": ["pass"]})
        svc.transition(demand_in_review.id, Phase.DONE, actor="test")
        with pytest.raises(InvalidTransitionError, match="terminal"):
            svc.cancel_demand(demand_in_review.id, reason="Nope", actor="gestor-demandas")

    def test_cancel_from_cancelled_fails(self, svc):
        """CANCELLED → CANCELLED should fail (already terminal)."""
        dem = svc.create_demand("Double cancel", source="test")
        svc.cancel_demand(dem.id, reason="First cancel", actor="gestor-demandas")
        with pytest.raises(InvalidTransitionError, match="terminal"):
            svc.cancel_demand(dem.id, reason="Second cancel", actor="gestor-demandas")

    def test_cancelled_no_outgoing(self, svc):
        """CANCELLED → any other phase via transition() should fail."""
        dem = svc.create_demand("Terminal test", source="test")
        svc.cancel_demand(dem.id, reason="Done", actor="gestor-demandas")
        for target in [Phase.SPIKE, Phase.DEV, Phase.REVIEW, Phase.DONE, Phase.BLOCKED]:
            with pytest.raises(InvalidTransitionError):
                svc.transition(dem.id, target, actor="gestor-demandas")

    def test_cancel_requires_reason(self, svc):
        """Cancel without reason should raise ValueError."""
        dem = svc.create_demand("No reason", source="test")
        with pytest.raises(ValueError, match="reason is required"):
            svc.cancel_demand(dem.id, reason="", actor="gestor-demandas")
        with pytest.raises(ValueError, match="reason is required"):
            svc.cancel_demand(dem.id, reason="   ", actor="gestor-demandas")


# ---------------------------------------------------------------------------
# 3. Rework flag tests
# ---------------------------------------------------------------------------

class TestRework:
    """Tests for REVIEW → DEV rework transitions."""

    def test_rework_sets_flag(self, svc, demand_in_review):
        """REVIEW → DEV should set rework=True and increment rework_count."""
        reworked, evt = svc.transition(
            demand_in_review.id, Phase.DEV,
            actor="gestor-demandas", rework_reason="Testes falhando"
        )
        assert reworked.phase == Phase.DEV
        assert reworked.rework is True
        assert reworked.rework_count == 1
        assert evt["is_rework"] is True

    def test_rework_count_increments(self, svc, demand_in_review):
        """Multiple reworks should increment counter."""
        # First rework
        svc.transition(demand_in_review.id, Phase.DEV, actor="gestor-demandas", rework_reason="Bug 1")
        # Go back to review
        svc.transition(demand_in_review.id, Phase.REVIEW, actor="gestor-demandas")
        # Second rework
        dem, _ = svc.transition(demand_in_review.id, Phase.DEV, actor="gestor-demandas", rework_reason="Bug 2")
        assert dem.rework_count == 2
        assert dem.rework is True

    def test_forward_transition_clears_rework_flag(self, svc, demand_in_review):
        """After rework, forward transition (DEV→REVIEW) should clear rework flag."""
        svc.transition(demand_in_review.id, Phase.DEV, actor="gestor-demandas", rework_reason="Fix needed")
        dem = svc.get_demand(demand_in_review.id)
        assert dem.rework is True
        # Forward again
        dem2, _ = svc.transition(demand_in_review.id, Phase.REVIEW, actor="gestor-demandas")
        assert dem2.rework is False
        assert dem2.rework_count == 1  # Count preserved

    def test_rework_history_recorded(self, svc, demand_in_review):
        """Rework should be recorded in agent_history with rework label."""
        svc.transition(demand_in_review.id, Phase.DEV, actor="gestor-demandas", rework_reason="Corrigir edge case")
        dem = svc.get_demand(demand_in_review.id)
        rework_entries = [h for h in dem.agent_history if "rework:" in h.get("action", "")]
        assert len(rework_entries) == 1
        assert rework_entries[0]["details"] == "Corrigir edge case"


# ---------------------------------------------------------------------------
# 4. Days-in-current-phase & badge tests
# ---------------------------------------------------------------------------

class TestDaysInPhase:
    """Tests for computed phase age properties."""

    def test_days_green(self, svc):
        """Freshly created demand should have green badge."""
        dem = svc.create_demand("Fresh", source="test")
        assert dem.days_in_current_phase < 1
        assert dem.phase_age_badge == "green"

    def test_days_calculation(self):
        """Manual test with backdated updated_at."""
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        dem = Demand(
            id="DEM-999", title="Old", description="", source="",
            priority="medium", phase=Phase.DEV,
            updated_at=three_days_ago,
        )
        assert 2.5 < dem.days_in_current_phase < 3.5
        assert dem.phase_age_badge == "yellow"

    def test_days_red_badge(self):
        """Demand older than 5 days should have red badge."""
        old = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        dem = Demand(
            id="DEM-998", title="Stale", description="", source="",
            priority="medium", phase=Phase.DEV,
            updated_at=old,
        )
        assert dem.days_in_current_phase > 5
        assert dem.phase_age_badge == "red"

    def test_empty_updated_at(self):
        """Empty updated_at should return 0 days."""
        dem = Demand(
            id="DEM-997", title="No date", description="", source="",
            priority="medium", phase=Phase.INTAKE,
            updated_at="",
        )
        assert dem.days_in_current_phase == 0.0
        assert dem.phase_age_badge == "green"


# ---------------------------------------------------------------------------
# 5. Schema migration tests
# ---------------------------------------------------------------------------

class TestSchemaMigration:
    """Tests for v2 column migrations on existing databases."""

    def test_v1_db_gets_migrated(self, tmp_path):
        """A database without v2 columns should get them via migration."""
        import sqlite3
        db = tmp_path / "v1.db"
        # Create a v1-style table
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE demands (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                description     TEXT NOT NULL DEFAULT '',
                source          TEXT NOT NULL DEFAULT '',
                priority        TEXT NOT NULL DEFAULT 'medium',
                status          TEXT NOT NULL DEFAULT 'open',
                phase           TEXT NOT NULL DEFAULT 'intake',
                classification  JSON NOT NULL DEFAULT '{}',
                artefacts       JSON NOT NULL DEFAULT '{}',
                agent_history   JSON NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        # Now create the service — should add v2 columns
        svc = DemandLifecycleService(db_path=db)
        dem = svc.create_demand("Migration test", source="test")
        assert dem.blocked_metadata is None
        assert dem.cancel_metadata is None
        assert dem.rework is False
        assert dem.rework_count == 0

    def test_fresh_db_has_v2_columns(self, tmp_path):
        """A fresh database should have v2 columns in the schema."""
        import sqlite3
        db = tmp_path / "fresh.db"
        svc = DemandLifecycleService(db_path=db)
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        cur = conn.execute("PRAGMA table_info(demands)")
        cols = {row["name"] for row in cur.fetchall()}
        conn.close()
        assert "blocked_metadata" in cols
        assert "cancel_metadata" in cols
        assert "rework" in cols
        assert "rework_count" in cols


# ---------------------------------------------------------------------------
# 6. Edge case / integration tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and integration scenarios."""

    def test_done_no_outgoing(self, svc, demand_in_review):
        """DONE → any should fail (except intake reset)."""
        svc.update_artefact(demand_in_review.id, "evidence", {"test_results": ["pass"]})
        svc.transition(demand_in_review.id, Phase.DONE, actor="test")
        for target in [Phase.SPIKE, Phase.DEV, Phase.BLOCKED, Phase.CANCELLED]:
            with pytest.raises(InvalidTransitionError):
                svc.transition(demand_in_review.id, target, actor="test")

    def test_nonexistent_demand_block(self, svc):
        """Blocking a nonexistent demand should raise DemandNotFoundError."""
        with pytest.raises(DemandNotFoundError):
            svc.block_demand("DEM-999", waiting_on="x", actor="gestor-demandas")

    def test_nonexistent_demand_cancel(self, svc):
        """Cancelling a nonexistent demand should raise DemandNotFoundError."""
        with pytest.raises(DemandNotFoundError):
            svc.cancel_demand("DEM-999", reason="x", actor="gestor-demandas")

    def test_full_lifecycle_with_block_and_rework(self, svc):
        """Full lifecycle: INTAKE→SPIKE→BLOCKED→SPIKE→SPEC→DEV→REVIEW→DEV(rework)→REVIEW→DONE."""
        # Create
        dem = svc.create_demand("Full lifecycle", "Integration test", source="test")
        assert dem.phase == Phase.INTAKE

        # INTAKE → SPIKE
        dem, _ = _to_spike(svc, dem.id)
        assert dem.phase == Phase.SPIKE

        # SPIKE → BLOCKED
        dem, _ = svc.block_demand(dem.id, waiting_on="API docs", actor="gestor-demandas")
        assert dem.phase == Phase.BLOCKED

        # BLOCKED → SPIKE (unblock)
        dem, _ = svc.unblock_demand(dem.id, actor="gestor-demandas", reason="Docs received")
        assert dem.phase == Phase.SPIKE

        # SPIKE → SPEC (trilha leve: sem artefato)
        dem, _ = svc.transition(dem.id, Phase.SPEC, actor="test")
        assert dem.phase == Phase.SPEC

        # SPEC → DEV (trilha leve: sem artefato)
        dem, _ = svc.transition(dem.id, Phase.DEV, actor="test")
        assert dem.phase == Phase.DEV

        # DEV → REVIEW
        dem, _ = svc.transition(dem.id, Phase.REVIEW, actor="test")
        assert dem.phase == Phase.REVIEW

        # REVIEW → DEV (rework)
        dem, evt = svc.transition(dem.id, Phase.DEV, actor="gestor-demandas", rework_reason="Bug found")
        assert dem.phase == Phase.DEV
        assert dem.rework is True
        assert dem.rework_count == 1
        assert evt["is_rework"] is True

        # DEV → REVIEW (again)
        dem, _ = svc.transition(dem.id, Phase.REVIEW, actor="test")
        assert dem.phase == Phase.REVIEW
        assert dem.rework is False  # flag cleared
        assert dem.rework_count == 1  # count preserved

        # REVIEW → DONE (with evidence)
        svc.update_artefact(dem.id, "evidence", {"test_results": ["all pass"]})
        dem, _ = svc.transition(dem.id, Phase.DONE, actor="test")
        assert dem.phase == Phase.DONE

        # Verify history has all transitions
        assert len(dem.agent_history) >= 8

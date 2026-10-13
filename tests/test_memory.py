"""Testes unitários para a camada de governança de memória do Compound AI."""
import tempfile
from pathlib import Path
import pytest

from core.memory import SessionMemoryStore, QuarantineStore, MemoryPurger


def test_session_memory_isolation():
    store = SessionMemoryStore()
    store.append("mission_a", {"step": 1, "thought": "analisando logistica"})
    store.append("mission_b", {"step": 1, "thought": "analisando sap"})

    hist_a = store.get_history("mission_a")
    hist_b = store.get_history("mission_b")

    assert len(hist_a) == 1
    assert hist_a[0]["thought"] == "analisando logistica"
    assert len(hist_b) == 1
    assert hist_b[0]["thought"] == "analisando sap"

    purged = store.purge_session("mission_a")
    assert purged == 1
    assert len(store.get_history("mission_a")) == 0
    assert len(store.get_history("mission_b")) == 1


def test_quarantine_store_deposit_and_promote():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        q_dir = tmp_path / "quarantine"
        vault_mock = tmp_path / "vault"
        vault_mock.mkdir()

        q_store = QuarantineStore(quarantine_dir=q_dir)
        item = q_store.deposit(
            target_vault_path="adrs/ADR-TEST.md",
            author_agent="architect",
            title="ADR de Teste",
            content="# ADR Teste\nConteudo gerado.",
        )

        assert item.status == "PENDING_REVIEW"
        assert item.candidate_id.startswith("quarantine_")

        pending = q_store.list_pending()
        assert len(pending) == 1
        assert pending[0].title == "ADR de Teste"

        # Mock settings.vault_dir para o teste de promoção
        from unittest import mock
        with mock.patch("core.memory.quarantine_store.settings.vault_dir", vault_mock):
            promoted_path = q_store.promote_to_vault(item.candidate_id, reviewer="hugo_dev")
            assert promoted_path.is_file()
            assert promoted_path.read_text(encoding="utf-8") == "# ADR Teste\nConteudo gerado."

            # Não deve mais constar em pendentes
            assert len(q_store.list_pending()) == 0


def test_memory_purger_safety():
    store = SessionMemoryStore()
    store.append("s1", {"data": 123})
    with tempfile.TemporaryDirectory() as tmp_dir:
        q_store = QuarantineStore(quarantine_dir=Path(tmp_dir))
        q_store.deposit("teste.md", "dev", "Titulo", "Texto")

        purger = MemoryPurger(session_store=store, quarantine_store=q_store)
        res = purger.purge_all_transient()

        assert res["sessions_purged"] == 1
        assert res["quarantine_purged"] == 1
        assert res["vault_preserved"] is True

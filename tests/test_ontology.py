"""Tests for core.ontology — DDD ontology parser and resolution."""
import pytest
from core.ontology import load_ontology, resolve_term, list_bounded_contexts, list_entities


class TestLoadOntology:
    def test_returns_registry_with_entities(self):
        reg = load_ontology()
        assert len(reg.entities) >= 10, f"Expected >= 10 entities, got {len(reg.entities)}"

    def test_returns_5_bounded_contexts(self):
        reg = load_ontology()
        assert len(reg.bounded_contexts) == 5

    def test_no_errors(self):
        reg = load_ontology()
        assert reg.errors == [], f"Unexpected errors: {reg.errors}"

    def test_status_is_proposal(self):
        reg = load_ontology()
        assert "proposta" in reg.status.lower()


class TestResolveTerm:
    def test_resolve_order_to_dispatchjob(self):
        matches = resolve_term("Order")
        names = [m["proposed_name"] for m in matches]
        assert any("DispatchJob" in n for n in names), f"DispatchJob not in {names}"

    def test_resolve_dispatchjob(self):
        matches = resolve_term("DispatchJob")
        assert len(matches) >= 1
        assert matches[0]["proposed_name"] == "DispatchJob"

    def test_resolve_universalpayload(self):
        matches = resolve_term("UniversalPayload")
        names = [m["proposed_name"] for m in matches]
        assert any("DispatchRequest" in n for n in names)

    def test_fuzzy_case_insensitive(self):
        matches = resolve_term("dispatch")
        assert len(matches) >= 2  # DispatchJob, DispatchRequest at least

    def test_empty_string_returns_empty(self):
        assert resolve_term("") == []
        assert resolve_term("   ") == []

    def test_no_match_returns_empty(self):
        assert resolve_term("xyznonexistent") == []

    def test_max_10_results(self):
        # Even if many match, at most 10
        matches = resolve_term("a")  # very broad
        assert len(matches) <= 10

    def test_result_has_bounded_context(self):
        matches = resolve_term("DispatchJob")
        if matches:
            assert matches[0]["bounded_context"] != ""

    def test_erp_port_resolves(self):
        matches = resolve_term("ErpPort")
        assert len(matches) >= 1


class TestListBoundedContexts:
    def test_returns_5(self):
        bcs = list_bounded_contexts()
        assert len(bcs) == 5

    def test_has_required_fields(self):
        bcs = list_bounded_contexts()
        for bc in bcs:
            assert "id" in bc
            assert "name" in bc
            assert "entities" in bc
            assert isinstance(bc["entities"], list)

    def test_bc_names(self):
        bcs = list_bounded_contexts()
        names = {bc["name"] for bc in bcs}
        assert "Fiscal" in names
        assert "Expedição e Remessas" in names


class TestListEntities:
    def test_list_all(self):
        entities = list_entities()
        assert len(entities) >= 10

    def test_filter_by_bc(self):
        fiscal = list_entities("Fiscal")
        assert len(fiscal) >= 1
        for e in fiscal:
            assert "fiscal" in e["bounded_context"].lower()

    def test_filter_no_match(self):
        result = list_entities("NonexistentContext")
        assert result == []

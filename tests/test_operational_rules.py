import pytest
from core.operational_rules import load_operational_rules, list_rules, get_details

def test_load_returns_registry():
    reg = load_operational_rules()
    assert len(reg.rules) >= 70, f"Expected >= 70 rules, got {len(reg.rules)}"

def test_list_all_rules():
    rules = list_rules()
    assert len(rules) >= 70

def test_list_by_category():
    emission = list_rules("emission")
    assert len(emission) == 19
    preflight = list_rules("preflight")
    assert len(preflight) == 7
    nfe = list_rules("nfe")
    assert len(nfe) == 13

def test_get_details_valid():
    details = get_details("INV-01")
    assert details["id"] == "INV-01"
    assert "reentrada" in details["description"].lower() or "WeakSet" in details["description"]
    assert details["category"] == "emission"

def test_get_details_invalid():
    result = get_details("INVALID-99")
    assert "error" in result

def test_categories_complete():
    rules = list_rules()
    categories = {r["category"] for r in rules}
    expected = {"emission", "preflight", "nfe", "recovery", "weight", "monitor", "logging", "deploy"}
    assert categories == expected, f"Missing categories: {expected - categories}"

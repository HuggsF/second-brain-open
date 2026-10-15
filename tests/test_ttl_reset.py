"""Tests for F-OR-05: TTL reset após HITL (PD-OVR-003).

Validates that mission_start is reset after _wait_approval returns,
so the 30s TTL counts from approval, not from mission submission.
"""
import ast
import inspect


def test_ttl_reset_after_manager_approval():
    """Verify that mission_start = time.time() appears after _wait_approval in run_mission."""
    from backend.orchestrator import Orchestrator
    source = inspect.getsource(Orchestrator.run_mission)
    # Parse the AST to verify the TTL reset is present
    assert "mission_start = time.time()" in source
    # Verify it appears AFTER _wait_approval
    wait_pos = source.find("_wait_approval()")
    reset_pos = source.find("mission_start = time.time()", wait_pos)
    assert reset_pos > wait_pos, "TTL reset must come after _wait_approval"


def test_ttl_reset_after_reviewer_approval():
    """Verify TTL reset exists at the reviewer approval point too."""
    from backend.orchestrator import Orchestrator
    source = inspect.getsource(Orchestrator.run_mission)
    # There should be at least 2 occurrences of the TTL reset
    count = source.count("mission_start = time.time()")
    # 1 initial + 2 resets = 3, or at minimum 2 resets after approval
    assert count >= 3, f"Expected at least 3 mission_start assignments (1 init + 2 resets), found {count}"

import time
from unittest import mock
from core.resilience.circuit_breaker import ToolCircuitBreaker, CircuitState

def test_half_open_only_one_probe():
    cb = ToolCircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
    # Force OPEN
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.02)  # trigger HALF_OPEN
    # 1st request: allowed (probe)
    assert cb.allow_request() is True
    # 2nd request: blocked
    assert cb.allow_request() is False
    # 3rd request: still blocked
    assert cb.allow_request() is False

def test_probe_success_allows_new_probe_in_next_cycle():
    cb = ToolCircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.02)
    assert cb.allow_request() is True  # probe
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    # Trigger new OPEN→HALF_OPEN cycle
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.02)
    assert cb.allow_request() is True  # new probe allowed

def test_probe_failure_reopens_and_new_probe_later():
    cb = ToolCircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.02)
    assert cb.allow_request() is True  # probe
    cb.record_failure()  # probe fails → reopen
    assert cb.state == CircuitState.OPEN
    time.sleep(0.02)  # new HALF_OPEN
    assert cb.allow_request() is True  # new probe allowed

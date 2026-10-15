"""Testes para core/resilience — Circuit Breaker e Rate Limiter.

Sprint 3 (Gaps G3 + G5): Cobertura completa dos módulos de resiliência.
"""

import time
import threading
from unittest.mock import patch

import pytest

from core.resilience.circuit_breaker import (
    CircuitState,
    CircuitStats,
    ToolCircuitBreaker,
    CircuitBreakerRegistry,
)
from core.resilience.rate_limiter import (
    BucketConfig,
    TokenBucket,
    RateLimiterRegistry,
    DEFAULT_BUCKET_CONFIGS,
)


# ─────────────────────────────────────────────
# CircuitStats
# ─────────────────────────────────────────────

class TestCircuitStats:
    def test_to_dict_defaults(self):
        s = CircuitStats(tool_name="my_tool")
        d = s.to_dict()
        assert d["tool_name"] == "my_tool"
        assert d["state"] == "CLOSED"
        assert d["failure_count"] == 0
        assert d["success_count"] == 0
        assert d["total_rejected"] == 0
        assert d["last_failure_time"] is None
        assert d["opened_at"] is None


# ─────────────────────────────────────────────
# ToolCircuitBreaker
# ─────────────────────────────────────────────

class TestToolCircuitBreaker:
    def test_initial_state_closed(self):
        cb = ToolCircuitBreaker("tool_a")
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.tool_name == "tool_a"

    def test_allow_request_when_closed(self):
        cb = ToolCircuitBreaker("tool_a")
        assert cb.allow_request() is True

    def test_closed_to_open_after_threshold(self):
        cb = ToolCircuitBreaker("tool_b", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_requests(self):
        cb = ToolCircuitBreaker("tool_c", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False
        assert cb.stats.total_rejected == 1

    def test_open_to_half_open_after_timeout(self):
        cb = ToolCircuitBreaker("tool_d", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_request(self):
        cb = ToolCircuitBreaker("tool_e", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_to_closed_on_success(self):
        cb = ToolCircuitBreaker("tool_f", failure_threshold=1, recovery_timeout=0.1, success_threshold=1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = ToolCircuitBreaker("tool_g", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets_consecutive_failures(self):
        cb = ToolCircuitBreaker("tool_h", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # reset consecutivas
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # não abriu, pois 1 falha < 3

    def test_success_threshold_multiple(self):
        """success_threshold=2 exige 2 sucessos em HALF_OPEN para fechar."""
        cb = ToolCircuitBreaker("tool_i", failure_threshold=1, recovery_timeout=0.1, success_threshold=2)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # ainda precisa de mais 1
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_everything(self):
        cb = ToolCircuitBreaker("tool_j", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failure_count == 0
        assert cb.stats.total_rejected == 0

    def test_stats_returns_copy(self):
        """stats retorna uma cópia, não a referência interna."""
        cb = ToolCircuitBreaker("tool_k")
        s1 = cb.stats
        cb.record_failure()
        s2 = cb.stats
        assert s1.failure_count == 0  # cópia não foi alterada
        assert s2.failure_count == 1

    def test_multiple_rejections_counted(self):
        cb = ToolCircuitBreaker("tool_l", failure_threshold=1)
        cb.record_failure()
        cb.allow_request()
        cb.allow_request()
        cb.allow_request()
        assert cb.stats.total_rejected == 3

    def test_open_state_records_opened_at(self):
        cb = ToolCircuitBreaker("tool_m", failure_threshold=1)
        cb.record_failure()
        assert cb.stats.opened_at is not None


# ─────────────────────────────────────────────
# CircuitBreakerRegistry
# ─────────────────────────────────────────────

class TestCircuitBreakerRegistry:
    def test_get_creates_breaker(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get("tool_x")
        assert isinstance(cb, ToolCircuitBreaker)
        assert cb.tool_name == "tool_x"

    def test_get_returns_same_instance(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get("tool_y")
        cb2 = reg.get("tool_y")
        assert cb1 is cb2

    def test_get_open_tools_empty(self):
        reg = CircuitBreakerRegistry()
        reg.get("tool_a")
        assert reg.get_open_tools() == []

    def test_get_open_tools_returns_open(self):
        reg = CircuitBreakerRegistry(failure_threshold=1)
        cb = reg.get("failing_tool")
        cb.record_failure()
        assert "failing_tool" in reg.get_open_tools()

    def test_get_all_stats(self):
        reg = CircuitBreakerRegistry()
        reg.get("tool_1")
        reg.get("tool_2")
        stats = reg.get_all_stats()
        assert "tool_1" in stats
        assert "tool_2" in stats
        assert stats["tool_1"]["state"] == "CLOSED"

    def test_reset_all(self):
        reg = CircuitBreakerRegistry(failure_threshold=1)
        cb = reg.get("tool_z")
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        count = reg.reset_all()
        assert count == 1
        assert cb.state == CircuitState.CLOSED

    def test_registry_uses_configured_threshold(self):
        reg = CircuitBreakerRegistry(failure_threshold=5, recovery_timeout=60.0)
        cb = reg.get("custom_tool")
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 60.0


# ─────────────────────────────────────────────
# BucketConfig
# ─────────────────────────────────────────────

class TestBucketConfig:
    def test_default_initial_tokens_equals_max(self):
        cfg = BucketConfig(max_tokens=10, refill_rate=0.5)
        assert cfg.initial_tokens == 10

    def test_custom_initial_tokens(self):
        cfg = BucketConfig(max_tokens=10, refill_rate=0.5, initial_tokens=3)
        assert cfg.initial_tokens == 3

    def test_default_bucket_configs_exist(self):
        assert "run_safe_command" in DEFAULT_BUCKET_CONFIGS
        assert DEFAULT_BUCKET_CONFIGS["run_safe_command"].max_tokens == 5


# ─────────────────────────────────────────────
# TokenBucket
# ─────────────────────────────────────────────

class TestTokenBucket:
    def test_initial_tokens_full(self):
        bucket = TokenBucket("t1", BucketConfig(max_tokens=5, refill_rate=1.0))
        assert bucket.available_tokens == pytest.approx(5.0, abs=0.5)

    def test_acquire_success(self):
        bucket = TokenBucket("t2", BucketConfig(max_tokens=5, refill_rate=1.0))
        assert bucket.try_acquire() is True

    def test_acquire_depletes_bucket(self):
        bucket = TokenBucket("t3", BucketConfig(max_tokens=3, refill_rate=0.0, initial_tokens=3))
        assert bucket.try_acquire() is True
        assert bucket.try_acquire() is True
        assert bucket.try_acquire() is True
        assert bucket.try_acquire() is False  # esgotou

    def test_rejection_counted(self):
        bucket = TokenBucket("t4", BucketConfig(max_tokens=1, refill_rate=0.0, initial_tokens=1))
        bucket.try_acquire()
        bucket.try_acquire()
        stats = bucket.get_stats()
        assert stats["total_allowed"] == 1
        assert stats["total_rejected"] == 1

    def test_refill_over_time(self):
        bucket = TokenBucket("t5", BucketConfig(max_tokens=5, refill_rate=20.0, initial_tokens=0))
        # Começa vazio, refill rápido: 20 tokens/s
        assert bucket.try_acquire() is False
        time.sleep(0.15)  # ~3 tokens devem ter sido adicionados
        assert bucket.try_acquire() is True

    def test_tokens_capped_at_max(self):
        bucket = TokenBucket("t6", BucketConfig(max_tokens=3, refill_rate=100.0, initial_tokens=3))
        time.sleep(0.1)  # recarga >> max
        assert bucket.available_tokens == pytest.approx(3.0, abs=0.1)

    def test_get_stats_structure(self):
        bucket = TokenBucket("t7", BucketConfig(max_tokens=10, refill_rate=0.5))
        stats = bucket.get_stats()
        assert "tool_name" in stats
        assert "available_tokens" in stats
        assert "max_tokens" in stats
        assert "refill_rate" in stats
        assert "total_allowed" in stats
        assert "total_rejected" in stats

    def test_reset(self):
        bucket = TokenBucket("t8", BucketConfig(max_tokens=5, refill_rate=0.0, initial_tokens=5))
        for _ in range(5):
            bucket.try_acquire()
        assert bucket.available_tokens == pytest.approx(0.0, abs=0.1)
        bucket.reset()
        assert bucket.available_tokens == pytest.approx(5.0, abs=0.1)

    def test_acquire_multiple_tokens(self):
        bucket = TokenBucket("t9", BucketConfig(max_tokens=5, refill_rate=0.0, initial_tokens=5))
        assert bucket.try_acquire(tokens=3) is True
        assert bucket.try_acquire(tokens=3) is False  # só tem 2

    def test_uses_default_config_for_unknown_tool(self):
        bucket = TokenBucket("unknown_tool_xyz")
        # Deve usar _DEFAULT_CONFIG: max_tokens=30, refill_rate=1.0
        assert bucket.config.max_tokens == 30
        assert bucket.config.refill_rate == 1.0

    def test_uses_specific_config_for_known_tool(self):
        bucket = TokenBucket("run_safe_command")
        assert bucket.config.max_tokens == 5
        assert bucket.config.refill_rate == 0.1


# ─────────────────────────────────────────────
# RateLimiterRegistry
# ─────────────────────────────────────────────

class TestRateLimiterRegistry:
    def test_get_creates_bucket(self):
        reg = RateLimiterRegistry()
        bucket = reg.get("tool_a")
        assert isinstance(bucket, TokenBucket)
        assert bucket.tool_name == "tool_a"

    def test_get_returns_same_instance(self):
        reg = RateLimiterRegistry()
        b1 = reg.get("tool_b")
        b2 = reg.get("tool_b")
        assert b1 is b2

    def test_try_acquire_shortcut(self):
        reg = RateLimiterRegistry(configs={
            "limited": BucketConfig(max_tokens=1, refill_rate=0.0, initial_tokens=1),
        })
        assert reg.try_acquire("limited") is True
        assert reg.try_acquire("limited") is False

    def test_get_all_stats(self):
        reg = RateLimiterRegistry()
        reg.get("tool_1")
        reg.get("tool_2")
        stats = reg.get_all_stats()
        assert "tool_1" in stats
        assert "tool_2" in stats

    def test_get_throttled_tools_empty(self):
        reg = RateLimiterRegistry()
        reg.get("healthy_tool")
        assert reg.get_throttled_tools() == []

    def test_get_throttled_tools_returns_depleted(self):
        reg = RateLimiterRegistry(configs={
            "slow_tool": BucketConfig(max_tokens=1, refill_rate=0.0, initial_tokens=1),
        })
        reg.try_acquire("slow_tool")
        assert "slow_tool" in reg.get_throttled_tools()

    def test_reset_all(self):
        reg = RateLimiterRegistry(configs={
            "t1": BucketConfig(max_tokens=1, refill_rate=0.0, initial_tokens=1),
        })
        reg.try_acquire("t1")
        assert reg.get_throttled_tools() == ["t1"]
        count = reg.reset_all()
        assert count == 1
        assert reg.get_throttled_tools() == []

    def test_unknown_tool_uses_default(self):
        reg = RateLimiterRegistry()
        bucket = reg.get("never_seen_before")
        assert bucket.config.max_tokens == 30


# ─────────────────────────────────────────────
# Thread-safety smoke test
# ─────────────────────────────────────────────

class TestThreadSafety:
    def test_circuit_breaker_concurrent_failures(self):
        """Simula falhas concorrentes sem deadlock ou crash."""
        cb = ToolCircuitBreaker("thread_tool", failure_threshold=50)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    cb.record_failure()
                    cb.allow_request()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == []
        assert cb.stats.failure_count == 400

    def test_token_bucket_concurrent_acquire(self):
        """Simula aquisições concorrentes sem deadlock ou crash."""
        bucket = TokenBucket("thread_bucket", BucketConfig(max_tokens=100, refill_rate=0.0, initial_tokens=100))
        results = []

        def worker():
            try:
                for _ in range(50):
                    results.append(bucket.try_acquire())
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if r is False)
        assert successes == 100  # max_tokens
        assert failures == 100   # 200 tentativas - 100 tokens

# Em tests/test_gate_isolation.py (novo)
from unittest import mock
from core.integration import pre_call_pipeline, PreCallResult


def test_rbac_exception_fails_closed():
    with mock.patch("core.integration.check_rbac", side_effect=RuntimeError("boom")), \
         mock.patch("core.integration.check_circuit_breaker", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_rate_limit", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_forbidden_topics", return_value=PreCallResult(True)):
        result = pre_call_pipeline("persona-devops", "some_tool", {}, "hello")
        assert result.allowed is False
        assert result.reason == "rbac_internal_error"


def test_cb_exception_fails_open():
    with mock.patch("core.integration.check_circuit_breaker", side_effect=RuntimeError("boom")), \
         mock.patch("core.integration.check_rate_limit", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_forbidden_topics", return_value=PreCallResult(True)):
        result = pre_call_pipeline(None, "some_tool", {}, "hello")
        assert result.allowed is True  # CB fail-open allows execution


def test_ft_exception_fails_closed():
    with mock.patch("core.integration.check_circuit_breaker", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_rate_limit", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_forbidden_topics", side_effect=RuntimeError("boom")):
        result = pre_call_pipeline(None, "some_tool", {}, "some text")
        assert result.allowed is False
        assert result.reason == "forbidden_topics_internal_error"


def test_pipeline_without_persona_skips_rbac_autonomy_input():
    with mock.patch("core.integration.check_circuit_breaker", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_rate_limit", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_forbidden_topics", return_value=PreCallResult(True)), \
         mock.patch("core.integration.check_rbac") as mock_rbac:
        result = pre_call_pipeline(None, "some_tool", {}, "hello")
        assert result.allowed is True
        mock_rbac.assert_not_called()

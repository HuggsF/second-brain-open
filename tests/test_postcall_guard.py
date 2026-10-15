# Em tests/test_postcall_guard.py (novo)
from unittest import mock
from core.integration import post_call_pipeline


def test_not_executed_skips_cb():
    with mock.patch("core.integration.record_tool_outcome") as mock_cb:
        post_call_pipeline("tool", success=False, identity="agent", trace_id="t1",
                          result={"error": "denied"}, executed=False)
        mock_cb.assert_not_called()


def test_executed_records_cb():
    with mock.patch("core.integration.record_tool_outcome") as mock_cb, \
         mock.patch("core.integration.audit_call"):
        post_call_pipeline("tool", success=True, identity="agent", trace_id="t1",
                          result={"ok": True}, executed=True)
        mock_cb.assert_called_once_with("tool", True)


def test_not_executed_audit_uses_blocked_prefix():
    with mock.patch("core.integration.audit_call") as mock_audit:
        post_call_pipeline("tool", success=False, identity="agent", trace_id="t1",
                          result={}, executed=False)
        call_args = mock_audit.call_args
        assert "broker.blocked.tool" in str(call_args)


def test_returns_result():
    with mock.patch("core.integration.record_tool_outcome"), \
         mock.patch("core.integration.audit_call"):
        r = post_call_pipeline("tool", success=True, identity="a", trace_id="t",
                              result={"data": 1}, executed=True)
        assert r == {"data": 1}

# Em tests/test_dlp_result.py (novo)
import json
from unittest import mock
from core.integration import post_call_pipeline


def test_dict_result_with_cpf_is_redacted():
    result = {"cpf": "123.456.789-00", "status": "ok"}
    with mock.patch("core.integration.record_tool_outcome"), \
         mock.patch("core.integration.audit_call"):
        r = post_call_pipeline("tool", success=True, identity="a", trace_id="t",
                              result=result, executed=True)
    assert "123.456.789-00" not in json.dumps(r)
    assert r["status"] == "ok"


def test_result_without_pii_unchanged():
    result = {"data": "hello world", "status": "ok"}
    with mock.patch("core.integration.record_tool_outcome"), \
         mock.patch("core.integration.audit_call"):
        r = post_call_pipeline("tool", success=True, identity="a", trace_id="t",
                              result=result, executed=True)
    assert r == {"data": "hello world", "status": "ok"}


def test_not_executed_skips_dlp():
    result = {"cpf": "123.456.789-00"}
    with mock.patch("core.integration.audit_call"):
        r = post_call_pipeline("tool", success=True, identity="a", trace_id="t",
                              result=result, executed=False)
    # DLP não roda quando não executada
    assert r["cpf"] == "123.456.789-00"


def test_string_result_with_pii_is_redacted():
    result_str = "O CPF do cliente é 123.456.789-00"
    from core.security.dlp_guardrail import inspect_text
    dlp_r = inspect_text(result_str)
    assert dlp_r.has_pii
    assert "123.456.789-00" not in dlp_r.redacted_text

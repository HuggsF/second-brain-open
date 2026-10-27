"""Testes de regressão para DD-02 (DLP fail-closed) e DD-03 (ImportError visível).

DD-02: Se o DLP scan falhar com exceção no post_call_pipeline,
       o resultado DEVE ser redactado (fail-closed, PD-OVR-004/INV-N12).

DD-03: Se core.integration não importar, o broker DEVE emitir
       'SECURITY DEGRADED' em stderr (nunca silencioso).
"""

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


class TestDLP_FailClosed(unittest.TestCase):
    """DD-02: DLP scan failure redacta o resultado (fail-closed)."""

    def test_dlp_exception_redacts_result(self):
        """Se inspect_text() levantar, resultado é limpo para prevenir PII leak."""
        from core.integration import post_call_pipeline, reset_all_singletons
        reset_all_singletons()

        original_result = {"data": "CPF 123.456.789-00", "tool": "get_info"}

        # Mock inspect_text para levantar exceção
        with mock.patch(
            "core.security.dlp_guardrail.inspect_text",
            side_effect=RuntimeError("DLP engine crashed"),
        ):
            returned = post_call_pipeline(
                tool_name="get_info",
                success=True,
                identity="agent:researcher",
                trace_id="t1",
                result=original_result,
                executed=True,
            )

        # Resultado deve ter sido redactado — NÃO deve conter PII
        self.assertNotIn("123.456.789-00", json.dumps(returned, default=str))
        self.assertEqual(returned.get("error"), "dlp_scan_failed")

    def test_dlp_exception_logs_error(self):
        """Exceção no DLP deve logar 'error:' em stderr, não 'warn:'."""
        from core.integration import post_call_pipeline, reset_all_singletons
        reset_all_singletons()

        captured = StringIO()
        with mock.patch(
            "core.security.dlp_guardrail.inspect_text",
            side_effect=RuntimeError("crash"),
        ), mock.patch("sys.stderr", captured):
            post_call_pipeline(
                tool_name="test_tool",
                success=True,
                identity="agent:test",
                trace_id="t2",
                result={"data": "test"},
                executed=True,
            )

        output = captured.getvalue()
        self.assertIn("error:", output.lower())
        self.assertIn("dlp", output.lower())

    def test_dlp_success_preserves_result(self):
        """DLP scan que funciona normalmente preserva o resultado."""
        from core.integration import post_call_pipeline, reset_all_singletons
        reset_all_singletons()

        result = {"answer": "Hello, world!", "tool": "greet"}

        returned = post_call_pipeline(
            tool_name="greet",
            success=True,
            identity="agent:researcher",
            trace_id="t3",
            result=result,
            executed=True,
        )

        # Resultado limpo deve ser preservado
        self.assertEqual(returned.get("answer"), "Hello, world!")

    def test_dlp_exception_redacts_string_result(self):
        """DD-02 edge case: resultado string (não dict) com DLP crash deve ser redactado."""
        from core.integration import post_call_pipeline, reset_all_singletons
        reset_all_singletons()

        string_result = "CPF do cliente: 123.456.789-00, email: teste@corp.com"

        with mock.patch(
            "core.security.dlp_guardrail.inspect_text",
            side_effect=RuntimeError("DLP engine crashed"),
        ):
            returned = post_call_pipeline(
                tool_name="lookup_client",
                success=True,
                identity="agent:researcher",
                trace_id="t-str",
                result=string_result,
                executed=True,
            )

        # Resultado string com PII NÃO deve vazar
        returned_str = json.dumps(returned, default=str)
        self.assertNotIn("123.456.789-00", returned_str)
        self.assertNotIn("teste@corp.com", returned_str)
        self.assertEqual(returned.get("error"), "dlp_scan_failed")


class TestImportError_Visible(unittest.TestCase):
    """DD-03: ImportError no broker emite SECURITY DEGRADED, nunca silencioso."""

    def test_pre_call_importerror_logs_security_degraded(self):
        """ImportError no pre_call deve logar SECURITY DEGRADED."""
        from core import broker
        from core.tools import IMPLEMENTATIONS

        async def fake_tool(**kw):
            return {"ok": True}

        captured = StringIO()
        trace = Path(tempfile.mktemp(suffix=".jsonl"))

        original_import = __import__

        def selective_import(name, *args, **kwargs):
            if name == "core.integration":
                raise ImportError("test: module unavailable")
            return original_import(name, *args, **kwargs)

        import asyncio
        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": fake_tool}), \
             mock.patch("sys.stderr", captured), \
             mock.patch("builtins.__import__", side_effect=selective_import):
            asyncio.run(broker.call(
                "agent:researcher", "get_adr", {"identifier": "A"},
                trace_path=trace,
            ))

        output = captured.getvalue()
        self.assertIn("SECURITY DEGRADED", output)

    def test_post_call_importerror_logs_security_degraded(self):
        """ImportError no post_call deve logar SECURITY DEGRADED."""
        from core import broker
        from core.tools import IMPLEMENTATIONS

        async def fake_tool(**kw):
            return {"ok": True}

        captured = StringIO()
        trace = Path(tempfile.mktemp(suffix=".jsonl"))

        # Usamos um approach mais direto: mock o import dentro do finally
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        call_count = {"pre": 0, "post": 0}

        def selective_import(name, *args, **kwargs):
            if name == "core.integration":
                call_count["pre"] += 1
                if call_count["pre"] == 1:
                    # Primeiro import (pre_call) — permite
                    return original_import(name, *args, **kwargs)
                # Segundo import (post_call) — falha
                raise ImportError("test: post_call unavailable")
            return original_import(name, *args, **kwargs)

        import asyncio
        with mock.patch.dict(IMPLEMENTATIONS, {"get_adr": fake_tool}), \
             mock.patch("sys.stderr", captured), \
             mock.patch("builtins.__import__", side_effect=selective_import):
            asyncio.run(broker.call(
                "agent:researcher", "get_adr", {"identifier": "A"},
                trace_path=trace,
            ))

        output = captured.getvalue()
        # Pelo menos um SECURITY DEGRADED deve aparecer
        self.assertIn("SECURITY DEGRADED", output)


if __name__ == "__main__":
    unittest.main()

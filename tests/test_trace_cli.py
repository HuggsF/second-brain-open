import tempfile
import unittest
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

import cli as cli_module
from core import tracing

TRACE_A = "a" * 32
TRACE_B = "b" * 32


def record(trace_id, span, tool, event="call", status="ok", parent=None, label=None, ms=None, args=None, ts="2026-10-09T12:00:00.000-03:00"):
    return {
        "schema_version": 1, "ts": ts, "trace_id": trace_id, "span_id": span, "parent_span_id": parent,
        "task_label": label, "server": "SRV-API Gateway", "tool": tool, "event": event, "status": status,
        "duration_ms": ms, "caller": "mcp", "args": args or {}, "error_type": None,
    }


class TestTraceCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / ".runtime" / "trace-log.jsonl"
        patcher = mock.patch.object(cli_module, "_trace_log_path", return_value=self.log)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = CliRunner()

    def seed(self):
        # Physical order as the middleware writes it: a child event lands before its call,
        # and a call's ts is its START, so sorting by ts restores parent-before-child.
        rows = [
            record(TRACE_A, "2" * 16, "srv_api_run_safe_command", event="ssh.exec", parent="1" * 16, ts="2026-10-09T12:00:00.002-03:00", args={"command": "ls /secret-path", "exit_code": 0}),
            record(TRACE_A, "1" * 16, "srv_api_run_safe_command", ms=42, label="DEM-12", ts="2026-10-09T12:00:00.001-03:00", args={"command": "ls /secret-path"}),
            record(TRACE_B, "3" * 16, "get_adr", ms=3, ts="2026-10-09T12:00:01.000-03:00", args={"adr_identifier": "ADR-003"}),
            record(TRACE_A, "4" * 16, "srv_api_view_logs", status="error", ms=7, ts="2026-10-09T12:00:02.000-03:00"),
        ]
        for row in rows:
            tracing.write_record(row, self.log)

    def test_trace_prints_chain_in_order(self):
        self.seed()
        result = self.runner.invoke(cli_module.cli, ["trace", TRACE_A])
        self.assertEqual(result.exit_code, 0, result.output)
        lines = [l for l in result.output.splitlines() if l.strip()]
        self.assertEqual(len(lines), 3)
        self.assertIn("DEM-12", lines[0])
        self.assertIn("srv_api_run_safe_command", lines[0])
        self.assertIn("ssh.exec", lines[1])
        self.assertIn("srv_api_view_logs", lines[2])
        self.assertIn("error", lines[2])
        self.assertNotIn("get_adr", result.output)

    def test_trace_unknown_id_exits_1(self):
        self.seed()
        result = self.runner.invoke(cli_module.cli, ["trace", "c" * 32])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Nenhum registo para " + "c" * 32, result.output)

    def test_trace_malformed_id_exits_1_without_traceback(self):
        result = self.runner.invoke(cli_module.cli, ["trace", "not-an-id"])
        self.assertEqual(result.exit_code, 1)
        self.assertNotIn("Traceback", result.output)
        self.assertIn("32", result.output)

    def test_trace_recent_lists_last_n(self):
        self.seed()
        result = self.runner.invoke(cli_module.cli, ["trace", "--recent", "2"])
        self.assertEqual(result.exit_code, 0, result.output)
        lines = [l for l in result.output.splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("get_adr", lines[0])
        self.assertIn("srv_api_view_logs", lines[1])

    def test_trace_without_arguments_defaults_to_recent_and_handles_empty_log(self):
        result = self.runner.invoke(cli_module.cli, ["trace"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("vazio", result.output.lower())

    def test_trace_output_contains_no_args_values(self):
        self.seed()
        for argv in (["trace", TRACE_A], ["trace", "--recent", "10"]):
            output = self.runner.invoke(cli_module.cli, argv).output
            self.assertNotIn("/secret-path", output)
            self.assertNotIn("ADR-003", output)

    def test_trace_rejects_id_together_with_recent(self):
        result = self.runner.invoke(cli_module.cli, ["trace", TRACE_A, "--recent", "3"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()

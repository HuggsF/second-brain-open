"""Fiação do orçamento (ADR-035) na CLI (`cli.py budget`, `_get_tracker`) e no servidor MCP
`local_tasks_mcp` (`get_budget_status`, `local_tasks_status`, ferramenta registrando custo).

Todos os caminhos (`settings.base_dir`, `events.EVENTS_LOG`, `tracing.TRACE_LOG`, banco do
orçamento) apontam para um diretório temporário; nada toca o `.runtime/` real. Os caches de
módulo (singleton do tracker) são zerados em cada teste.
"""
import asyncio
import dataclasses
import gc
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from config import settings
from core import events, tracing
from core.budget import BudgetConfig, BudgetTracker, FailedBudgetTracker
from core.cost import CostRecord
from core.local_tasks import profile as profile_module
from core.local_tasks import router
from tests.test_local_tasks import GOOD, FakeClient, _cloud_only_profile, _profile


def _with_budget(profile, daily=1.0, monthly=20.0):
    return dataclasses.replace(profile, budget=BudgetConfig(daily_usd=daily, monthly_usd=monthly))


def _cost(amount):
    return CostRecord(model="cloud-m", tier="cloud", tokens_in=1, tokens_out=1, ms=0,
                      paid_equivalent_usd=0.0, provider="cloud", actual_usd=amount)


class _TempRuntime(unittest.TestCase):
    """Base: diretório temporário como base_dir e logs de eventos/trace dentro dele."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(gc.collect)  # fecha conexões SQLite órfãs antes da limpeza (Windows)
        self.base = Path(self.tmp.name)
        self.runtime = self.base / ".runtime"
        self.events_log = self.runtime / "events.jsonl"
        self.db_path = self.runtime / "budget.db"
        for target, attr, value in (
            (settings, "base_dir", self.base),
            (events, "EVENTS_LOG", self.events_log),
            (tracing, "TRACE_LOG", self.base / "trace-log.jsonl"),
        ):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def use_profile(self, profile):
        """load_profile devolve `profile` no módulo de perfil e no router; devolve o mock do
        módulo de perfil (o que `cli._get_tracker` e o servidor MCP importam)."""
        mocks = []
        for target in (profile_module, router):
            patcher = mock.patch.object(target, "load_profile", return_value=profile)
            mocks.append(patcher.start())
            self.addCleanup(patcher.stop)
        return mocks[0]

    def tracker(self, config=None):
        self.runtime.mkdir(parents=True, exist_ok=True)
        t = BudgetTracker(self.db_path, config or BudgetConfig(daily_usd=1.0, monthly_usd=20.0))
        self.addCleanup(t.close)
        return t


class _CliBase(_TempRuntime):
    def setUp(self):
        super().setUp()
        import importlib
        import importlib.util

        import click
        from click.testing import CliRunner

        # cli.py importa scripts.sanitize no fim do módulo; se ele não existe neste checkout,
        # um stub (só durante o teste) deixa o grupo carregar. Só as entradas `cli` e
        # `scripts.sanitize` de sys.modules são restauradas (restaurar o dicionário inteiro
        # descarregaria numpy, que não recarrega no mesmo processo). O `cli` reimportado zera
        # os caches do tracker a cada teste.
        saved = {name: sys.modules.get(name) for name in ("cli", "scripts.sanitize")}

        def restore():
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        self.addCleanup(restore)
        sys.modules.pop("cli", None)
        try:
            real_sanitize = importlib.util.find_spec("scripts.sanitize") is not None
        except ImportError:
            real_sanitize = False
        if not real_sanitize:
            stub = types.ModuleType("scripts.sanitize")
            stub.sanitize_cmd = click.Command("sanitize", callback=lambda: None)
            sys.modules["scripts.sanitize"] = stub
        self.cli_module = importlib.import_module("cli")
        self.runner = CliRunner()

    def invoke(self, *args):
        return self.runner.invoke(self.cli_module.cli, ["budget", *args])


class CliBudgetCommandTests(_CliBase):
    def test_no_flags_prints_state_and_limits(self):
        self.use_profile(_with_budget(_profile(), daily=1.0, monthly=20.0))
        self.tracker().record(_cost(0.25), envelope_id="e1")
        result = self.invoke()
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Budget status: normal", result.output)
        self.assertIn("Daily:   US$ 0.25 / 1.00  (25%)  remaining: US$ 0.75", result.output)
        self.assertIn("Monthly: US$ 0.25 / 20.00  (1%)  remaining: US$ 19.75", result.output)

    def test_history_lists_n_days(self):
        self.use_profile(_with_budget(_profile()))
        self.tracker().record(_cost(0.25), envelope_id="e1")
        result = self.invoke("--history", "3")
        self.assertEqual(result.exit_code, 0, result.output)
        lines = [l for l in result.output.splitlines() if l.strip()]
        self.assertEqual(len(lines), 3, result.output)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(lines[-1].split(), [today, "US$", "0.2500"])
        self.assertTrue(all(l.endswith("US$ 0.0000") for l in lines[:-1]), result.output)

    def test_profile_without_budget_prints_message_and_exits_zero(self):
        """Comportamento atual fixado: mensagem, saída 0, nenhum banco criado."""
        self.use_profile(_profile())
        for args in ((), ("--history", "3"), ("--rebuild",)):
            result = self.invoke(*args)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(result.output.strip(), "Budget não configurado no perfil.")
        self.assertFalse(self.db_path.exists())

    def test_profile_load_failure_exits_one(self):
        with mock.patch.object(profile_module, "load_profile", side_effect=RuntimeError("boom")):
            result = self.invoke()
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Erro ao carregar o perfil", result.output)


def _result_line(envelope_id, ts, usd, *, kind="task.result"):
    record = {"kind": kind, "id": envelope_id, "task": "classify", "from": "router",
              "trace_id": f"t-{envelope_id}",
              "cost": {"provider": "cloud", "model": "cloud-m", "tier": "cloud",
                       "tokens_in": 10, "tokens_out": 5, "actual_usd": usd,
                       "paid_equivalent_usd": 0.0}}
    if ts is not None:
        record["ts"] = ts
    if envelope_id is None:
        del record["id"]
    return json.dumps(record)


class CliBudgetRebuildTests(_CliBase):
    def setUp(self):
        super().setUp()
        self.use_profile(_with_budget(_profile()))
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.now = datetime.now(timezone.utc)
        self.last_month = (self.now.replace(day=1) - timedelta(days=1)).isoformat()

    def write(self, name, lines):
        (self.runtime / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def rows(self):
        with sqlite3.connect(self.db_path) as conn:
            return dict(conn.execute("SELECT envelope_id, actual_usd FROM cost_log").fetchall())

    def test_rebuild_reads_rotated_and_current_files(self):
        self.write("events.2.jsonl", [_result_line("old", self.last_month, 0.5)])
        self.write("events.1.jsonl", [_result_line("mid", self.now.isoformat(), 0.25)])
        self.write("events.jsonl", [_result_line("new", self.now.isoformat(), 0.125),
                                    _result_line("req", self.now.isoformat(), 9.0, kind="task.request")])
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.rows(), {"old": 0.5, "mid": 0.25, "new": 0.125})
        self.assertIn("Reconstruído: 3 registros, ignoradas: 0, US$ 0.8750 acumulado.", result.output)

    def test_rebuild_skips_and_counts_invalid_lines(self):
        self.write("events.1.jsonl", [
            "{isto não é json",
            _result_line("sem-ts", None, 1.0),
            _result_line("ok-1", self.now.isoformat(), 0.25),
        ])
        self.write("events.jsonl", [
            _result_line(None, self.now.isoformat(), 2.0),        # sem envelope_id
            _result_line("ts-ruim", "não-é-data", 4.0),            # ts que não é ISO 8601
            _result_line("ok-2", self.last_month, 0.5),
            "",                                                    # linha vazia não conta
        ])
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.rows(), {"ok-1": 0.25, "ok-2": 0.5})
        self.assertIn("Reconstruído: 2 registros, ignoradas: 4, US$ 0.7500 acumulado.", result.output)

    def test_rebuild_skips_and_counts_non_numeric_costs(self):
        """actual_usd/paid_equivalent_usd em texto, NaN, inf ou bool: linha pulada e contada."""
        nan_line = _result_line("nan", self.now.isoformat(), 0.0).replace(
            '"actual_usd": 0.0', '"actual_usd": NaN')
        self.assertIn('"actual_usd": NaN', nan_line)
        inf_line = _result_line("inf", self.now.isoformat(), 0.0).replace(
            '"actual_usd": 0.0', '"actual_usd": Infinity')
        paid_text = json.loads(_result_line("paid-texto", self.now.isoformat(), 0.125))
        paid_text["cost"]["paid_equivalent_usd"] = "x"
        sem_valor = json.loads(_result_line("sem-valor", self.now.isoformat(), 0.0))
        del sem_valor["cost"]["actual_usd"]
        nulo = json.loads(_result_line("nulo", self.now.isoformat(), 0.0))
        nulo["cost"]["actual_usd"] = None
        self.write("events.jsonl", [
            _result_line("abc", self.now.isoformat(), "abc"),
            nan_line,
            inf_line,
            _result_line("bool", self.now.isoformat(), True),
            json.dumps(paid_text),
            json.dumps(sem_valor),   # ausente conta 0.0, como antes
            json.dumps(nulo),        # null conta 0.0, como antes
            _result_line("ok", self.now.isoformat(), 0.25),
        ])
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIsNone(result.exception, result.output)
        self.assertEqual(self.rows(), {"sem-valor": 0.0, "nulo": 0.0, "ok": 0.25})
        self.assertIn("Reconstruído: 3 registros, ignoradas: 5, US$ 0.2500 acumulado.", result.output)

    def test_rebuild_keeps_rows_missing_from_events(self):
        self.tracker().record(_cost(0.0625), envelope_id="so-no-banco")
        self.write("events.jsonl", [_result_line("ok", self.now.isoformat(), 0.25)])
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.rows(), {"so-no-banco": 0.0625, "ok": 0.25})

    def test_rebuild_without_events_files_reports_zero(self):
        result = self.invoke("--rebuild")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Reconstruído: 0 registros, ignoradas: 0, US$ 0.0000 acumulado.", result.output)


class CliGetTrackerTests(_CliBase):
    def test_open_failure_returns_failed_tracker_then_retries(self):
        self.use_profile(_with_budget(_profile()))
        import core.budget as budget_module
        real = budget_module.BudgetTracker
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise sqlite3.OperationalError("database is locked")
            tracker = real(*args, **kwargs)
            self.addCleanup(tracker.close)
            return tracker

        with mock.patch.object(budget_module, "BudgetTracker", side_effect=flaky):
            first = self.cli_module._get_tracker()
            second = self.cli_module._get_tracker()
            third = self.cli_module._get_tracker()
        self.assertIsInstance(first, FailedBudgetTracker)
        self.assertEqual(first.status().state, "exceeded")
        self.assertIsInstance(second, real)
        self.assertIs(third, second)
        self.assertEqual(len(calls), 2)
        self.assertEqual(Path(calls[1][0]), self.db_path)

    def test_profile_without_budget_caches_none(self):
        loader = self.use_profile(_profile())
        self.assertIsNone(self.cli_module._get_tracker())
        self.assertIsNone(self.cli_module._get_tracker())
        self.assertEqual(loader.call_count, 1)
        self.assertFalse(self.db_path.exists())


class _PricedFake(FakeClient):
    """Cliente falso que se apresenta como o provedor de nuvem com preço (como o FallbackClient)."""

    def __init__(self, spec, *answers):
        super().__init__(*answers, tokens_in=1000, tokens_out=500)
        self.spec = spec
        self.last_provider = None

    def chat(self, model, system, user, schema):
        done = super().chat(model, system, user, schema)
        self.last_provider = self.spec
        return done


class McpBudgetWiringTests(_TempRuntime):
    def setUp(self):
        super().setUp()
        from fastmcp import Client
        import mcp_servers.local_tasks_mcp as module
        self.Client = Client
        self.module = module
        for attr, value in (("_budget_tracker", None), ("_budget_tracker_no_config", False)):
            patcher = mock.patch.object(module, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self._close_tracker)

    def _close_tracker(self):
        tracker = self.module._budget_tracker
        if isinstance(tracker, BudgetTracker):
            tracker.close()

    def call(self, tool, args=None):
        async def run():
            async with self.Client(self.module.mcp) as client:
                return await client.call_tool(tool, args or {})
        return asyncio.run(run()).data

    def test_get_budget_status_with_budget(self):
        self.use_profile(_with_budget(_profile(), daily=1.0, monthly=20.0))
        out = self.call("get_budget_status")
        self.assertEqual(out["state"], "normal")
        self.assertEqual(out["daily_limit"], 1.0)
        self.assertEqual(out["monthly_limit"], 20.0)
        self.assertEqual(out["daily_spent"], 0.0)
        self.assertIsNone(out["limiting_period"])
        self.assertTrue(self.db_path.exists())

    def test_get_budget_status_without_budget(self):
        self.use_profile(_profile())
        self.assertEqual(self.call("get_budget_status"), {"state": "unconfigured"})
        self.assertFalse(self.db_path.exists())

    def test_local_tasks_status_includes_budget(self):
        self.use_profile(_with_budget(_profile(), daily=1.0, monthly=20.0))
        with mock.patch.object(router, "status", return_value={"profile": "t"}):
            out = self.call("local_tasks_status")
        self.assertEqual(out["profile"], "t")
        self.assertEqual(out["budget"]["state"], "normal")
        self.assertEqual(out["budget"]["daily_limit"], 1.0)
        self.assertEqual(out["budget"]["monthly_remaining"], 20.0)

    def test_local_tasks_status_without_budget_has_no_budget_key(self):
        self.use_profile(_profile())
        with mock.patch.object(router, "status", return_value={"profile": "t"}):
            out = self.call("local_tasks_status")
        self.assertNotIn("budget", out)

    def test_classify_records_cloud_cost_in_tracker(self):
        profile = _with_budget(_cloud_only_profile(), daily=1.0, monthly=20.0)
        cloud = profile.providers[0]
        self.assertTrue(cloud.price)  # Task 3: nuvem com orçamento exige preço
        self.use_profile(profile)
        fake = _PricedFake(cloud, GOOD)
        with mock.patch.dict("os.environ", {"CLOUD_KEY_TEST": "x"}), \
                mock.patch.object(router, "build_client", return_value=fake):
            env = self.call("classify", {"text": "algum texto"})
        self.assertEqual(env["status"], "ok", env)
        expected = (1000 * cloud.price["input"] + 500 * cloud.price["output"]) / 1e6
        self.assertGreater(expected, 0)
        self.assertAlmostEqual(env["cost"]["actual_usd"], expected)
        tracker = self.module._budget_tracker
        self.assertIsInstance(tracker, BudgetTracker)
        self.assertAlmostEqual(tracker.status().daily_spent, expected)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT envelope_id, tier, actual_usd FROM cost_log").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], env["id"])
        self.assertEqual(rows[0][1], "cloud")
        self.assertAlmostEqual(rows[0][2], expected)


if __name__ == "__main__":
    unittest.main()

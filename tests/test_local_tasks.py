import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from config import settings
from core.local_tasks.ollama_client import Completion, LocalModelError, OllamaClient
from core.local_tasks.profile import Profile, ProfileNotFound, load_profile


def _write(root: Path, name: str, text: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "profile.yaml").write_bytes(text.encode("utf-8"))


class ProfileTests(unittest.TestCase):
    def test_defaults_fill_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "mini", "name: mini\nlabels:\n  type: [a]\n")
            p = load_profile("mini", root=root)
        self.assertIsInstance(p, Profile)
        self.assertEqual(p.local_model, settings.chat_model)
        self.assertEqual(p.timeout_seconds, 30)
        self.assertEqual(p.max_input_tokens, 6000)
        self.assertEqual(p.retries, 1)
        self.assertEqual(p.paid_reference, {"model": "none", "input": 0.0, "output": 0.0})
        self.assertEqual(p.labels, {"type": ["a"]})

    def test_missing_labels_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "bad", "name: bad\n")
            with self.assertRaises(ValueError):
                load_profile("bad", root=root)

    def test_unknown_profile_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProfileNotFound):
                load_profile("nope", root=Path(tmp))

    def test_env_selects_profile(self):
        with mock.patch.dict(os.environ, {"BRAIN_PROFILE": "example"}):
            self.assertEqual(load_profile().name, "example")

    def test_rejects_path_traversal_name(self):
        with self.assertRaises(ProfileNotFound):
            load_profile("../x")


class OllamaClientTests(unittest.TestCase):
    def _client(self, handler):
        return OllamaClient(base_url="http://ollama.test", transport=httpx.MockTransport(handler))

    def test_chat_sends_schema_as_format_and_reads_counters(self):
        seen = {}

        def handler(request):
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "message": {"role": "assistant", "content": '{"a": 1}'},
                "prompt_eval_count": 11, "eval_count": 5, "total_duration": 2_500_000_000,
            })

        schema = {"type": "object"}
        out = self._client(handler).chat("m1", "sys", "usr", schema)
        self.assertEqual(out, Completion(text='{"a": 1}', tokens_in=11, tokens_out=5, ms=2500, model="m1"))
        self.assertEqual(seen["path"], "/api/chat")
        self.assertEqual(seen["body"], {
            "model": "m1",
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            "format": schema, "stream": False, "options": {"temperature": 0},
        })

    def test_missing_counters_default_to_zero(self):
        c = self._client(lambda r: httpx.Response(200, json={"message": {"content": "x"}}))
        out = c.chat("m", "s", "u", {})
        self.assertEqual((out.tokens_in, out.tokens_out, out.ms), (0, 0, 0))

    def test_connection_error_is_local_unavailable(self):
        def handler(request):
            raise httpx.ConnectError("boom")

        with self.assertRaises(LocalModelError) as cm:
            self._client(handler).chat("m", "s", "SECRET-USER-TEXT", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")
        self.assertNotIn("SECRET-USER-TEXT", str(cm.exception))

    def test_timeout_is_timeout(self):
        def handler(request):
            raise httpx.ReadTimeout("slow")

        with self.assertRaises(LocalModelError) as cm:
            self._client(handler).chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "timeout")

    def test_http_404_model_missing_is_local_unavailable(self):
        c = self._client(lambda r: httpx.Response(404, json={"error": "model not found"}))
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")

    def test_response_without_message_content_is_local_unavailable(self):
        c = self._client(lambda r: httpx.Response(200, json={"done": True}))
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")

    def test_available_reads_api_tags(self):
        def handler(request):
            self.assertEqual(request.url.path, "/api/tags")
            return httpx.Response(200, json={"models": [{"name": "a:latest"}, {"name": "b:3b"}]})

        c = self._client(handler)
        self.assertTrue(c.available("a"))
        self.assertTrue(c.available("b:3b"))
        self.assertFalse(c.available("b"))
        self.assertFalse(c.available("zzz"))

    def test_available_never_raises(self):
        def handler(request):
            raise httpx.ConnectError("down")

        self.assertFalse(self._client(handler).available("a"))
        self.assertFalse(self._client(lambda r: httpx.Response(500)).available("a"))


class FakeClient:
    def __init__(self, *answers, tokens_in=10, tokens_out=5):
        self.answers = list(answers)
        self.calls = 0
        self.users = []
        self.tokens = (tokens_in, tokens_out)

    def chat(self, model, system, user, schema):
        self.calls += 1
        self.users.append(user)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        text = a if isinstance(a, str) else json.dumps(a)
        return Completion(text=text, tokens_in=self.tokens[0], tokens_out=self.tokens[1], ms=7, model=model)


def _profile():
    return Profile(
        name="t", labels={"type": ["adr", "system"], "team": ["logistics", "platform"]},
        local_model="m", timeout_seconds=5, max_input_tokens=6000, retries=1,
        paid_reference={"model": "ref", "input": 1.0, "output": 2.0},
    )


GOOD = {"labels": {"type": "adr", "team": "logistics", "tags": ["a"]}, "confidence": 0.9}


class RouterTests(unittest.TestCase):
    def setUp(self):
        from core import events
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "events.jsonl"
        patcher = mock.patch.object(events, "EVENTS_LOG", self.log)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_task(self, task="classify", client=None, profile=None, **kw):
        from core.local_tasks import router
        kw.setdefault("text", "some text")
        return router.run_task(task, profile=profile or _profile(), client=client, **kw)

    def test_helpers(self):
        from core.local_tasks import router
        self.assertEqual(router.estimate_tokens("a" * 9), 3)
        self.assertEqual(router.parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(router.parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(router.parse_json('here: {"a": {"b": "}"}} ok'), {"a": {"b": "}"}})
        self.assertIsNone(router.parse_json("nothing"))
        self.assertIsNone(router.parse_json("[1]"))

    def test_classify_happy_path(self):
        env = self.run_task(client=FakeClient(GOOD))
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["payload"]["labels"]["type"], "adr")
        self.assertGreater(env["cost"]["tokens_in"], 0)
        self.assertEqual(env["cost"]["tier"], "local")
        self.assertAlmostEqual(env["cost"]["paid_equivalent_usd"], (10 * 1.0 + 5 * 2.0) / 1e6)

    def test_label_case_is_normalised_to_vocabulary(self):
        ans = {"labels": {"type": " ADR ", "team": "Logistics", "tags": ["X", "x", "y"]}, "confidence": 0.5}
        env = self.run_task(client=FakeClient(ans))
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["payload"]["labels"]["type"], "adr")
        self.assertEqual(env["payload"]["labels"]["team"], "logistics")
        self.assertEqual(env["payload"]["labels"]["tags"], ["x", "y"])

    def test_one_valid_label_is_kept_and_other_is_empty(self):
        ans = {"labels": {"type": "adr", "team": "nope", "tags": []}, "confidence": 0.5}
        env = self.run_task(client=FakeClient(ans))
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["payload"]["labels"]["type"], "adr")
        self.assertEqual(env["payload"]["labels"]["team"], "")

    def test_unknown_labels_are_dropped_and_none_left_escalates(self):
        ans = {"labels": {"type": "zzz", "team": "qqq", "tags": ["a"]}, "confidence": 0.5}
        env = self.run_task(client=FakeClient(ans))
        self.assertEqual(env["status"], "escalate")
        self.assertEqual(env["reason"], "no_valid_label")

    def test_extract_fenced_json_is_accepted(self):
        fenced = '```json\n{"date": "2026-01-01", "status": "accepted", "title": "T", "type": "adr"}\n```'
        env = self.run_task("extract", client=FakeClient(fenced), template="adr@1")
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["template"], "adr@1")
        self.assertEqual(env["payload"]["title"], "T")

    def test_invalid_then_valid_retries_once(self):
        fc = FakeClient({"nope": 1}, GOOD)
        env = self.run_task(client=fc)
        self.assertEqual(env["status"], "ok")
        self.assertEqual(fc.calls, 2)
        self.assertIn("A resposta anterior falhou na validação:", fc.users[1])
        self.assertEqual(env["cost"]["tokens_in"], 20)
        self.assertEqual(env["cost"]["tokens_out"], 10)
        self.assertEqual(env["cost"]["ms"], 14)

    def test_two_invalid_answers_escalate_schema_invalid(self):
        fc = FakeClient("not json", {"nope": 1}, GOOD)
        env = self.run_task(client=fc)
        self.assertEqual(env["status"], "escalate")
        self.assertEqual(env["reason"], "schema_invalid")
        self.assertEqual(fc.calls, 2)
        self.assertEqual(env["cost"]["tokens_in"], 20)

    def test_input_too_large_never_calls_model(self):
        fc = FakeClient(GOOD)
        env = self.run_task(client=fc, text="a" * 24001)
        self.assertEqual(env["status"], "escalate")
        self.assertEqual(env["reason"], "input_too_large")
        self.assertEqual(fc.calls, 0)
        self.assertEqual(env["cost"]["tier"], "deterministic")

    def test_unknown_template_and_task_are_invalid_without_model(self):
        fc = FakeClient(GOOD)
        for kw in ({"task": "extract", "template": "zzz@9"}, {"task": "extract"},
                   {"task": "extract", "template": "bad"}):
            env = self.run_task(client=fc, **kw)
            self.assertEqual((env["status"], env["reason"]), ("invalid", "unknown_template"))
            self.assertEqual(env["cost"]["tier"], "deterministic")
            self.assertEqual(env["cost"]["tokens_in"], 0)
        env = self.run_task("frobnicate", client=fc)
        self.assertEqual((env["status"], env["reason"]), ("invalid", "unknown_task"))
        self.assertEqual(fc.calls, 0)

    def test_profile_not_found_is_invalid(self):
        from core.local_tasks import router
        fc = FakeClient(GOOD)
        with mock.patch.object(router, "load_profile", side_effect=ProfileNotFound("x")):
            env = router.run_task("classify", text="t", client=fc)
        self.assertEqual((env["status"], env["reason"]), ("invalid", "profile_not_found"))
        self.assertEqual(fc.calls, 0)
        self.assertEqual(env["cost"]["model"], settings.chat_model)

    def test_local_unavailable_escalates(self):
        env = self.run_task(client=FakeClient(LocalModelError("local_unavailable")))
        self.assertEqual((env["status"], env["reason"]), ("escalate", "local_unavailable"))
        env = self.run_task(client=FakeClient(LocalModelError("timeout")))
        self.assertEqual((env["status"], env["reason"]), ("escalate", "timeout"))

    def test_unexpected_exception_is_error(self):
        env = self.run_task(client=FakeClient(RuntimeError("boom")))
        self.assertEqual(env["status"], "error")
        self.assertIsNone(env["reason"])

    def test_every_result_is_a_valid_envelope_and_two_events_are_recorded(self):
        from core.protocol.envelope import validate_envelope
        env = self.run_task(client=FakeClient(GOOD), trace_id="a" * 32)
        self.assertEqual(validate_envelope(env), [])
        self.assertEqual(env["kind"], "task.result")
        self.assertEqual(env["to"], "caller")
        self.assertEqual(env["trace_id"], "a" * 32)
        lines = [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([l["kind"] for l in lines], ["task.request", "task.result"])
        self.assertEqual(lines[1]["parent_id"], lines[0]["id"])
        self.assertEqual(lines[0]["trace_id"], lines[1]["trace_id"])
        self.assertNotIn("payload", lines[0])
        for task, kw in (("frobnicate", {}), ("classify", {"text": "a" * 24001})):
            self.assertEqual(validate_envelope(self.run_task(task, client=FakeClient(GOOD), **kw)), [])

    def test_trace_id_generated_when_missing(self):
        env = self.run_task(client=FakeClient(GOOD))
        self.assertRegex(env["trace_id"], r"^[0-9a-f]{32}$")


if __name__ == "__main__":
    unittest.main()

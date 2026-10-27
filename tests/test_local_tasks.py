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
        self.assertEqual(p.keep_alive, "30m")

    def test_keep_alive_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "warm", "name: warm\nlabels:\n  type: [a]\nkeep_alive: -1\n")
            self.assertEqual(load_profile("warm", root=root).keep_alive, -1)

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

    def test_keep_alive_is_sent_only_when_configured(self):
        bodies = []

        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"message": {"content": "{}"}})

        OllamaClient(base_url="http://ollama.test", transport=httpx.MockTransport(handler), keep_alive="30m").chat("m", "s", "u", {})
        self._client(handler).chat("m", "s", "u", {})
        self.assertEqual(bodies[0]["keep_alive"], "30m")
        self.assertNotIn("keep_alive", bodies[1])

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

    def test_default_client_keeps_the_model_loaded_per_profile(self):
        from core.local_tasks import router
        from core.local_tasks import providers
        with mock.patch.object(providers, "OllamaClient", return_value=FakeClient(GOOD)) as cls:
            env = self.run_task(profile=_profile())
        self.assertEqual(env["status"], "ok")
        self.assertEqual(cls.call_args.kwargs.get("keep_alive"), _profile().keep_alive)
        self.assertEqual(cls.call_args.kwargs.get("timeout"), _profile().timeout_seconds)

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

    def test_unknown_task_keeps_requested_name(self):
        from core.protocol.envelope import validate_envelope
        fc = FakeClient(GOOD)
        env = self.run_task("translate", client=fc)
        self.assertEqual((env["task"], env["status"], env["reason"]), ("translate", "invalid", "unknown_task"))
        self.assertEqual(validate_envelope(env), [])
        self.assertEqual(fc.calls, 0)
        env = self.run_task("Weird Name!", client=fc)
        self.assertEqual(env["task"], "weird_name_")
        self.assertEqual(self.run_task("!!", client=fc)["task"], "unknown")

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

    def test_all_return_paths_are_valid_envelopes(self):
        from core.local_tasks import router
        from core.protocol.envelope import validate_envelope
        adr = {"date": "2026-01-01", "status": "accepted", "title": "T", "type": "adr"}
        nolabel = {"labels": {"type": "zzz", "team": "qqq", "tags": []}, "confidence": 0.5}
        cases = [
            ("ok", None, dict(client=FakeClient(GOOD))),
            ("ok", None, dict(task="extract", template="adr@1", client=FakeClient(adr))),
            ("escalate", "schema_invalid", dict(client=FakeClient("x", "y"))),
            ("escalate", "no_valid_label", dict(client=FakeClient(nolabel))),
            ("escalate", "local_unavailable", dict(client=FakeClient(LocalModelError("local_unavailable")))),
            ("escalate", "input_too_large", dict(client=FakeClient(GOOD), text="a" * 24001)),
            ("error", None, dict(client=FakeClient(RuntimeError("boom")))),
            ("invalid", "unknown_template", dict(task="extract", client=FakeClient(GOOD))),
            ("invalid", "unknown_task", dict(task="frobnicate", client=FakeClient(GOOD))),
        ]
        for status, reason, kw in cases:
            env = self.run_task(**kw)
            self.assertEqual((env["status"], env["reason"]), (status, reason))
            self.assertEqual(validate_envelope(env), [], (status, reason))
        with mock.patch.object(router, "load_profile", side_effect=ProfileNotFound("x")):
            env = router.run_task("classify", text="t", client=FakeClient(GOOD))
        self.assertEqual((env["status"], env["reason"]), ("invalid", "profile_not_found"))
        self.assertEqual(validate_envelope(env), [])

    def test_malformed_profile_is_error_result_with_both_events(self):
        from core.local_tasks import router
        from core.protocol.envelope import validate_envelope
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "bad", "name: bad\n")
            with mock.patch.object(router, "load_profile",
                                   side_effect=lambda: load_profile("bad", root=Path(tmp))):
                env = router.run_task("classify", text="t", client=FakeClient(GOOD))
        self.assertEqual((env["status"], env["reason"]), ("error", None))
        self.assertEqual(env["cost"]["tier"], "deterministic")
        self.assertEqual(env["cost"]["model"], settings.chat_model)
        self.assertEqual(validate_envelope(env), [])
        lines = [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([l["kind"] for l in lines], ["task.request", "task.result"])

    def test_trace_id_generated_when_missing(self):
        env = self.run_task(client=FakeClient(GOOD))
        self.assertRegex(env["trace_id"], r"^[0-9a-f]{32}$")




def _profile_small(max_tokens=10):
    p = _profile()
    return Profile(name=p.name, labels=p.labels, local_model=p.local_model,
                   timeout_seconds=p.timeout_seconds, max_input_tokens=max_tokens,
                   retries=p.retries, paid_reference=p.paid_reference)


SUMMARY = {"summary": "s", "key_points": ["k"]}


class SummarizeTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_summarize_small_input_single_call(self):
        fc = FakeClient(SUMMARY)
        env = self.run_task("summarize", client=fc, target_words=50)
        self.assertEqual((env["status"], fc.calls), ("ok", 1))
        self.assertEqual(env["payload"], SUMMARY)
        from core.local_tasks import tasks
        system, _ = tasks.prompt("summarize", "t", _profile(), tasks.output_schema("summarize", None), 50)
        self.assertIn("50 words", system)
        self.assertEqual(env["cost"]["tier"], "local")

    def test_summarize_large_input_map_reduce_calls_blocks_plus_one(self):
        text = "\n\n".join(["a" * 30, "b" * 30, "c" * 30])
        fc = FakeClient({"summary": "s1", "key_points": []}, {"summary": "s2", "key_points": []},
                        {"summary": "s3", "key_points": []}, {"summary": "final", "key_points": ["k"]})
        env = self.run_task("summarize", client=fc, text=text, profile=_profile_small())
        self.assertEqual((env["status"], fc.calls), ("ok", 4))
        self.assertEqual(env["payload"]["summary"], "final")
        self.assertEqual((env["cost"]["tokens_in"], env["cost"]["tokens_out"]), (40, 20))
        self.assertIn("s1", fc.users[3])
        self.assertIn("s3", fc.users[3])

    def test_summarize_reduce_too_large_escalates(self):
        text = "\n\n".join(["a" * 30, "b" * 30, "c" * 30])
        big = {"summary": "x" * 30, "key_points": []}
        fc = FakeClient(big, big, big)
        env = self.run_task("summarize", client=fc, text=text, profile=_profile_small())
        self.assertEqual((env["status"], env["reason"]), ("escalate", "input_too_large"))

    def test_summarize_block_escalation_propagates(self):
        text = "\n\n".join(["a" * 30, "b" * 30])
        fc = FakeClient({"summary": "s1", "key_points": []}, LocalModelError("timeout"))
        env = self.run_task("summarize", client=fc, text=text, profile=_profile_small())
        self.assertEqual((env["status"], env["reason"]), ("escalate", "timeout"))
        self.assertEqual(env["cost"]["tokens_in"], 10)

    def test_split_blocks_never_exceeds_limit(self):
        from core.local_tasks import tasks
        text = "\n\n".join(["p" * 25, "word " * 30 + "\n" + "line two " * 5, "z" * 100, "short"])
        for limit in (10, 40, 64):
            blocks = tasks.split_blocks(text, limit)
            self.assertTrue(blocks)
            self.assertTrue(all(0 < len(b) <= limit for b in blocks), limit)
            self.assertEqual("".join(blocks).replace("\n", "").replace(" ", ""),
                             text.replace("\n", "").replace(" ", ""))
        self.assertEqual(tasks.split_blocks("a\n\nb", 100), ["a\n\nb"])


ADR_MD = ("---\r\ntype: adr\r\nstatus: accepted\r\ndate: 2026-10-13\r\n---\r\n\r\n"
          "# Use local tasks\r\n\r\nBody text.\r\n")


class ValidateTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_validate_markdown_crlf_bom_frontmatter(self):
        doc = b"\xef\xbb\xbf" + ADR_MD.encode("utf-8")
        fc = FakeClient()
        env = self.run_task("validate", client=fc, text=doc.decode("utf-8"), template="adr@1")
        self.assertEqual(env["status"], "ok", env)
        self.assertEqual(env["payload"], {"valid": True, "missing": [], "errors": [], "review": []})
        self.assertEqual((fc.calls, env["cost"]["tier"]), (0, "deterministic"))

    def test_validate_reports_missing_keys(self):
        doc = "---\ntype: adr\nstatus: accepted\n---\n# T\n"
        env = self.run_task("validate", client=FakeClient(), text=doc, template="adr@1")
        self.assertEqual(env["status"], "ok")
        self.assertFalse(env["payload"]["valid"])
        self.assertEqual(env["payload"]["missing"], ["date"])

    def test_validate_missing_title_and_wrong_type(self):
        from core.local_tasks import tasks
        out = tasks.validate_document("---\ntype: adr\nstatus: 3\ndate: 2026-10-13\n---\nno heading\n", "adr@1")
        self.assertEqual(out["missing"], ["title"])
        self.assertEqual(len(out["errors"]), 1)
        self.assertIn("status", out["errors"][0])

    def test_validate_no_frontmatter_is_invalid_not_exception(self):
        from core.local_tasks import tasks
        out = tasks.validate_document("# Just a title\n", "adr@1")
        self.assertFalse(out["valid"])
        self.assertTrue(out["errors"])

    def test_validate_accepts_dict(self):
        from core.local_tasks import tasks
        out = tasks.validate_document({"type": "adr", "status": "x", "date": "d", "title": "t"}, "adr@1")
        self.assertTrue(out["valid"])

    def test_validate_unknown_template_is_invalid_status(self):
        env = self.run_task("validate", client=FakeClient(), text=ADR_MD, template="nope@1")
        self.assertEqual((env["status"], env["reason"]), ("invalid", "unknown_template"))

    def test_validate_with_source_calls_model_once_and_returns_review(self):
        fc = FakeClient({"review": ["status contradicts source"]})
        env = self.run_task("validate", client=fc, text=ADR_MD, template="adr@1", source="the source")
        self.assertEqual((env["status"], fc.calls), ("ok", 1))
        self.assertEqual(env["payload"]["review"], ["status contradicts source"])
        self.assertTrue(env["payload"]["valid"])
        self.assertEqual(env["cost"]["tier"], "local")
        self.assertIn("the source", fc.users[0])


class ValidateJsonTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_extract_payload_passes_to_validate_as_json_text(self):
        adr = {"date": "2026-01-01", "status": "accepted", "title": "T", "type": "adr"}
        extracted = self.run_task("extract", template="adr@1", client=FakeClient(adr))
        self.assertEqual(extracted["status"], "ok")
        text = "\ufeff  " + json.dumps(extracted["payload"]) + "\n"
        env = self.run_task("validate", client=FakeClient(), text=text, template="adr@1")
        self.assertEqual(env["status"], "ok", env)
        self.assertEqual(env["payload"], {"valid": True, "missing": [], "errors": [], "review": []})

    def test_json_object_with_missing_keys_is_reported(self):
        from core.local_tasks import tasks
        out = tasks.validate_document('{"type": "adr", "status": "x"}', "adr@1")
        self.assertEqual(out["missing"], ["date", "title"])

    def test_text_starting_with_brace_but_not_object_falls_back_to_markdown(self):
        from core.local_tasks import tasks
        for text in ("{not json", "[1]", '{"a": 1} trailing'):
            out = tasks.validate_document(text, "adr@1")
            self.assertFalse(out["valid"])
            self.assertIn("documento sem frontmatter YAML", out["errors"])


class NestedRequiredTests(unittest.TestCase):
    def test_nested_required_is_an_error_not_silently_valid(self):
        from core.local_tasks import tasks
        doc = {"labels": {"team": "x", "tags": []}, "confidence": 0.5}
        out = tasks.validate_document(doc, "classification@1")
        self.assertFalse(out["valid"])
        self.assertEqual(out["missing"], [])
        self.assertEqual(len(out["errors"]), 1)
        self.assertTrue(out["errors"][0].startswith("labels: "), out["errors"])
        self.assertIn("'type'", out["errors"][0])

    def test_root_required_goes_to_missing_only(self):
        from core.local_tasks import tasks
        out = tasks.validate_document({"confidence": 0.5}, "classification@1")
        self.assertEqual((out["missing"], out["errors"]), (["labels"], []))


class EmptySourceTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_empty_source_does_not_call_the_model(self):
        fc = FakeClient()
        env = self.run_task("validate", client=fc, text=ADR_MD, template="adr@1", source="")
        self.assertEqual((env["status"], fc.calls, env["cost"]["tier"]), ("ok", 0, "deterministic"))
        self.assertTrue(env["payload"]["valid"])


class PaidReferenceTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_prices_are_normalised_to_float(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "p", "labels:\n  type: [a]\npaid_reference:\n  model: r\n  input: '0.5'\n")
            p = load_profile("p", root=Path(tmp))
        self.assertEqual(p.paid_reference, {"model": "r", "input": 0.5, "output": 0.0})

    def test_null_or_non_numeric_price_is_value_error(self):
        for price in ("null", "abc", "[1]", "true"):
            with tempfile.TemporaryDirectory() as tmp:
                _write(Path(tmp), "p", f"labels:\n  type: [a]\npaid_reference:\n  input: {price}\n")
                with self.assertRaises(ValueError, msg=price):
                    load_profile("p", root=Path(tmp))

    def test_malformed_price_in_profile_object_still_returns_envelope(self):
        from core.protocol.envelope import validate_envelope
        p = _profile()
        bad = Profile(name=p.name, labels=p.labels, local_model=p.local_model,
                      timeout_seconds=p.timeout_seconds, max_input_tokens=p.max_input_tokens,
                      retries=p.retries, paid_reference={"model": "r", "input": None, "output": "x"})
        env = self.run_task(client=FakeClient(GOOD), profile=bad)
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["cost"]["paid_equivalent_usd"], 0.0)
        self.assertEqual(validate_envelope(env), [])

    def test_router_turns_bad_price_profile_into_error(self):
        from core.local_tasks import router
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "p", "labels:\n  type: [a]\npaid_reference:\n  input: null\n")
            with mock.patch.object(router, "load_profile",
                                   side_effect=lambda: load_profile("p", root=Path(tmp))):
                env = router.run_task("classify", text="t", client=FakeClient(GOOD))
        self.assertEqual((env["status"], env["reason"]), ("error", None))


class ClockClient(FakeClient):
    """Cada chamada avança o relógio falso em `step` segundos."""

    def __init__(self, clock, step, *answers):
        super().__init__(*answers)
        self.clock, self.step = clock, step

    def chat(self, model, system, user, schema):
        self.clock[0] += self.step
        return super().chat(model, system, user, schema)


class LimitsTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_max_blocks_default_and_from_yaml(self):
        self.assertEqual(_profile().max_blocks, 4)
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "p", "labels:\n  type: [a]\nmax_blocks: 2\n")
            self.assertEqual(load_profile("p", root=Path(tmp)).max_blocks, 2)
            _write(Path(tmp), "q", "labels:\n  type: [a]\n")
            self.assertEqual(load_profile("q", root=Path(tmp)).max_blocks, 4)

    def test_summarize_above_max_blocks_escalates_without_calls(self):
        text = "\n\n".join(c * 30 for c in "abcde")
        fc = FakeClient()
        env = self.run_task("summarize", client=fc, text=text, profile=_profile_small())
        self.assertEqual((env["status"], env["reason"], fc.calls), ("escalate", "input_too_large", 0))
        self.assertEqual(env["cost"]["tier"], "deterministic")

    def test_total_deadline_escalates_timeout_with_spent_cost(self):
        from core.local_tasks import router
        clock = [0.0]
        # timeout 5 s x (1 + 1 retry) x 2 = prazo de 20 s; cada chamada leva 15 s.
        fc = ClockClient(clock, 15, {"summary": "s1", "key_points": []},
                         {"summary": "s2", "key_points": []}, {"summary": "s3", "key_points": []})
        text = "\n\n".join(c * 30 for c in "abc")
        with mock.patch.object(router, "_clock", lambda: clock[0]):
            env = self.run_task("summarize", client=fc, text=text, profile=_profile_small())
        self.assertEqual((env["status"], env["reason"]), ("escalate", "timeout"))
        self.assertEqual(fc.calls, 2)
        self.assertEqual((env["cost"]["tier"], env["cost"]["tokens_in"]), ("local", 20))

    def test_deadline_also_bounds_retries(self):
        from core.local_tasks import router
        clock = [0.0]
        fc = ClockClient(clock, 25, "nao json", GOOD)
        with mock.patch.object(router, "_clock", lambda: clock[0]):
            env = self.run_task(client=fc)
        self.assertEqual((env["status"], env["reason"], fc.calls), ("escalate", "timeout", 1))
        self.assertEqual(env["cost"]["tokens_in"], 10)

    def test_within_deadline_is_unchanged(self):
        from core.local_tasks import router
        clock = [0.0]
        fc = ClockClient(clock, 1, GOOD)
        with mock.patch.object(router, "_clock", lambda: clock[0]):
            env = self.run_task(client=fc)
        self.assertEqual(env["status"], "ok")


class StatusTests(unittest.TestCase):
    def setUp(self):
        from core import events
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(events, "EVENTS_LOG", Path(self.tmp.name) / "events.jsonl")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_keys_and_values(self):
        from core.local_tasks import router
        client = mock.Mock()
        client.available.return_value = True
        out = router.status(profile=_profile(), client=client)
        self.assertEqual(set(out), {"profile", "local_model", "model_available",
                                    "event_write_failures", "templates", "providers"})
        self.assertEqual(out["providers"], [])
        self.assertEqual(out["profile"], "t")
        self.assertEqual(out["local_model"], "m")
        self.assertTrue(out["model_available"])
        self.assertIsInstance(out["event_write_failures"], int)
        self.assertIsInstance(out["templates"], list)
        client.available.assert_called_once_with("m")

    def test_status_probes_with_short_timeout_not_the_profile_one(self):
        from core.local_tasks import router
        fake = mock.Mock()
        fake.available.return_value = True
        with mock.patch.object(router, "OllamaClient", return_value=fake) as cls:
            out = router.status(profile=_profile())
        cls.assert_called_once_with(timeout=5)
        self.assertEqual(router.STATUS_TIMEOUT_SECONDS, 5)
        self.assertTrue(out["model_available"])

    def test_status_never_raises_when_profile_is_missing(self):
        from core.local_tasks import router
        with mock.patch.object(router, "load_profile", side_effect=ProfileNotFound("x")):
            out = router.status(client=mock.Mock())
        self.assertIsNone(out["profile"])
        self.assertFalse(out["model_available"])
        self.assertEqual(out["local_model"], settings.chat_model)


class _CloudFakeClient:
    """FallbackClient falso para testes de router com providers."""

    def __init__(self, *answers, tokens_in=10, tokens_out=5, ms=100, spec=None):
        self.answers = list(answers)
        self.calls = 0
        self.tokens = (tokens_in, tokens_out)
        self.ms = ms
        self._spec = spec
        self.last_provider = spec

    def chat(self, model, system, user, schema):
        self.calls += 1
        a = self.answers.pop(0) if self.answers else "{}"
        if isinstance(a, Exception):
            raise a
        text = a if isinstance(a, str) else json.dumps(a)
        self.last_provider = self._spec
        return Completion(text=text, tokens_in=self.tokens[0], tokens_out=self.tokens[1],
                          ms=self.ms, model=model)


def _profile_with_providers():
    from core.local_tasks.providers import ProviderSpec
    return Profile(
        name="t", labels={"type": ["adr", "system"], "team": ["logistics", "platform"]},
        local_model="m", timeout_seconds=5, max_input_tokens=6000, retries=1,
        paid_reference={"model": "ref", "input": 1.0, "output": 2.0},
        providers=(
            ProviderSpec(kind="openai_compatible", name="cloud", model="cloud-m",
                         base_url="https://api.test/v1", timeout_seconds=20,
                         price={"input": 0.5, "output": 1.0}),
            ProviderSpec(kind="ollama", name="local", model="m",
                         base_url="http://localhost:11434", timeout_seconds=120),
        ),
    )


class ProvidersRouterTests(unittest.TestCase):
    setUp = RouterTests.setUp
    run_task = RouterTests.run_task

    def test_cloud_answer_fills_tier_provider_actual_usd(self):
        from core.local_tasks.providers import ProviderSpec
        cloud_spec = ProviderSpec(kind="openai_compatible", name="cloud", model="cloud-m",
                                  base_url="https://api.test/v1",
                                  price={"input": 0.5, "output": 1.0})
        fc = _CloudFakeClient(GOOD, spec=cloud_spec)
        profile = _profile_with_providers()
        env = self.run_task(client=fc, profile=profile)
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["cost"]["tier"], "cloud")
        self.assertEqual(env["cost"]["provider"], "cloud")
        self.assertEqual(env["cost"]["model"], "cloud-m")
        expected_usd = (10 * 0.5 + 5 * 1.0) / 1e6
        self.assertAlmostEqual(env["cost"]["actual_usd"], expected_usd)

    def test_fallback_to_local_marks_tier_local(self):
        from core.local_tasks.providers import ProviderSpec
        local_spec = ProviderSpec(kind="ollama", name="local", model="m",
                                  base_url="http://localhost:11434")
        fc = _CloudFakeClient(GOOD, spec=local_spec)
        profile = _profile_with_providers()
        env = self.run_task(client=fc, profile=profile)
        self.assertEqual(env["cost"]["tier"], "local")
        self.assertEqual(env["cost"]["provider"], "local")

    def test_profile_without_providers_unchanged(self):
        """Regressão: perfil sem providers = tier local, model == local_model."""
        env = self.run_task(client=FakeClient(GOOD))
        self.assertEqual(env["status"], "ok")
        self.assertEqual(env["cost"]["tier"], "local")
        self.assertEqual(env["cost"]["model"], "m")
        self.assertNotIn("provider", env["cost"])
        self.assertNotIn("actual_usd", env["cost"])

    def test_envelope_accepts_cloud_provider_actual_usd_and_rejects_unknown_tier(self):
        from core.protocol.envelope import validate_envelope
        from core.local_tasks.providers import ProviderSpec
        cloud_spec = ProviderSpec(kind="openai_compatible", name="cloud", model="cloud-m",
                                  base_url="https://api.test/v1",
                                  price={"input": 0.5, "output": 1.0})
        fc = _CloudFakeClient(GOOD, spec=cloud_spec)
        env = self.run_task(client=fc, profile=_profile_with_providers())
        self.assertEqual(validate_envelope(env), [])
        # Unknown tier should fail
        env["cost"]["tier"] = "unknown"
        errors = validate_envelope(env)
        self.assertTrue(any("tier" in e for e in errors))

    def test_deadline_uses_max_provider_timeout(self):
        from core.local_tasks import router
        profile = _profile_with_providers()
        # max timeout = 120 (from ollama provider), (1 + 1) * 2 = 480
        self.assertEqual(router.deadline_seconds(profile), 120 * (1 + 1) * 2)

    def _fallback(self, *entries):
        from core.local_tasks.providers import FallbackClient
        return FallbackClient(list(entries))

    def _specs(self):
        p = _profile_with_providers()
        return p.providers[0], p.providers[1]

    def test_retry_after_cloud_invalid_json_sums_tokens_and_reports_last_provider(self):
        cloud, local = self._specs()
        # 1a tentativa: a nuvem responde texto que não é JSON; 2a: a nuvem cai e o local responde.
        cloud_client = FakeClient("isto não é json", LocalModelError("local_unavailable"),
                                  tokens_in=100, tokens_out=50)
        local_client = FakeClient(GOOD, tokens_in=7, tokens_out=3)
        fb = self._fallback((cloud, cloud_client), (local, local_client))
        env = self.run_task(client=fb, profile=_profile_with_providers())
        self.assertEqual(env["status"], "ok")
        self.assertEqual(cloud_client.calls, 2)
        self.assertEqual(local_client.calls, 1)
        self.assertEqual(env["cost"]["tokens_in"], 107)
        self.assertEqual(env["cost"]["tokens_out"], 53)
        self.assertEqual(env["cost"]["tier"], "local")
        self.assertEqual(env["cost"]["provider"], "local")
        self.assertEqual(env["cost"]["model"], "m")

    def test_actual_usd_sums_price_of_each_responder(self):
        cloud, local = self._specs()  # nuvem: 0.5/1.0 por 1M; local: 0/0
        cloud_client = FakeClient("isto não é json", LocalModelError("local_unavailable"),
                                  tokens_in=100, tokens_out=50)
        local_client = FakeClient(GOOD, tokens_in=7, tokens_out=3)
        fb = self._fallback((cloud, cloud_client), (local, local_client))
        env = self.run_task(client=fb, profile=_profile_with_providers())
        self.assertAlmostEqual(env["cost"]["actual_usd"], (100 * 0.5 + 50 * 1.0) / 1e6)

    def test_reused_fallback_client_does_not_leak_last_provider(self):
        cloud, local = self._specs()
        cloud_client = FakeClient(GOOD, LocalModelError("local_unavailable"))
        local_client = FakeClient(LocalModelError("local_unavailable"))
        fb = self._fallback((cloud, cloud_client), (local, local_client))
        first = self.run_task(client=fb, profile=_profile_with_providers())
        self.assertEqual(first["cost"]["tier"], "cloud")
        second = self.run_task(client=fb, profile=_profile_with_providers())
        self.assertEqual(second["status"], "escalate")
        self.assertEqual(second["reason"], "local_unavailable")
        self.assertNotEqual(second["cost"]["tier"], "cloud")
        self.assertNotIn("provider", second["cost"])
        self.assertNotIn("actual_usd", second["cost"])

    def test_latency_counts_failed_attempts(self):
        from core.local_tasks import providers
        cloud, local = self._specs()
        clock = [0.0]

        class SlowFail:
            def chat(self, model, system, user, schema):
                clock[0] += 3.0
                raise LocalModelError("timeout", "ReadTimeout")

        fb = self._fallback((cloud, SlowFail()), (local, FakeClient(GOOD)))
        with mock.patch.object(providers, "_clock", lambda: clock[0]):
            env = self.run_task(client=fb, profile=_profile_with_providers())
        self.assertEqual(env["cost"]["tier"], "local")
        self.assertGreaterEqual(env["cost"]["ms"], 3000)

    def test_latency_kept_when_every_provider_fails(self):
        from core.local_tasks import providers
        cloud, local = self._specs()
        clock = [0.0]

        class SlowFail:
            def chat(self, model, system, user, schema):
                clock[0] += 1.5
                raise LocalModelError("timeout", "ReadTimeout")

        fb = self._fallback((cloud, SlowFail()), (local, SlowFail()))
        with mock.patch.object(providers, "_clock", lambda: clock[0]):
            env = self.run_task(client=fb, profile=_profile_with_providers())
        self.assertEqual(env["status"], "escalate")
        self.assertEqual(env["cost"]["ms"], 3000)


class ProvidersStatusTests(unittest.TestCase):
    setUp = StatusTests.setUp

    def _with_key(self, value):
        from core.local_tasks.providers import ProviderSpec
        p = _profile_with_providers()
        cloud = ProviderSpec(kind="openai_compatible", name="cloud", model="cloud-m",
                             base_url="https://api.test/v1", api_key_env="STATUS_TEST_KEY")
        env = {"STATUS_TEST_KEY": value} if value is not None else {}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        if value is None:
            os.environ.pop("STATUS_TEST_KEY", None)
        return Profile(name=p.name, labels=p.labels, local_model=p.local_model,
                       timeout_seconds=p.timeout_seconds, max_input_tokens=p.max_input_tokens,
                       retries=p.retries, paid_reference=p.paid_reference,
                       providers=(cloud, p.providers[1]))

    def _status(self, profile, cloud_up, local_up):
        from core.local_tasks import providers, router
        cloud = mock.Mock()
        cloud.available.return_value = cloud_up
        local = mock.Mock()
        local.available.return_value = local_up
        with mock.patch.object(providers, "OpenAICompatClient", return_value=cloud) as oa, \
                mock.patch.object(providers, "OllamaClient", return_value=local) as ol:
            out = router.status(profile=profile)
        return out, oa, ol

    def test_model_available_needs_configured_and_available(self):
        out, _, _ = self._status(self._with_key(None), cloud_up=True, local_up=False)
        self.assertEqual(out["providers"][0]["configured"], False)
        self.assertEqual(out["providers"][0]["available"], True)
        self.assertFalse(out["model_available"])

    def test_model_available_with_key_and_cloud_up(self):
        out, _, _ = self._status(self._with_key("sk-SENTINELA-123"), cloud_up=True, local_up=False)
        self.assertTrue(out["model_available"])
        self.assertNotIn("sk-SENTINELA-123", json.dumps(out))

    def test_model_available_by_local_reserve(self):
        out, _, _ = self._status(self._with_key(""), cloud_up=True, local_up=True)
        self.assertFalse(out["providers"][0]["configured"])
        self.assertTrue(out["model_available"])

    def test_status_lists_providers_without_blocking(self):
        import threading
        import time
        from core.local_tasks import providers, router
        release = threading.Event()
        self.addCleanup(release.set)

        class Raises:
            def available(self, *a):
                raise RuntimeError("boom")

        class Slow:
            def available(self, *a):
                release.wait(10)  # sonda que não volta dentro do prazo
                return True

        self.assertEqual(router.STATUS_TIMEOUT_SECONDS, 5)
        profile = self._with_key("sk-SENTINELA-123")
        with mock.patch.object(providers, "OpenAICompatClient", return_value=Raises()) as oa, \
                mock.patch.object(providers, "OllamaClient", return_value=Slow()) as ol, \
                mock.patch.object(router, "STATUS_TIMEOUT_SECONDS", 0.2):
            started = time.monotonic()
            out = router.status(profile=profile)
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.5)
        self.assertEqual([p["name"] for p in out["providers"]], ["cloud", "local"])
        self.assertEqual([p["available"] for p in out["providers"]], [False, False])
        self.assertFalse(out["model_available"])
        # Cada sonda usa o timeout curto do status, nunca o do perfil.
        self.assertEqual(oa.call_args.kwargs["timeout"], 0.2)
        self.assertEqual(ol.call_args.kwargs["timeout"], 0.2)

    def test_status_probe_uses_five_second_timeout(self):
        out, oa, ol = self._status(self._with_key("x"), cloud_up=True, local_up=True)
        self.assertEqual(oa.call_args.kwargs["timeout"], 5)
        self.assertEqual(ol.call_args.kwargs["timeout"], 5)


if __name__ == "__main__":
    unittest.main()

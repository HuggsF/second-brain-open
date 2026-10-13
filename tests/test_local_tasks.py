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


if __name__ == "__main__":
    unittest.main()

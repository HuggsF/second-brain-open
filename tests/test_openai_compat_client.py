"""Testes para core/local_tasks/openai_compat_client — cliente OpenAI-compativel."""
import json
import os
import time
import unittest
from unittest import mock

import httpx

from core.local_tasks.ollama_client import Completion, LocalModelError


def _handler_200(body_json):
    """Handler factory: responde 200 com o corpo dado."""
    def handler(request):
        return httpx.Response(200, json=body_json)
    return handler


def _ok_response(content="{}"):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


class OpenAICompatClientTests(unittest.TestCase):
    def _client(self, handler, **kw):
        from core.local_tasks.openai_compat_client import OpenAICompatClient
        return OpenAICompatClient(
            base_url="https://api.test/v1",
            transport=httpx.MockTransport(handler),
            **kw,
        )

    def test_body_json_schema(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            seen["headers"] = dict(request.headers)
            return httpx.Response(200, json=_ok_response('{"a": 1}'))

        schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
        c = self._client(handler, structured="json_schema")
        out = c.chat("model-1", "system prompt", "user text", schema)
        body = seen["body"]
        self.assertEqual(body["model"], "model-1")
        self.assertEqual(body["messages"], [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user text"},
        ])
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["name"], "output")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(body["response_format"]["json_schema"]["schema"], schema)
        self.assertEqual(out.text, '{"a": 1}')
        self.assertEqual(out.tokens_in, 10)
        self.assertEqual(out.tokens_out, 5)
        self.assertEqual(out.model, "model-1")
        self.assertGreaterEqual(out.ms, 0)

    def test_body_json_object_and_none(self):
        bodies = []

        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json=_ok_response())

        self._client(handler, structured="json_object").chat("m", "s", "u", {})
        self._client(handler, structured="none").chat("m", "s", "u", {})
        self.assertEqual(bodies[0]["response_format"], {"type": "json_object"})
        self.assertNotIn("response_format", bodies[1])

    def test_extra_merged_but_cannot_override_model_or_messages(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_ok_response())

        extra = {"provider": {"data_collection": "deny"}, "model": "HACKED", "messages": []}
        c = self._client(handler, extra=extra)
        c.chat("real-model", "s", "u", {})
        body = seen["body"]
        self.assertEqual(body["model"], "real-model")
        self.assertEqual(len(body["messages"]), 2)
        self.assertEqual(body["provider"], {"data_collection": "deny"})

    def test_bearer_from_env_and_absent_without_env(self):
        headers_seen = []

        def handler(request):
            headers_seen.append(dict(request.headers))
            return httpx.Response(200, json=_ok_response())

        # With key in env
        with mock.patch.dict(os.environ, {"TEST_KEY": "sk-SENTINELA-123"}):
            self._client(handler, api_key_env="TEST_KEY").chat("m", "s", "u", {})
        self.assertEqual(headers_seen[0].get("authorization"), "Bearer sk-SENTINELA-123")

        # Without key in env
        self._client(handler).chat("m", "s", "u", {})
        self.assertNotIn("authorization", headers_seen[1])

    def test_error_mapping(self):
        from core.local_tasks.openai_compat_client import OpenAICompatClient
        cases = [
            (401, "local_unavailable"),
            (403, "local_unavailable"),
            (404, "local_unavailable"),
            (429, "local_unavailable"),
            (500, "local_unavailable"),
        ]
        for status_code, reason in cases:
            c = self._client(lambda r, sc=status_code: httpx.Response(sc))
            with self.assertRaises(LocalModelError) as cm:
                c.chat("m", "s", "u", {})
            self.assertEqual(cm.exception.reason, reason, f"HTTP {status_code}")

        # Timeout
        def timeout_handler(r):
            raise httpx.ReadTimeout("slow")
        c = self._client(timeout_handler)
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "timeout")

        # ConnectError
        def connect_handler(r):
            raise httpx.ConnectError("refused")
        c = self._client(connect_handler)
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")

    def test_content_null_with_refusal_is_unavailable(self):
        body = {"choices": [{"message": {"content": None, "refusal": "I cannot do this"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        c = self._client(_handler_200(body))
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")

    def test_missing_usage_counts_zero(self):
        body = {"choices": [{"message": {"content": "{}"}}]}
        c = self._client(_handler_200(body))
        out = c.chat("m", "s", "u", {})
        self.assertEqual(out.tokens_in, 0)
        self.assertEqual(out.tokens_out, 0)

    def test_key_never_in_error_text(self):
        with mock.patch.dict(os.environ, {"TEST_KEY": "sk-SENTINELA-123"}):
            c = self._client(lambda r: httpx.Response(401), api_key_env="TEST_KEY")
            with self.assertRaises(LocalModelError) as cm:
                c.chat("m", "s", "u", {})
            self.assertNotIn("sk-SENTINELA-123", str(cm.exception))

        # Also in timeout
        def timeout_handler(r):
            raise httpx.ReadTimeout("slow")
        with mock.patch.dict(os.environ, {"TEST_KEY": "sk-SENTINELA-123"}):
            c = self._client(timeout_handler, api_key_env="TEST_KEY")
            with self.assertRaises(LocalModelError) as cm:
                c.chat("m", "s", "u", {})
            self.assertNotIn("sk-SENTINELA-123", str(cm.exception))

    def test_available_true_false_never_raises(self):
        def ok_handler(request):
            return httpx.Response(200, json={"data": [{"id": "model-1"}]})
        c = self._client(ok_handler)
        self.assertTrue(c.available())

        c = self._client(lambda r: httpx.Response(500))
        self.assertFalse(c.available())

        def err_handler(r):
            raise httpx.ConnectError("down")
        c = self._client(err_handler)
        self.assertFalse(c.available())

    def test_content_not_string_is_unavailable(self):
        body = {"choices": [{"message": {"content": 42}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        c = self._client(_handler_200(body))
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")

    def test_missing_choices_is_unavailable(self):
        c = self._client(_handler_200({"usage": {"prompt_tokens": 1}}))
        with self.assertRaises(LocalModelError) as cm:
            c.chat("m", "s", "u", {})
        self.assertEqual(cm.exception.reason, "local_unavailable")


if __name__ == "__main__":
    unittest.main()

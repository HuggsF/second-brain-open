"""Testes para core/local_tasks/openai_compat_client — cliente OpenAI-compativel."""
import json
import math
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

    def test_missing_usage_estimates_tokens_from_text(self):
        system, user, text = "s" * 10, "u" * 11, "t" * 9
        body = {"choices": [{"message": {"content": text}}]}
        out = self._client(_handler_200(body)).chat("m", system, user, {})
        self.assertEqual(out.tokens_in, math.ceil(len(system + user) / 4))  # 6
        self.assertEqual(out.tokens_out, math.ceil(len(text) / 4))          # 3
        self.assertEqual((out.tokens_in, out.tokens_out), (6, 3))

    def test_missing_usage_estimate_has_minimum_one(self):
        body = {"choices": [{"message": {"content": ""}}]}
        out = self._client(_handler_200(body)).chat("m", "", "", {})
        self.assertEqual((out.tokens_in, out.tokens_out), (1, 1))

    def test_partial_usage_estimates_only_missing_field(self):
        system, user, text = "abcd", "efgh", "x" * 13
        body = {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 50}}
        out = self._client(_handler_200(body)).chat("m", system, user, {})
        self.assertEqual((out.tokens_in, out.tokens_out), (50, 4))
        body = {"choices": [{"message": {"content": text}}], "usage": {"completion_tokens": 7}}
        out = self._client(_handler_200(body)).chat("m", system, user, {})
        self.assertEqual((out.tokens_in, out.tokens_out), (2, 7))

    def test_present_usage_is_used_unchanged(self):
        body = {"choices": [{"message": {"content": "x" * 400}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 0}}
        out = self._client(_handler_200(body)).chat("m", "s" * 400, "u", {})
        self.assertEqual((out.tokens_in, out.tokens_out), (3, 0))

    def test_malformed_usage_is_estimated_without_raising(self):
        system, user, text = "s" * 8, "u" * 8, "{}"
        for usage in ("abc", [1, 2], 7,
                      {"prompt_tokens": "x", "completion_tokens": None},
                      {"prompt_tokens": [1], "completion_tokens": {"a": 1}},
                      {"prompt_tokens": True, "completion_tokens": float("nan")},
                      {"prompt_tokens": -3, "completion_tokens": float("inf")}):
            raw = json.dumps({"choices": [{"message": {"content": text}}], "usage": usage})
            out = self._client(lambda r, raw=raw: httpx.Response(200, content=raw)).chat(
                "m", system, user, {})
            self.assertEqual((out.tokens_in, out.tokens_out), (4, 1), usage)
        body = {"choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 12.0, "completion_tokens": 3}}
        out = self._client(_handler_200(body)).chat("m", "s", "u", {})
        self.assertEqual((out.tokens_in, out.tokens_out), (12, 3))

    def test_available_uses_the_given_timeout(self):
        from core.local_tasks.openai_compat_client import OpenAICompatClient
        seen = {}

        def handler(request):
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, json={"data": []})

        c = OpenAICompatClient(base_url="https://api.test/v1", timeout=3,
                               transport=httpx.MockTransport(handler))
        self.assertTrue(c.available())
        self.assertEqual(seen["timeout"], {"connect": 3, "read": 3, "write": 3, "pool": 3})

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

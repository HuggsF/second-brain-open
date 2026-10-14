"""Testes para core/local_tasks/providers — cadeia de provedores."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import settings
from core.local_tasks.ollama_client import Completion, LocalModelError
from core.local_tasks.profile import load_profile

from tests.test_local_tasks import _write


class ProviderSpecTests(unittest.TestCase):
    """Task 1: parse de providers no perfil e ProviderSpec."""

    def test_defaults_per_kind_ollama(self):
        from core.local_tasks.providers import parse_providers
        raw = [{"kind": "ollama", "model": "llama3.2:3b"}]
        specs = parse_providers("t", raw, {"timeout_seconds": 30, "keep_alive": "30m"})
        self.assertEqual(len(specs), 1)
        s = specs[0]
        self.assertEqual(s.kind, "ollama")
        self.assertEqual(s.name, "ollama")
        self.assertEqual(s.model, "llama3.2:3b")
        self.assertEqual(s.base_url, settings.ollama_url)
        self.assertIsNone(s.api_key_env)
        self.assertEqual(s.timeout_seconds, 30)
        self.assertEqual(s.keep_alive, "30m")
        self.assertEqual(s.structured, "json_schema")
        self.assertEqual(s.extra, {})
        self.assertEqual(s.price, {"input": 0.0, "output": 0.0})

    def test_defaults_per_kind_openai_compatible(self):
        from core.local_tasks.providers import parse_providers
        raw = [{"kind": "openai_compatible", "model": "m1", "base_url": "https://api.test/v1"}]
        specs = parse_providers("t", raw, {"timeout_seconds": 20, "keep_alive": "30m"})
        s = specs[0]
        self.assertEqual(s.kind, "openai_compatible")
        self.assertEqual(s.name, "openai_compatible")
        self.assertEqual(s.model, "m1")
        self.assertEqual(s.base_url, "https://api.test/v1")
        self.assertIsNone(s.api_key_env)
        self.assertEqual(s.timeout_seconds, 20)
        self.assertEqual(s.structured, "json_schema")
        self.assertEqual(s.extra, {})

    def test_rejects_bad_items(self):
        from core.local_tasks.providers import parse_providers
        defaults = {"timeout_seconds": 30, "keep_alive": "30m"}
        # not a list
        with self.assertRaises(ValueError):
            parse_providers("t", "bad", defaults)
        # item not a dict
        with self.assertRaises(ValueError):
            parse_providers("t", ["bad"], defaults)
        # unknown kind
        with self.assertRaises(ValueError):
            parse_providers("t", [{"kind": "magic", "model": "m"}], defaults)
        # model missing
        with self.assertRaises(ValueError):
            parse_providers("t", [{"kind": "ollama"}], defaults)
        # openai_compatible without base_url
        with self.assertRaises(ValueError):
            parse_providers("t", [{"kind": "openai_compatible", "model": "m"}], defaults)
        # structured invalid
        with self.assertRaises(ValueError):
            parse_providers("t", [{"kind": "ollama", "model": "m", "structured": "bad"}], defaults)
        # price not numeric
        with self.assertRaises(ValueError):
            parse_providers("t", [{"kind": "ollama", "model": "m", "price": {"input": "abc"}}], defaults)

    def test_profile_without_providers_is_empty_tuple(self):
        from core.local_tasks.profile import Profile
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "mini", "labels:\n  type: [a]\n")
            p = load_profile("mini", root=Path(tmp))
        self.assertEqual(p.providers, ())

    def test_kiosk_profile_still_loads(self):
        p = load_profile("kiosk")
        self.assertEqual(p.name, "kiosk")
        self.assertIsInstance(p.providers, tuple)

    def test_profile_with_providers_parses(self):
        yaml_text = (
            "labels:\n  type: [a]\ntimeout_seconds: 60\n"
            "providers:\n"
            "  - kind: openai_compatible\n"
            "    model: m1\n"
            "    base_url: https://api.test/v1\n"
            "    api_key_env: MY_KEY\n"
            "    timeout_seconds: 20\n"
            "    structured: json_object\n"
            "    extra:\n"
            "      provider: {data_collection: deny}\n"
            "    price: {input: 0.5, output: 1.0}\n"
            "  - kind: ollama\n"
            "    model: llama3.2:3b\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "prov", yaml_text)
            p = load_profile("prov", root=Path(tmp))
        self.assertEqual(len(p.providers), 2)
        self.assertEqual(p.providers[0].kind, "openai_compatible")
        self.assertEqual(p.providers[0].model, "m1")
        self.assertEqual(p.providers[0].api_key_env, "MY_KEY")
        self.assertEqual(p.providers[0].timeout_seconds, 20)
        self.assertEqual(p.providers[0].structured, "json_object")
        self.assertEqual(p.providers[0].extra, {"provider": {"data_collection": "deny"}})
        self.assertEqual(p.providers[0].price, {"input": 0.5, "output": 1.0})
        self.assertEqual(p.providers[1].kind, "ollama")
        self.assertEqual(p.providers[1].timeout_seconds, 60)

    def test_env_file_honours_BRAIN_ENV_FILE(self):
        import importlib
        import config as config_mod
        original_env = os.environ.get("BRAIN_ENV_FILE")
        original_settings = config_mod.settings

        def restore():
            # tearDown: ambiente original, config recarregado e o mesmo objeto settings que os
            # outros módulos já importaram.
            if original_env is None:
                os.environ.pop("BRAIN_ENV_FILE", None)
            else:
                os.environ["BRAIN_ENV_FILE"] = original_env
            importlib.reload(config_mod)
            config_mod.settings = original_settings

        self.addCleanup(restore)
        with tempfile.TemporaryDirectory() as tmp:
            fake_env = Path(tmp) / ".env"
            fake_env.write_text("DUMMY=1", encoding="utf-8")
            with mock.patch.dict(os.environ, {"BRAIN_ENV_FILE": str(fake_env)}):
                importlib.reload(config_mod)
                self.assertEqual(config_mod.settings.env_file, fake_env)


class _FakeClient:
    """Cliente falso para FallbackClient tests."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def chat(self, model, system, user, schema):
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return Completion(text=a, tokens_in=10, tokens_out=5, ms=7, model=model)


class FallbackTests(unittest.TestCase):
    """Task 3: FallbackClient, build_client, deadline_timeout."""

    def test_skips_cloud_without_key_and_with_empty_key(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        cloud_spec = ProviderSpec(kind="openai_compatible", name="cloud", model="m1",
                                  base_url="https://api.test/v1", api_key_env="NONEXISTENT_KEY_XYZ")
        cloud_client = _FakeClient("{}")
        local_spec = ProviderSpec(kind="ollama", name="local", model="m2",
                                  base_url="http://localhost:11434")
        local_client = _FakeClient("{}")
        fb = FallbackClient([(cloud_spec, cloud_client), (local_spec, local_client)])
        # Key not in env: cloud should be skipped
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXISTENT_KEY_XYZ", None)
            fb.chat("ignored", "s", "u", {})
        self.assertEqual(cloud_client.calls, 0)
        self.assertEqual(local_client.calls, 1)

        # Key empty: cloud should be skipped
        cloud_client2 = _FakeClient("{}")
        local_client2 = _FakeClient("{}")
        fb2 = FallbackClient([(cloud_spec, cloud_client2), (local_spec, local_client2)])
        with mock.patch.dict(os.environ, {"NONEXISTENT_KEY_XYZ": ""}):
            fb2.chat("ignored", "s", "u", {})
        self.assertEqual(cloud_client2.calls, 0)
        self.assertEqual(local_client2.calls, 1)

    def test_falls_back_on_unavailable_and_timeout(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec1 = ProviderSpec(kind="openai_compatible", name="cloud", model="m1",
                             base_url="https://api.test/v1")
        spec2 = ProviderSpec(kind="openai_compatible", name="cloud2", model="m2",
                             base_url="https://api2.test/v1")
        spec3 = ProviderSpec(kind="ollama", name="local", model="m3",
                             base_url="http://localhost:11434")
        c1 = _FakeClient(LocalModelError("local_unavailable"))
        c2 = _FakeClient(LocalModelError("timeout", "ReadTimeout"))
        c3 = _FakeClient("{}")
        fb = FallbackClient([(spec1, c1), (spec2, c2), (spec3, c3)])
        out = fb.chat("ignored", "s", "u", {})
        self.assertEqual((c1.calls, c2.calls, c3.calls), (1, 1, 1))
        self.assertEqual(out.model, "m3")
        self.assertEqual(fb.last_provider.name, "local")

    def test_latency_includes_failed_attempts(self):
        from core.local_tasks import providers
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec1 = ProviderSpec(kind="openai_compatible", name="cloud", model="m1",
                             base_url="https://api.test/v1")
        spec2 = ProviderSpec(kind="ollama", name="local", model="m2",
                             base_url="http://localhost:11434")
        clock = [0.0]

        class SlowFail:
            calls = 0

            def chat(self, model, system, user, schema):
                clock[0] += 2.5  # a nuvem gastou 2,5 s antes de falhar
                raise LocalModelError("timeout", "ReadTimeout")

        c2 = _FakeClient("{}")  # responde com ms=7
        fb = FallbackClient([(spec1, SlowFail()), (spec2, c2)])
        with mock.patch.object(providers, "_clock", lambda: clock[0]):
            out = fb.chat("ignored", "s", "u", {})
        self.assertEqual(out.ms, 2500 + 7)

    def test_all_fail_error_carries_elapsed_ms(self):
        from core.local_tasks import providers
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec = ProviderSpec(kind="ollama", name="local", model="m2", base_url="http://x")
        clock = [0.0]

        class SlowFail:
            def chat(self, model, system, user, schema):
                clock[0] += 1.2
                raise LocalModelError("timeout", "ReadTimeout")

        fb = FallbackClient([(spec, SlowFail())])
        with mock.patch.object(providers, "_clock", lambda: clock[0]):
            with self.assertRaises(LocalModelError) as cm:
                fb.chat("ignored", "s", "u", {})
        self.assertEqual(cm.exception.ms, 1200)

    def test_last_provider_reset_when_every_provider_fails(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec = ProviderSpec(kind="openai_compatible", name="cloud", model="m1",
                            base_url="https://api.test/v1")
        c = _FakeClient("{}", LocalModelError("local_unavailable"))
        fb = FallbackClient([(spec, c)])
        fb.chat("ignored", "s", "u", {})
        self.assertEqual(fb.last_provider.name, "cloud")
        with self.assertRaises(LocalModelError):
            fb.chat("ignored", "s", "u", {})
        self.assertIsNone(fb.last_provider)

    def test_all_fail_raises_last(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec1 = ProviderSpec(kind="openai_compatible", name="a", model="m",
                             base_url="https://api.test/v1")
        spec2 = ProviderSpec(kind="ollama", name="b", model="m2",
                             base_url="http://localhost:11434")
        last_error = LocalModelError("timeout", "slow")
        c1 = _FakeClient(LocalModelError("local_unavailable"))
        c2 = _FakeClient(last_error)
        fb = FallbackClient([(spec1, c1), (spec2, c2)])
        with self.assertRaises(LocalModelError) as cm:
            fb.chat("ignored", "s", "u", {})
        self.assertEqual(cm.exception.reason, "timeout")

    def test_last_provider_tracks_responder(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec1 = ProviderSpec(kind="openai_compatible", name="cloud", model="m1",
                             base_url="https://api.test/v1")
        spec2 = ProviderSpec(kind="ollama", name="local", model="m2",
                             base_url="http://localhost:11434")
        c1 = _FakeClient(LocalModelError("local_unavailable"))
        c2 = _FakeClient("{}")
        fb = FallbackClient([(spec1, c1), (spec2, c2)])
        fb.chat("ignored", "s", "u", {})
        self.assertEqual(fb.last_provider.name, "local")

    def test_uses_spec_model_not_argument(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec = ProviderSpec(kind="ollama", name="local", model="real-model",
                            base_url="http://localhost:11434")
        c = _FakeClient("{}")
        fb = FallbackClient([(spec, c)])
        out = fb.chat("IGNORED", "s", "u", {})
        self.assertEqual(out.model, "real-model")

    def test_build_client_without_providers_is_ollama_client(self):
        from core.local_tasks.providers import build_client
        from core.local_tasks.ollama_client import OllamaClient
        p = load_profile("example")
        client = build_client(p)
        self.assertIsInstance(client, OllamaClient)
        self.assertEqual(client.timeout, p.timeout_seconds)
        self.assertEqual(client.keep_alive, p.keep_alive)

    def test_build_client_with_providers_order(self):
        from core.local_tasks.providers import FallbackClient, build_client
        yaml_text = (
            "labels:\n  type: [a]\ntimeout_seconds: 60\n"
            "providers:\n"
            "  - kind: openai_compatible\n"
            "    model: m1\n"
            "    base_url: https://api.test/v1\n"
            "    api_key_env: MY_KEY\n"
            "  - kind: ollama\n"
            "    model: llama3.2:3b\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "dual", yaml_text)
            p = load_profile("dual", root=Path(tmp))
        client = build_client(p)
        self.assertIsInstance(client, FallbackClient)
        self.assertEqual(len(client.entries), 2)
        self.assertEqual(client.entries[0][0].kind, "openai_compatible")
        self.assertEqual(client.entries[1][0].kind, "ollama")

    def test_deadline_timeout_max(self):
        from core.local_tasks.providers import deadline_timeout
        yaml_text = (
            "labels:\n  type: [a]\ntimeout_seconds: 30\n"
            "providers:\n"
            "  - kind: openai_compatible\n"
            "    model: m1\n"
            "    base_url: https://api.test/v1\n"
            "    timeout_seconds: 20\n"
            "  - kind: ollama\n"
            "    model: m2\n"
            "    timeout_seconds: 120\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "dt", yaml_text)
            p = load_profile("dt", root=Path(tmp))
        self.assertEqual(deadline_timeout(p), 120)

    def test_deadline_timeout_no_providers(self):
        from core.local_tasks.providers import deadline_timeout
        p = load_profile("example")
        self.assertEqual(deadline_timeout(p), p.timeout_seconds)

    def test_no_entry_usable_raises_local_unavailable(self):
        from core.local_tasks.providers import FallbackClient, ProviderSpec
        spec = ProviderSpec(kind="openai_compatible", name="cloud", model="m1",
                            base_url="https://api.test/v1", api_key_env="NONEXISTENT_KEY_ZZZ")
        c = _FakeClient("{}")
        fb = FallbackClient([(spec, c)])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXISTENT_KEY_ZZZ", None)
            with self.assertRaises(LocalModelError) as cm:
                fb.chat("ignored", "s", "u", {})
            self.assertEqual(cm.exception.reason, "local_unavailable")
        self.assertEqual(c.calls, 0)


if __name__ == "__main__":
    unittest.main()

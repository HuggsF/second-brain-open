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
        with tempfile.TemporaryDirectory() as tmp:
            fake_env = Path(tmp) / ".env"
            fake_env.write_text("DUMMY=1\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"BRAIN_ENV_FILE": str(fake_env)}):
                importlib.reload(config_mod)
                self.assertEqual(config_mod.settings.env_file, fake_env)
        # restore
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BRAIN_ENV_FILE", None)
            importlib.reload(config_mod)


if __name__ == "__main__":
    unittest.main()

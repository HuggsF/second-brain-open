"""Testes do envelope brain.task/1 e do registro de schemas de template."""
import unittest

from config import settings
from core.protocol import envelope, registry


def frontmatter_keys(path):
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    assert lines[0].strip() == "---", path
    keys = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t":
            continue
        keys.append(line.split(":", 1)[0].strip())
    return keys


class TestEnvelope(unittest.TestCase):
    def test_request_roundtrip_is_valid(self):
        env = envelope.make_envelope("task.request", "classify", sender="cli", to="local", payload={"text": "x"})
        self.assertEqual((env["protocol"], env["from"]), ("brain.task/1", "cli"))
        self.assertEqual(envelope.validate_envelope(env), [])

    def test_every_kind_is_valid(self):
        cost = {"model": "m", "tier": "local", "tokens_in": 1, "tokens_out": 2, "ms": 3, "paid_equivalent_usd": 0.0}
        for kind, to in (("task.request", "local"), ("task.result", "caller"), ("task.event", "caller")):
            env = envelope.make_envelope(kind, "extract", sender="x", to=to, payload={}, template="adr@1",
                                         trace_id="a" * 32, parent_id="p", status="ok", cost=cost)
            self.assertEqual(envelope.validate_envelope(env), [], kind)

    def test_rejects_unknown_reason_kind_and_task(self):
        for bad in ({"reason": "because"}, {"kind": "task.other"}, {"task": "translate"}):
            env = {**envelope.make_envelope("task.result", "classify", sender="cli", to="caller", payload={}, status="escalate", reason="timeout"), **bad}
            self.assertNotEqual(envelope.validate_envelope(env), [], bad)

    def test_reasons_are_the_eight_codes(self):
        self.assertEqual(len(envelope.REASONS), 8)
        self.assertEqual(envelope.TASKS, ("classify", "extract", "summarize", "validate"))


class TestRegistry(unittest.TestCase):
    def test_registry_loads_by_ref_and_rejects_unknown(self):
        self.assertIn("adr@1", registry.available())
        with self.assertRaises(registry.UnknownTemplate):
            registry.load_schema("adr@9")
        with self.assertRaises(registry.UnknownTemplate):
            registry.load_schema("../adr@1")

    def test_each_template_schema_requires_the_vault_template_frontmatter_keys(self):
        for name in ("adr", "system", "daily", "playbook", "rule", "demand"):
            keys = frontmatter_keys(settings.vault_dir / "_templates" / f"{name}.md")
            self.assertTrue(set(keys) <= set(registry.load_schema(f"{name}@1")["required"]), name)

    def test_output_schemas_validate(self):
        ok = {"labels": {"type": "adr", "team": "t", "tags": []}, "confidence": 0.5}
        self.assertEqual(registry.validate("classification@1", ok), [])
        self.assertNotEqual(registry.validate("classification@1", {**ok, "extra": 1}), [])
        self.assertNotEqual(registry.validate("classification@1", {**ok, "confidence": 2}), [])
        self.assertEqual(registry.validate("summary@1", {"summary": "s", "key_points": ["a"]}), [])
        self.assertNotEqual(registry.validate("summary@1", {"summary": "s"}), [])


if __name__ == "__main__":
    unittest.main()

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import tracing


def _log(tmp):
    return Path(tmp) / ".runtime" / "trace-log.jsonl"


def _rec(trace_id, n=0, **extra):
    return {"schema_version": 1, "trace_id": trace_id, "span_id": "0" * 16, "n": n, **extra}


class TestIds(unittest.TestCase):
    def test_new_ids_have_w3c_shape(self):
        self.assertRegex(tracing.new_trace_id(), r"^[0-9a-f]{32}$")
        self.assertRegex(tracing.new_span_id(), r"^[0-9a-f]{16}$")
        self.assertNotEqual(tracing.new_trace_id(), tracing.new_trace_id())
        self.assertNotEqual(tracing.new_span_id(), tracing.new_span_id())

    def test_derive_hex_passthrough(self):
        self.assertEqual(tracing.derive_trace_id("a" * 32), ("a" * 32, None))

    def test_derive_hashes_text_stably(self):
        first = tracing.derive_trace_id("DEM-12-emissao")
        second = tracing.derive_trace_id("DEM-12-emissao")
        self.assertEqual(first, second)
        self.assertRegex(first[0], r"^[0-9a-f]{32}$")
        self.assertEqual(first[1], "DEM-12-emissao")
        self.assertNotEqual(first[0], tracing.derive_trace_id("DEM-13")[0])

    def test_derive_blank_or_invalid_is_absent(self):
        for value in (None, "", "   ", "\x00\x07", 123, ["x"]):
            tid1, label1 = tracing.derive_trace_id(value)
            tid2, _ = tracing.derive_trace_id(value)
            self.assertIsNone(label1, repr(value))
            self.assertRegex(tid1, r"^[0-9a-f]{32}$")
            self.assertNotEqual(tid1, tid2, repr(value))

    def test_task_label_and_trace_id_never_carry_a_sensitive_value(self):
        tid1, label1 = tracing.derive_trace_id("cpf 123.456.789-09")
        tid2, label2 = tracing.derive_trace_id("cpf 987.654.321-00")
        self.assertNotIn("123.456.789-09", label1)
        self.assertIn("[redacted]", label1)
        self.assertEqual(tid1, tid2)  # derived from the masked text: the id is not a hash of the CPF

    def test_label_is_clean_and_capped(self):
        _, label = tracing.derive_trace_id("x\ny" + "z" * 200)
        self.assertNotIn("\n", label)
        self.assertLessEqual(len(label), 80)


class TestRedact(unittest.TestCase):
    def test_redact_masks_secret_keys_case_insensitively(self):
        out = tracing.redact_args({"GitHub_Token": "abc", "Password": "p", "api_key": "k", "q": "ok"})
        self.assertEqual(out["GitHub_Token"], "[redacted]")
        self.assertEqual(out["Password"], "[redacted]")
        self.assertEqual(out["api_key"], "[redacted]")
        self.assertEqual(out["q"], "ok")

    def test_content_args_become_char_counts(self):
        out = tracing.redact_args({"text": "CONTEUDO-SENTINELA" * 3, "q": "ok", "source": None},
                                  content_args=frozenset({"text", "source"}))
        self.assertEqual(out["text"], {"chars": 54})
        self.assertIsNone(out["source"])
        self.assertEqual(out["q"], "ok")
        self.assertNotIn("SENTINELA", json.dumps(out))
        self.assertEqual(tracing.redact_args({"text": "abc"})["text"], "abc")

    def test_redact_truncates_and_keeps_original(self):
        original = {"q": "a" * 500, "command": "b" * 800}
        snapshot = dict(original)
        out = tracing.redact_args(original)
        self.assertEqual(len(out["q"]), 200)
        self.assertEqual(len(out["command"]), 500)
        self.assertEqual(original, snapshot)

    def test_redact_survives_unserialisable_values(self):
        out = tracing.redact_args({"b": b"\xff", "o": object()})
        json.dumps(out)

    def test_redact_masks_secrets_inside_nested_values(self):
        original = {"opts": {"api_key": "SUPERSECRET", "ok": "fine"}, "items": [{"token": "TOK123"}, "plain"]}
        out = tracing.redact_args(original)
        text = json.dumps(out)
        self.assertNotIn("SUPERSECRET", text)
        self.assertNotIn("TOK123", text)
        self.assertEqual(out["opts"]["ok"], "fine")
        self.assertEqual(out["items"][1], "plain")
        self.assertEqual(original["opts"]["api_key"], "SUPERSECRET")

    def test_redact_bounds_very_deep_nesting(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"token": "DEEPSECRET"}}}}}}
        self.assertNotIn("DEEPSECRET", json.dumps(tracing.redact_args({"x": deep})))

    def test_redact_masks_sensitive_values_whatever_the_key(self):
        token = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
        out = tracing.redact_args({"summary": f"x {token} y", "note": "cpf 123.456.789-09", "ref": "k" + "3" * 44,
                                   "nested": {"text": f"also {token}"}, "plain": "keep me"})
        text = json.dumps(out)
        self.assertNotIn(token, text)
        self.assertNotIn("123.456.789-09", text)
        self.assertNotIn("3" * 44, text)
        self.assertEqual(out["plain"], "keep me")

    def test_redact_masks_values_hidden_by_control_characters(self):
        out = tracing.redact_args({"s": "cpf 123\x00456\x00789\x0009", "k": "nf " + "3\x01" * 44})
        self.assertNotIn("456", out["s"])
        self.assertNotIn("3333", out["k"])
        self.assertIn("[redacted]", out["s"] + out["k"])

    def test_redact_masks_a_pem_block_including_its_body(self):
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----\ndone"
        out = tracing.redact_args({"summary": pem})["summary"]
        self.assertNotIn("MIIEvQ", out)
        self.assertNotIn("END PRIVATE", out)
        self.assertIn("[redacted]", out)

    def test_redact_masks_printed_formats_of_cpf_and_nf_key(self):
        groups = " ".join(["3333"] * 11)
        dotted = ".".join(["3333"] * 11)
        for value in ("123 456 789 09", "123-456-789-09", groups, dotted, "123.4​56.789-09", "１２３.456.789-09"):
            out = tracing.redact_args({"note": f"x {value} y"})["note"]
            self.assertNotRegex(out, r"456|3333", value)

    def test_redact_keeps_ordinary_numbers_readable(self):
        out = tracing.redact_args({"ref": "vault/x.md:47", "ts": "2026-10-09T12:00:00.000-03:00", "t": "PR #13, 2026-10-08, 36 cenarios"})
        self.assertEqual(out, {"ref": "vault/x.md:47", "ts": "2026-10-09T12:00:00.000-03:00", "t": "PR #13, 2026-10-08, 36 cenarios"})

    def test_find_sensitive_names_the_rule(self):
        self.assertEqual(tracing.find_sensitive("123 456 789 09"), "cpf")
        self.assertEqual(tracing.find_sensitive(" ".join(["3333"] * 11)), "nf-key")
        self.assertEqual(tracing.find_sensitive("ghp_" + "a1B2c3D4e5F6g7H8i9J0"), "token")
        self.assertIsNone(tracing.find_sensitive("vault/x.md:47"))

    def test_redact_drops_task_id(self):
        self.assertNotIn("task_id", tracing.redact_args({"task_id": "DEM-1", "q": "x"}))


class TestWrite(unittest.TestCase):
    def test_write_record_appends_valid_json_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            tracing.write_record(_rec("a" * 32, 1), path)
            tracing.write_record(_rec("a" * 32, 2), path)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual([json.loads(l)["n"] for l in lines], [1, 2])

    def test_write_record_bounds_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            tracing.write_record(_rec("a" * 32, args={"q": "x" * 10000}), path)
            line = path.read_bytes().splitlines()[0]
            self.assertLessEqual(len(line) + 1, tracing.MAX_RECORD_BYTES)
            json.loads(line)

    def test_write_record_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(tracing.write_record(_rec("a" * 32), Path(tmp)))

    def test_rotation_keeps_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            with mock.patch.object(tracing, "MAX_BYTES", 200):
                for n in range(10):
                    tracing.write_record(_rec("a" * 32, n, pad="p" * 60), path)
            names = {p.name for p in path.parent.iterdir()}
            self.assertIn("trace-log.jsonl", names)
            for i in (1, 2, 3):
                self.assertIn(f"trace-log.{i}.jsonl", names)
            self.assertNotIn("trace-log.4.jsonl", names)


class TestRead(unittest.TestCase):
    def test_read_trace_filters_and_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            a, b = "a" * 32, "b" * 32
            with mock.patch.object(tracing, "MAX_BYTES", 250):
                for n, tid in enumerate([a, b, a, b, a, a]):
                    tracing.write_record(_rec(tid, n, pad="p" * 60), path)
            got = tracing.read_trace(a, path)
            self.assertEqual([r["n"] for r in got], [0, 2, 4, 5])
            self.assertTrue(all(r["trace_id"] == a for r in got))
            self.assertTrue((path.parent / "trace-log.1.jsonl").exists())

    def test_read_trace_skips_unparseable_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            tracing.write_record(_rec("a" * 32, 1), path)
            with open(path, "a", encoding="utf-8") as f:
                f.write("not json\n")
            self.assertEqual(len(tracing.read_trace("a" * 32, path)), 1)

    def test_unicode_line_separators_do_not_lose_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            tracing.write_record(_rec("a" * 32, 1, args={"q": "x y z"}), path)
            tracing.write_record(_rec("a" * 32, 2), path)
            got = tracing.read_trace("a" * 32, path)
            self.assertEqual([r["n"] for r in got], [1, 2])
            self.assertEqual(got[0]["args"]["q"], "x y z")

    def test_read_recent_returns_last_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _log(tmp)
            for n in range(5):
                tracing.write_record(_rec("a" * 32, n), path)
            self.assertEqual([r["n"] for r in tracing.read_recent(2, path)], [3, 4])

    def test_read_on_missing_log_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(tracing.read_trace("a" * 32, _log(tmp)), [])
            self.assertEqual(tracing.read_recent(3, _log(tmp)), [])


if __name__ == "__main__":
    unittest.main()

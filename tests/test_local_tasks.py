import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import settings
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


if __name__ == "__main__":
    unittest.main()

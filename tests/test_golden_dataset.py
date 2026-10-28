"""Golden dataset da recuperacao: tamanho, fontes existentes e entidades ausentes do vault (spec 2.5, CA-8)."""
import tempfile
import unittest
from pathlib import Path

import yaml

from config import settings
from core.vault_vocab import normalize_terms

DATASET = Path(__file__).resolve().parent.parent / "evals" / "golden_dataset.yaml"


def _as_phrase(text: str) -> str:
    return " " + " ".join(normalize_terms(text)) + " "


def entities_found(entities: list[str], vault_dir: Path) -> list[tuple[str, str]]:
    """(entidade, arquivo) para cada entidade que aparece como sequencia contigua de termos no vault."""
    found = []
    texts = {}
    for path in sorted(vault_dir.rglob("*.md")):
        try:
            texts[path.relative_to(vault_dir).as_posix()] = _as_phrase(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    for entity in entities:
        phrase = _as_phrase(entity)
        for rel, text in texts.items():
            if phrase in text:
                found.append((entity, rel))
                break
    return found


def _load():
    return yaml.safe_load(DATASET.read_text(encoding="utf-8"))


class TestGoldenDataset(unittest.TestCase):
    def setUp(self):
        self.data = _load()
        self.positives = self.data["cases"]
        self.negatives = self.data["negatives"]
        self.known = self.data["known_limit_negatives"]

    def test_counts(self):
        self.assertEqual(len(self.positives), 30)
        self.assertEqual(len(self.negatives), 30)
        self.assertEqual(len(self.known), 3)

    def test_negatives_are_mappings(self):
        for case in self.negatives + self.known:
            self.assertIsInstance(case, dict)
            self.assertTrue(case["prompt"])
            self.assertIsInstance(case["absent_entities"], list)
            self.assertIsInstance(case["neighbor_domain"], bool)

    def test_neighbor_domain(self):
        neighbors = [case for case in self.negatives if case["neighbor_domain"]]
        self.assertGreaterEqual(len(neighbors), 10)
        for case in neighbors + self.known:
            self.assertTrue(case["absent_entities"], case["prompt"])

    def test_positives_keep_runner_fields(self):
        for case in self.positives:
            for key in ("id", "title", "prompt", "expected_sources", "must_pass_gates"):
                self.assertIn(key, case, case.get("id"))
            self.assertIsInstance(case["must_pass_gates"], list)

    def test_expected_sources_exist(self):
        for case in self.positives:
            self.assertTrue(case["expected_sources"], case["id"])
            for src in case["expected_sources"]:
                self.assertTrue((settings.vault_dir / src).is_file(), f"{case['id']}: {src}")

    def test_absent_entities_not_in_vault(self):
        entities = [e for case in self.negatives + self.known for e in case["absent_entities"]]
        self.assertEqual(entities_found(entities, settings.vault_dir), [])

    def test_ids_and_prompts_unique(self):
        ids = [case["id"] for case in self.positives]
        self.assertEqual(len(ids), len(set(ids)))
        prompts = [case["prompt"] for case in self.positives + self.negatives + self.known]
        normalized = [normalize_terms(p) for p in prompts]
        self.assertEqual(len(normalized), len(set(normalized)))


class TestContaminationHelper(unittest.TestCase):
    def test_contamination_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "daily").mkdir()
            (vault / "daily" / "hoje.md").write_text("Conversamos sobre a integracao com acme cloud.", encoding="utf-8")
            self.assertEqual(entities_found(["Acme Cloud"], vault), [("Acme Cloud", "daily/hoje.md")])
            self.assertEqual(entities_found(["Acme Store"], vault), [])

    def test_partial_word_is_not_a_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "a.md").write_text("acmecloud junto", encoding="utf-8")
            self.assertEqual(entities_found(["Acme"], vault), [])


if __name__ == "__main__":
    unittest.main()

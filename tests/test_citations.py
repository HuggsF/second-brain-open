"""Contrato de citacao: piso de relevancia, diversidade por documento, versao e lacunas."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.citations import Citation, build_citations, gaps_for, select_hits

EMPTY_GAP = "Índice vazio ou indisponível para este espaço."
LOW_GAP = "Nenhum trecho atinge a relevância mínima; não há evidência no vault para esta consulta."
STALE_GAP = "Há citações de versão anterior do documento; rode o sync."


def _hit(doc, score, **extra):
    payload = {
        "file_path": doc,
        "section": "Secao",
        "line_start": 1,
        "line_end": 3,
        "doc_sha256": "x",
        "space_id": "s",
        "content": "texto",
    }
    payload.update(extra)
    return {"score": score, "payload": payload}


def hits(*scores):
    return [_hit("doc.md", s) for s in scores]


def hits_docs(*pairs):
    return [_hit(doc, score) for doc, score in pairs]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SelectHitsTest(unittest.TestCase):
    def test_floor_cuts_everything_when_top_is_low(self):  # CA-04 / INV-N02
        self.assertEqual(select_hits(hits(0.60, 0.59), min_score=0.65, max_drop=0.10, max_per_doc=2, limit=5), [])

    def test_floor_relative_to_top(self):  # CA-04
        got = select_hits(hits(0.80, 0.75, 0.69), min_score=0.65, max_drop=0.10, max_per_doc=5, limit=5)
        self.assertEqual([h["score"] for h in got], [0.80, 0.75])

    def test_absolute_floor_applies_even_inside_drop_window(self):
        got = select_hits(hits(0.70, 0.64), min_score=0.65, max_drop=0.10, max_per_doc=5, limit=5)
        self.assertEqual([h["score"] for h in got], [0.70])

    def test_empty_input(self):
        self.assertEqual(select_hits([], min_score=0.65, max_drop=0.10, max_per_doc=2, limit=5), [])

    def test_max_per_doc_frees_slots_for_other_docs(self):  # CA-05
        got = select_hits(
            hits_docs(("a", 0.80), ("a", 0.79), ("a", 0.78), ("b", 0.77)),
            min_score=0.65, max_drop=0.10, max_per_doc=2, limit=3,
        )
        self.assertEqual([h["payload"]["file_path"] for h in got], ["a", "a", "b"])

    def test_limit_cuts_after_diversity(self):
        got = select_hits(hits(0.9, 0.89, 0.88, 0.87), min_score=0.65, max_drop=0.10, max_per_doc=5, limit=2)
        self.assertEqual([h["score"] for h in got], [0.9, 0.89])

    def test_limit_zero_or_negative_returns_nothing(self):
        for limit in (0, -1):
            self.assertEqual(select_hits(hits(0.9, 0.8), min_score=0.65, max_drop=0.10, max_per_doc=5, limit=limit), [])

    def test_hit_exactly_at_min_score_is_kept(self):
        got = select_hits(hits(0.65), min_score=0.65, max_drop=0.10, max_per_doc=5, limit=5)
        self.assertEqual([h["score"] for h in got], [0.65])

    def test_does_not_mutate_input_and_returns_same_dicts(self):
        data = hits(0.9, 0.8, 0.5)
        snapshot = list(data)
        got = select_hits(data, min_score=0.65, max_drop=0.10, max_per_doc=5, limit=5)
        self.assertEqual(data, snapshot)
        self.assertEqual(len(data), 3)
        self.assertIs(got[0], data[0])
        self.assertIsNot(got, data)


class BuildCitationsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.vault = Path(self._tmp.name) / "vault"
        self.vault.mkdir()

    def _write(self, rel, data: bytes):
        path = self.vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_equal_hash_is_not_stale(self):
        self._write("a.md", b"conteudo\r\nigual\n")
        got = build_citations([_hit("a.md", 0.9, doc_sha256=sha(b"conteudo\r\nigual\n"))], self.vault)
        self.assertEqual(got, [Citation("a.md", "Secao", 1, 3, sha(b"conteudo\r\nigual\n"), 0.9, False)])

    def test_edited_file_is_stale(self):
        self._write("a.md", b"novo")
        got = build_citations([_hit("a.md", 0.9, doc_sha256=sha(b"velho"))], self.vault)
        self.assertTrue(got[0].stale)
        self.assertEqual(got[0].sha256, sha(b"velho"))

    def test_deleted_file_is_stale(self):
        got = build_citations([_hit("sumiu.md", 0.9, doc_sha256=sha(b"x"))], self.vault)
        self.assertTrue(got[0].stale)

    def test_refused_path_is_stale_and_reads_nothing_outside(self):
        outside = Path(self._tmp.name) / "fora.md"
        outside.write_bytes(b"segredo")
        real = Path.read_bytes
        read = []

        def spy(self_path):
            read.append(self_path)
            return real(self_path)

        with mock.patch.object(Path, "read_bytes", spy):
            got = build_citations([_hit("../fora.md", 0.9, doc_sha256=sha(b"segredo"))], self.vault)
        self.assertTrue(got[0].stale)
        self.assertEqual(read, [])

    def test_payload_without_hash_is_stale_with_none(self):
        self._write("a.md", b"x")
        hit = _hit("a.md", 0.9)
        for key in ("doc_sha256", "line_start", "line_end"):
            del hit["payload"][key]
        got = build_citations([hit], self.vault)
        self.assertEqual((got[0].sha256, got[0].line_start, got[0].line_end, got[0].stale), (None, None, None, True))

    def test_missing_section_is_empty_string(self):
        self._write("a.md", b"x")
        hit = _hit("a.md", 0.9, doc_sha256=sha(b"x"))
        del hit["payload"]["section"]
        self.assertEqual(build_citations([hit], self.vault)[0].section, "")

    def test_hash_computed_once_per_document_and_order_preserved(self):
        self._write("a.md", b"aa")
        self._write("b.md", b"bb")
        batch = [
            _hit("a.md", 0.9, doc_sha256=sha(b"aa")),
            _hit("b.md", 0.8, doc_sha256=sha(b"bb")),
            _hit("a.md", 0.7, doc_sha256=sha(b"aa")),
        ]
        real = Path.read_bytes
        calls = []

        def spy(self_path):
            calls.append(self_path.name)
            return real(self_path)

        with mock.patch.object(Path, "read_bytes", spy):
            got = build_citations(batch, self.vault)
        self.assertEqual(sorted(calls), ["a.md", "b.md"])
        self.assertEqual([c.document for c in got], ["a.md", "b.md", "a.md"])
        self.assertEqual([c.score for c in got], [0.9, 0.8, 0.7])
        self.assertFalse(any(c.stale for c in got))


class GapsForTest(unittest.TestCase):
    def _cit(self, stale):
        return Citation("a.md", "S", 1, 2, "h", 0.8, stale)

    def test_empty_index(self):
        self.assertEqual(gaps_for([], None, 0.65), [EMPTY_GAP])

    def test_no_evidence(self):
        self.assertEqual(gaps_for([], 0.50, 0.65), [LOW_GAP])

    def test_no_citations_with_top_above_floor_reports_no_evidence_gap(self):
        self.assertEqual(gaps_for([], 0.90, 0.65), [])

    def test_no_citations_with_top_equal_to_floor_reports_no_gap(self):
        self.assertEqual(gaps_for([], 0.65, 0.65), [])

    def test_stale_gap_once(self):
        got = gaps_for([self._cit(True), self._cit(True)], 0.80, 0.65)
        self.assertEqual(got, [STALE_GAP])

    def test_fresh_citations_have_no_gaps(self):
        self.assertEqual(gaps_for([self._cit(False)], 0.80, 0.65), [])


if __name__ == "__main__":
    unittest.main()

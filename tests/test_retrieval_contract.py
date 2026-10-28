import hashlib
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from config import settings
from core.citations import GAP_EMPTY_INDEX, GAP_NO_EVIDENCE, GAP_STALE
from core.qdrant_store import QdrantStore
from evals.retrieval_eval import collect, grid, known_limits_metric, load_cases, load_known_limits, suggest

VECTOR_SIZE = 4
QUERY_VECTOR = [1.0, 0.0, 0.0, 0.0]
NO_DOC_TEXT = "Nenhum documento relevante encontrado na sua base de conhecimento para essa pergunta."
REBUILD_HINT = "Rode 'cli.py sync --rebuild' para reconstruir o índice deste espaço."


def make_store(collection_name="kb", client=None):
    """QdrantStore sobre um QdrantClient em memoria (sem servidor)."""
    client = client or QdrantClient(location=":memory:")
    with mock.patch("core.qdrant_store.QdrantClient", return_value=client):
        store = QdrantStore(url="http://unused", collection_name=collection_name)
    return store, client


class TestStoreScope(unittest.TestCase):
    def setUp(self):
        self.store, self.client = make_store("kb")
        self.addCleanup(self.client.close)
        self.store.ensure_collection(vector_size=VECTOR_SIZE)
        vector = [1.0, 0.0, 0.0, 0.0]
        self.client.upsert(
            collection_name="kb",
            points=[
                PointStruct(id=1, vector=vector, payload={"space_id": "s1", "file_path": "a.md"}),
                PointStruct(id=2, vector=vector, payload={"space_id": "s1", "file_path": "b.md"}),
                PointStruct(id=3, vector=vector, payload={"space_id": "s2", "file_path": "c.md"}),
                PointStruct(id=4, vector=vector, payload={"space_id": "s2", "file_path": "d.md"}),
            ],
        )
        # Referencia: busca num armazem que so contem os pontos de s1.
        only_s1_store, only_s1_client = make_store("kb_s1")
        self.addCleanup(only_s1_client.close)
        only_s1_store.ensure_collection(vector_size=VECTOR_SIZE)
        only_s1_client.upsert(
            collection_name="kb_s1",
            points=[
                PointStruct(id=1, vector=vector, payload={"space_id": "s1", "file_path": "a.md"}),
                PointStruct(id=2, vector=vector, payload={"space_id": "s1", "file_path": "b.md"}),
            ],
        )
        self.only_s1_hits = only_s1_store.search([1.0, 0, 0, 0], limit=10)

    def test_search_never_returns_other_space(self):  # CA-03 / INV-N01
        hits = self.store.search([1.0, 0, 0, 0], limit=10, space_id="s1")
        self.assertTrue(hits and all(h["payload"]["space_id"] == "s1" for h in hits))
        self.assertEqual(len(hits), 2)

    def test_points_without_space_are_invisible(self):
        self.client.upsert(
            collection_name="kb",
            points=[PointStruct(id=99, vector=[1.0, 0.0, 0.0, 0.0],
                                payload={"file_path": "legacy.md"})],
        )
        self.assertEqual(
            self.store.search([1.0, 0, 0, 0], limit=10, space_id="s1"), self.only_s1_hits
        )

    def test_without_space_id_keeps_unfiltered_behavior(self):
        hits = self.store.search([1.0, 0, 0, 0], limit=10)
        self.assertEqual({h["payload"]["space_id"] for h in hits}, {"s1", "s2"})
        self.assertEqual(len(hits), 4)

    def test_space_id_combines_with_other_filters(self):
        self.client.set_payload(
            collection_name="kb", payload={"category": "x"}, points=[1, 3]
        )
        hits = self.store.search([1.0, 0, 0, 0], limit=10, category="x", space_id="s1")
        self.assertEqual([h["payload"]["file_path"] for h in hits], ["a.md"])

    def test_index_version_follows_alias(self):
        self.assertEqual(self.store.index_version(), "kb")  # colecao real
        self.store.create_named_collection("kb__1", VECTOR_SIZE)
        self.store.swap_alias("kb2", "kb__1", has_old_alias=False)
        aliased, _ = make_store("kb2", client=self.client)
        self.assertEqual(aliased.index_version(), "kb__1")


def vector_for(score):
    """Vetor cuja similaridade de cosseno com QUERY_VECTOR e `score`."""
    return [score, math.sqrt(1.0 - score * score), 0.0, 0.0]


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_query(self, text):
        self.calls += 1
        return list(QUERY_VECTOR)


class TestRetriever(unittest.TestCase):
    """BrainRetriever.query()/answer() com escopo, piso, diversidade e citacoes (spec 2.3, 2.5, 6)."""

    def setUp(self):
        from core.retriever import BrainRetriever

        for name, value in (("space_id", "kiosk"), ("retrieval_min_score", 0.65),
                            ("retrieval_max_drop", 0.10), ("retrieval_max_per_doc", 2)):
            patcher = mock.patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vault = Path(tmp.name)
        (self.vault / "a.md").write_text("conteudo a", encoding="utf-8")
        (self.vault / "b.md").write_text("conteudo b", encoding="utf-8")
        sha = {name: hashlib.sha256((self.vault / name).read_bytes()).hexdigest() for name in ("a.md", "b.md")}

        def payload(file_path, section, space="kiosk", **extra):
            data = {"file_path": file_path, "doc_title": file_path.upper(), "section": section,
                    "category": "systems", "chunk_index": 0, "line_start": 1, "line_end": 3,
                    "doc_sha256": sha.get(file_path, "0" * 64), "content": f"texto {file_path} {section}"}
            if space is not None:
                data["space_id"] = space
            data.update(extra)
            return data

        def build(collection, points):
            store, client = make_store(collection)
            self.addCleanup(client.close)
            store.ensure_collection(vector_size=VECTOR_SIZE)
            client.upsert(collection_name=collection, points=[
                PointStruct(id=i, vector=vector_for(score), payload=data)
                for i, (score, data) in enumerate(points, start=1)
            ])
            return BrainRetriever(embedder=FakeEmbedder(), store=store, vault_dir=self.vault), store

        # Melhor 0.95 -> piso 0.85: a.md tem 3 trechos acima (diversidade corta em 2), c.md fica abaixo.
        self.retriever, self.store = build("kb", [
            (0.95, payload("a.md", "A1")),
            (0.93, payload("a.md", "A2")),
            (0.91, payload("a.md", "A3")),
            (0.90, payload("b.md", "B1")),
            (0.70, payload("c.md", "C1")),
            (0.99, payload("x.md", "X1", space="outro")),
        ])
        self.retriever_low_scores, _ = build("low", [
            (0.50, payload("a.md", "A1")),
            (0.45, payload("b.md", "B1")),
            (0.40, payload("c.md", "C1")),
            (0.35, payload("d.md", "D1")),
            (0.30, payload("e.md", "E1")),
        ])
        self.retriever_on_old_points, _ = build("old", [
            (0.95, payload("a.md", "A1", space=None)),
            (0.90, payload("b.md", "B1", space=None)),
        ])

    @staticmethod
    def _ollama_ok(text=" resposta do modelo "):
        client_cls = mock.MagicMock()
        response = client_cls.return_value.__enter__.return_value.post.return_value
        response.status_code = 200
        response.json.return_value = {"response": text}
        return client_cls

    def test_query_keeps_old_keys_and_adds_new(self):  # CA-07 / INV-N05
        r = self.retriever.query("x")
        self.assertTrue({"question", "context", "sources", "citations", "gaps", "index_version"} <= set(r))
        self.assertTrue({"file_path", "doc_title", "section", "category", "score", "sha256", "line_start",
                         "line_end", "stale"} <= set(r["sources"][0]))
        self.assertIsInstance(r["question"], str)
        self.assertIsInstance(r["context"], str)
        self.assertNotIn("content", r["sources"][0])

    def test_query_applies_space_floor_and_diversity(self):  # INV-N01 / spec 2.3
        r = self.retriever.query("x")
        self.assertEqual([(s["file_path"], s["section"]) for s in r["sources"]],
                         [("a.md", "A1"), ("a.md", "A2"), ("b.md", "B1")])
        self.assertEqual([c["document"] for c in r["citations"]], ["a.md", "a.md", "b.md"])
        self.assertNotIn("x.md", r["context"])
        self.assertNotIn("c.md", r["context"])
        self.assertEqual(r["gaps"], [])
        self.assertEqual(r["index_version"], "kb")

    def test_sources_carry_citation_fields(self):
        r = self.retriever.query("x")
        for source, citation in zip(r["sources"], r["citations"], strict=True):
            for key in ("sha256", "line_start", "line_end", "stale"):
                self.assertEqual(source[key], citation[key])
            self.assertFalse(source["stale"])
        self.assertEqual(set(r["citations"][0]),
                         {"document", "section", "line_start", "line_end", "sha256", "score", "stale"})

    def test_search_uses_space_and_triple_limit(self):
        with mock.patch.object(self.store, "search", wraps=self.store.search) as search:
            self.retriever.query("x", limit=2, category="systems")
        kwargs = search.call_args.kwargs
        self.assertEqual((kwargs["space_id"], kwargs["limit"], kwargs["category"]), ("kiosk", 6, "systems"))

    def test_include_content_adds_chunk_text(self):
        sources = self.retriever.query("x", include_content=True)["sources"]
        self.assertEqual(sources[0]["content"], "texto a.md A1")

    def test_low_scores_give_no_citation(self):  # INV-N02
        r = self.retriever_low_scores.query("x")
        self.assertEqual((r["sources"], r["citations"], r["context"]), ([], [], ""))
        self.assertEqual(r["gaps"], [GAP_NO_EVIDENCE])

    def test_no_evidence_answer_skips_model(self):  # CA-08 / INV-N06
        with mock.patch("core.retriever.httpx.Client") as client:
            r = self.retriever_low_scores.answer("x")
        client.assert_not_called()
        self.assertEqual(r["status"], "no_evidence")
        self.assertEqual(r["citations"], [])
        self.assertEqual((r["answer"], r["sources"], r["gaps"]), (NO_DOC_TEXT, [], [GAP_NO_EVIDENCE]))

    def test_model_error_is_typed(self):  # CA-08
        with mock.patch("core.retriever.httpx.Client", side_effect=RuntimeError("down")):
            r = self.retriever.answer("x")
        self.assertEqual(r["status"], "model_error")
        self.assertTrue(r["answer"].startswith(
            "Contexto recuperado com sucesso do Qdrant, porém não foi possível conectar ao chat do Ollama: down"))
        self.assertEqual(len(r["citations"]), 3)

    def test_model_non_200_is_model_error(self):
        client_cls = self._ollama_ok()
        client_cls.return_value.__enter__.return_value.post.return_value.status_code = 500
        with mock.patch("core.retriever.httpx.Client", client_cls):
            r = self.retriever.answer("x")
        self.assertEqual(r["status"], "model_error")
        self.assertEqual(r["answer"], "Contexto recuperado com sucesso, mas o modelo local retornou código 500.")

    def test_answer_ok_keeps_old_keys_and_adds_new(self):  # CA-07
        with mock.patch("core.retriever.httpx.Client", self._ollama_ok()):
            r = self.retriever.answer("x")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["answer"], "resposta do modelo")
        self.assertTrue({"answer", "sources", "status", "citations", "gaps"} <= set(r))
        self.assertEqual([s["file_path"] for s in r["sources"]], [c["document"] for c in r["citations"]])
        self.assertEqual(r["gaps"], [])

    def test_edited_note_is_stale(self):  # Review Focus 2
        (self.vault / "a.md").write_text("mudou", encoding="utf-8")
        r = self.retriever.query("x")
        self.assertTrue(r["citations"][0]["stale"])
        self.assertTrue(r["sources"][0]["stale"])
        self.assertIn(GAP_STALE, r["gaps"])
        self.assertIn("Há citações de versão anterior do documento; rode o sync.", r["gaps"])

    def test_old_index_without_space_gives_gap(self):  # Review Focus 3
        r = self.retriever_on_old_points.query("x")
        self.assertEqual((r["citations"], r["gaps"]), ([], ["Índice vazio ou indisponível para este espaço."]))
        self.assertEqual(r["gaps"], [GAP_EMPTY_INDEX])

    def test_filter_no_match_with_populated_space_gives_no_evidence(self):
        """Busca com bounded_context sem match: espaco tem pontos, lacuna e sem evidencia."""
        r = self.retriever.query("x", bounded_context="Inexistente")
        self.assertEqual(r["citations"], [])
        self.assertEqual(r["gaps"], [GAP_NO_EVIDENCE])

    def test_filter_no_match_on_old_index_gives_empty_index(self):
        """Busca com filtro num indice so com pontos antigos: lacuna de indice vazio."""
        r = self.retriever_on_old_points.query("x", bounded_context="Fiscal")
        self.assertEqual(r["citations"], [])
        self.assertEqual(r["gaps"], [GAP_EMPTY_INDEX])

    def test_apply_floor_false_returns_raw(self):
        r = self.retriever_low_scores.query("x", apply_floor=False)
        self.assertEqual(len(r["sources"]), 4)
        self.assertEqual(len(r["citations"]), 4)
        self.assertEqual([s["file_path"] for s in r["sources"]], ["a.md", "b.md", "c.md", "d.md"])

    def test_default_constructor_still_works(self):
        from core.retriever import BrainRetriever

        with mock.patch("core.retriever.OllamaEmbeddingClient") as embedder, \
                mock.patch("core.retriever.QdrantStore") as store:
            r = BrainRetriever()
        self.assertIs(r.embedder, embedder.return_value)
        self.assertIs(r.store, store.return_value)
        self.assertEqual(r.vault_dir, settings.vault_dir)

    # Gate de entidade desconhecida (spec 2.3, CA-5, CA-6).
    def test_unknown_entity_gives_no_citation_and_named_gap(self):
        r = self.retriever.query("Como a Acme recebe pedidos?")
        self.assertEqual((r["citations"], r["sources"], r["context"]), ([], [], ""))
        self.assertEqual(r["gaps"], ["Termo(s) sem registro no vault: Acme; não há evidência para esta consulta."])

    def test_unknown_entity_answer_skips_model(self):
        client_cls = self._ollama_ok()
        with mock.patch("core.retriever.httpx.Client", client_cls):
            r = self.retriever.answer("Como a Acme recebe pedidos?")
        self.assertEqual(r["status"], "no_evidence")
        self.assertEqual(r["gaps"], ["Termo(s) sem registro no vault: Acme; não há evidência para esta consulta."])
        client_cls.assert_not_called()

    def test_known_capitalized_term_keeps_hits(self):
        (self.vault / "c.md").write_text("Integração com a Acme.", encoding="utf-8")
        r = self.retriever.query("Como a Acme recebe pedidos?")
        self.assertEqual([c["document"] for c in r["citations"]], ["a.md", "a.md", "b.md"])

    def test_entity_gate_false_keeps_hits(self):
        r = self.retriever.query("Como a Acme recebe pedidos?", entity_gate=False)
        self.assertEqual(len(r["citations"]), 3)

    def test_apply_floor_false_ignores_gate(self):
        r = self.retriever.query("Como a Acme recebe pedidos?", limit=5, apply_floor=False)
        self.assertEqual(len(r["sources"]), 5)

    def test_empty_vault_disables_gate(self):
        for name in ("a.md", "b.md"):
            (self.vault / name).unlink()
        r = self.retriever.query("Como a Acme recebe pedidos?")
        self.assertEqual(len(r["sources"]), 3)
        self.assertNotIn("Acme", " ".join(r["gaps"]))


class TestAskCli(unittest.TestCase):
    """cli.py ask orienta o rebuild quando o indice do espaco esta vazio (spec 6)."""

    def setUp(self):
        import importlib
        import importlib.util
        import sys
        import types

        import click
        from click.testing import CliRunner

        # cli.py importa scripts.sanitize no fim do modulo; se ele nao existe neste checkout,
        # um stub (so durante o teste) deixa o grupo carregar. sys.modules e restaurado no fim.
        modules = mock.patch.dict(sys.modules)
        modules.start()
        self.addCleanup(modules.stop)
        sys.modules.pop("cli", None)
        try:
            real_sanitize = importlib.util.find_spec("scripts.sanitize") is not None
        except ImportError:
            real_sanitize = False
        if not real_sanitize:
            stub = types.ModuleType("scripts.sanitize")
            stub.sanitize_cmd = click.Command("sanitize", callback=lambda: None)
            sys.modules["scripts.sanitize"] = stub
        self.cli = importlib.import_module("cli").cli
        self.runner = CliRunner()
        patcher = mock.patch("core.retriever.BrainRetriever")
        self.retriever = patcher.start().return_value
        self.addCleanup(patcher.stop)

    def _ask(self, result):
        self.retriever.answer.return_value = result
        return self.runner.invoke(self.cli, ["ask", "pergunta"])

    def test_empty_index_prints_rebuild_hint(self):
        out = self._ask({"answer": NO_DOC_TEXT, "sources": [], "status": "no_evidence",
                         "citations": [], "gaps": [GAP_EMPTY_INDEX]})
        self.assertEqual(out.exit_code, 0, out.output)
        self.assertIn(REBUILD_HINT, out.output)
        self.assertIn("Nenhum documento relevante", out.output)

    def test_no_evidence_without_empty_index_has_no_hint(self):
        out = self._ask({"answer": NO_DOC_TEXT, "sources": [], "status": "no_evidence",
                         "citations": [], "gaps": [GAP_NO_EVIDENCE]})
        self.assertEqual(out.exit_code, 0, out.output)
        self.assertNotIn(REBUILD_HINT, out.output)

    def test_old_result_without_gaps_still_prints(self):
        out = self._ask({"answer": "ok", "sources": [{"file_path": "a.md", "section": "S", "score": 0.9}]})
        self.assertEqual(out.exit_code, 0, out.output)
        self.assertNotIn(REBUILD_HINT, out.output)
        self.assertIn("a.md", out.output)


def fake_collected(pos, neg):
    """`collected` no formato de `collect`: cada positivo tem uma fonte esperada e um hit no score dado."""
    positives = []
    for i, (score, is_expected) in enumerate(pos):
        expected = f"adrs/ADR-{i:03d}.md"
        hit_file = expected if is_expected else f"adrs/OUTRO-{i:03d}.md"
        positives.append({"prompt": f"positivo {i}", "expected": [expected],
                          "hits": [{"file_path": hit_file, "score": score}]})
    negatives = [{"prompt": f"negativo {i}", "hits": [{"file_path": f"adrs/NEG-{i:03d}.md", "score": score}]}
                 for i, score in enumerate(neg)]
    return {"positives": positives, "negatives": negatives}


class TestRetrievalEval(unittest.TestCase):
    def test_grid_and_suggestion(self):  # CA-10
        collected = fake_collected(pos=[(.79, True), (.74, True)], neg=[.56, .55])
        rows = grid(collected, [0.55, 0.60, 0.70], [0.10])
        best = suggest(rows)
        self.assertEqual((best["min_score"], best["negatives_cleared"], best["recall_at_k"]), (0.60, 1.0, 1.0))
        by_min = {row["min_score"]: row for row in rows}
        self.assertEqual(by_min[0.55]["negatives_cleared"], 0.0)
        self.assertEqual(by_min[0.70]["recall_at_k"], 1.0)  # tambem limpa, mas com piso maior
        self.assertEqual(set(rows[0]), {"min_score", "max_drop", "recall_at_k", "negatives_cleared"})

    def test_suggest_none_when_no_row_clears_all_negatives(self):
        rows = grid(fake_collected(pos=[(.79, True)], neg=[.80]), [0.55, 0.60], [0.10])
        self.assertIsNone(suggest(rows))

    def test_suggest_tie_prefers_lowest_min_then_lowest_drop(self):
        rows = [
            {"min_score": 0.70, "max_drop": 0.05, "recall_at_k": 1.0, "negatives_cleared": 1.0},
            {"min_score": 0.60, "max_drop": 0.10, "recall_at_k": 1.0, "negatives_cleared": 1.0},
            {"min_score": 0.60, "max_drop": 0.05, "recall_at_k": 1.0, "negatives_cleared": 1.0},
            {"min_score": 0.50, "max_drop": 0.05, "recall_at_k": 0.5, "negatives_cleared": 1.0},
            {"min_score": 0.40, "max_drop": 0.05, "recall_at_k": 1.0, "negatives_cleared": 0.5},
        ]
        best = suggest(rows)
        self.assertEqual((best["min_score"], best["max_drop"]), (0.60, 0.05))

    def test_recall_counts_only_expected_sources_among_selected_hits(self):
        collected = {"positives": [{"prompt": "p", "expected": ["a.md", "b.md"],
                                    "hits": [{"file_path": "a.md", "score": 0.80},
                                             {"file_path": "x.md", "score": 0.79},
                                             {"file_path": "b.md", "score": 0.50}]}],
                     "negatives": []}
        rows = grid(collected, [0.55], [0.10])
        self.assertEqual(rows[0]["recall_at_k"], 0.5)  # b.md cai abaixo do corte de queda
        self.assertEqual(rows[0]["negatives_cleared"], 1.0)

    def _write_dataset(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "ds.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_load_cases_accepts_string_and_mapping_negatives(self):
        path = self._write_dataset(
            "cases: []\n"
            "negatives:\n"
            "  - \"a\"\n"
            "  - {prompt: \"b\", absent_entities: [\"Acme\"], neighbor_domain: true}\n"
        )
        _, neg = load_cases(path)
        self.assertEqual(neg, ["a", "b"])

    def test_load_known_limits(self):
        path = self._write_dataset(
            "known_limit_negatives:\n"
            "  - {prompt: \"c\", absent_entities: [\"acme\"], neighbor_domain: true}\n"
        )
        self.assertEqual(load_known_limits(path), ["c"])
        self.assertEqual(load_known_limits(self._write_dataset("cases: []\n")), [])

    def test_dataset_has_enough_cases_and_files_exist(self):
        pos, neg = load_cases(Path("evals/golden_dataset.yaml"))
        self.assertGreaterEqual(len(pos), 12)
        self.assertGreaterEqual(len(neg), 8)
        for case in pos:
            self.assertTrue(case["prompt"])
            self.assertTrue(case["expected_sources"])
            for src in case["expected_sources"]:
                self.assertTrue((settings.vault_dir / src).is_file(), src)

    def test_collect_asks_for_raw_hits_with_triple_limit(self):
        retriever = mock.Mock()
        retriever.query.return_value = {"sources": [
            {"file_path": "a.md", "score": 0.8, "section": "S", "sha256": "x"},
            {"file_path": "b.md", "score": 0.6, "section": "T"}]}
        positives = [{"prompt": "p1", "expected_sources": ["a.md"]}]
        out = collect(retriever, positives, ["n1"], k=5, vocabulary=frozenset({"x"}))
        self.assertEqual(retriever.query.call_count, 2)
        for call in retriever.query.call_args_list:
            self.assertIs(call.kwargs["apply_floor"], False)
            self.assertEqual(call.kwargs["limit"], 15)
        self.assertEqual(out["positives"], [{"prompt": "p1", "expected": ["a.md"],
                                             "hits": [{"file_path": "a.md", "score": 0.8},
                                                      {"file_path": "b.md", "score": 0.6}],
                                             "unknown": []}])
        self.assertEqual(out["negatives"][0]["prompt"], "n1")
        self.assertEqual(len(out["negatives"][0]["hits"]), 2)

    def test_collect_records_unknown_and_known_limits(self):
        retriever = mock.Mock()
        retriever.query.return_value = {"sources": [{"file_path": "a.md", "score": 0.8}]}
        out = collect(retriever, [], ["Como a Acme vende?"], k=5, known_limits=["como a acme vende?"],
                      vocabulary=frozenset({"vende"}))
        self.assertEqual(out["negatives"][0]["unknown"], ["Acme"])
        self.assertEqual(out["known_limits"][0]["unknown"], [])
        self.assertEqual(out["known_limits"][0]["hits"], [{"file_path": "a.md", "score": 0.8}])

    def test_gate_clears_high_scoring_negative(self):
        collected = {"positives": [], "negatives": [
            {"prompt": "n", "hits": [{"file_path": "x.md", "score": 0.80}], "unknown": ["Acme"]}]}
        self.assertEqual(grid(collected, [0.65], [0.10], gate=False)[0]["negatives_cleared"], 0.0)
        self.assertEqual(grid(collected, [0.65], [0.10], gate=True)[0]["negatives_cleared"], 1.0)

    def test_gate_drops_recall_of_unknown_positive(self):
        hits = [{"file_path": "a.md", "score": 0.9}]
        collected = {"negatives": [], "positives": [
            {"prompt": "p1", "expected": ["a.md"], "hits": hits, "unknown": []},
            {"prompt": "p2", "expected": ["a.md"], "hits": hits, "unknown": ["Acme"]}]}
        self.assertEqual(grid(collected, [0.65], [0.10], gate=False)[0]["recall_at_k"], 1.0)
        self.assertEqual(grid(collected, [0.65], [0.10], gate=True)[0]["recall_at_k"], 0.5)

    def test_gate_accepts_collected_without_unknown(self):
        collected = fake_collected([(0.9, True)], [0.5])
        self.assertEqual(grid(collected, [0.65], [0.10], gate=True), grid(collected, [0.65], [0.10]))

    def test_known_limits_metric(self):
        collected = {"positives": [], "negatives": [], "known_limits": [
            {"prompt": "k1", "hits": [{"file_path": "a.md", "score": 0.50}], "unknown": []},
            {"prompt": "k2", "hits": [], "unknown": []},
            {"prompt": "k3", "hits": [{"file_path": "b.md", "score": 0.90}], "unknown": []}]}
        metric = known_limits_metric(collected, min_score=0.65, max_drop=0.10, k=5, basis="provisional")
        self.assertEqual(metric, {"count": 3, "without_sources": 2, "fraction_without_sources": 2 / 3,
                                  "min_score": 0.65, "max_drop": 0.10, "basis": "provisional"})

    def test_known_limits_not_in_negative_denominator(self):
        collected = fake_collected([], [0.5])
        collected["known_limits"] = [{"prompt": "k", "hits": [{"file_path": "a.md", "score": 0.9}], "unknown": []}]
        self.assertEqual(grid(collected, [0.65], [0.10], gate=True)[0]["negatives_cleared"], 1.0)

    def test_runner_no_longer_claims_recall(self):
        from evals.runner import run_evals
        with mock.patch("builtins.print"):
            report = run_evals(verbose=False)
        self.assertTrue(report["results"])
        for result in report["results"]:
            self.assertIsNone(result["recall"], result["case_id"])
        # sem recall no composto: caso com todos os gates aprovados vale exatamente 100
        for result in report["results"]:
            if result["gates_total"] and result["gates_passed"] == result["gates_total"]:
                self.assertEqual(result["score"], 100.0)
        no_gates = [r for r in report["results"] if not r["gates_total"]]
        self.assertTrue(no_gates)
        self.assertTrue(all(r["score"] is None for r in no_gates))


class TestRetrievalEvalCli(unittest.TestCase):
    """cli.py retrieval-eval: codigos de saida, sem Qdrant nem Ollama (collect e grid simulados)."""

    COLLECTED = {"positives": [], "negatives": []}
    SUGGESTED_ROWS = [{"min_score": 0.60, "max_drop": 0.10, "recall_at_k": 0.9, "negatives_cleared": 1.0}]

    def setUp(self):
        import importlib
        import importlib.util
        import sys
        import types

        import click
        from click.testing import CliRunner

        modules = mock.patch.dict(sys.modules)
        modules.start()
        self.addCleanup(modules.stop)
        sys.modules.pop("cli", None)
        try:
            real_sanitize = importlib.util.find_spec("scripts.sanitize") is not None
        except ImportError:
            real_sanitize = False
        if not real_sanitize:
            stub = types.ModuleType("scripts.sanitize")
            stub.sanitize_cmd = click.Command("sanitize", callback=lambda: None)
            sys.modules["scripts.sanitize"] = stub
        cli_module = importlib.import_module("cli")
        self.cli = cli_module.cli
        self.runner = CliRunner()
        patcher = mock.patch("core.retriever.BrainRetriever")
        self.retriever_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.retriever_cls.return_value.store.legacy_points_count.return_value = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reports_dir = Path(self.tmp.name) / "reports"
        reports = mock.patch.object(cli_module, "REPORTS_DIR", self.reports_dir)
        reports.start()
        self.addCleanup(reports.stop)

    def invoke(self, *args, rows=None):
        with mock.patch("evals.retrieval_eval.collect", return_value=self.COLLECTED), \
                mock.patch("evals.retrieval_eval.grid",
                           return_value=self.SUGGESTED_ROWS if rows is None else rows):
            return self.runner.invoke(self.cli, ["retrieval-eval", *args])

    def test_suggestion_with_enough_recall_exits_zero_and_writes_report(self):
        out = self.invoke("--min-recall", "0.8")
        self.assertEqual(out.exit_code, 0, out.output)
        self.assertEqual(len(list(self.reports_dir.glob("retrieval-*.json"))), 1)

    def test_suggestion_below_min_recall_exits_one(self):
        out = self.invoke("--min-recall", "0.95")
        self.assertEqual(out.exit_code, 1, out.output)

    def test_no_suggestion_exits_one(self):
        rows = [{"min_score": 0.60, "max_drop": 0.10, "recall_at_k": 1.0, "negatives_cleared": 0.5}]
        out = self.invoke(rows=rows)
        self.assertEqual(out.exit_code, 1, out.output)

    def test_prints_two_tables_and_suggests_from_gate_rows(self):
        def rows_by_gate(*args, gate=False, **kwargs):
            return self.SUGGESTED_ROWS if gate else [dict(self.SUGGESTED_ROWS[0], negatives_cleared=0.5)]
        with mock.patch("evals.retrieval_eval.collect", return_value=self.COLLECTED),                 mock.patch("evals.retrieval_eval.grid", side_effect=rows_by_gate):
            out = self.runner.invoke(self.cli, ["retrieval-eval"])
        self.assertEqual(out.exit_code, 0, out.output)
        self.assertIn("Grade sem gate", out.output)
        self.assertIn("Grade com gate", out.output)

    def test_report_has_gate_rows_known_limits_scheme_and_dataset_hash(self):
        import json
        from core.embeddings import current_embed_scheme
        dataset = Path("evals/golden_dataset.yaml")
        out = self.invoke("--dataset", str(dataset))
        self.assertEqual(out.exit_code, 0, out.output)
        report = json.loads(next(self.reports_dir.glob("retrieval-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(report["gate_rows"], self.SUGGESTED_ROWS)
        self.assertEqual(report["known_limits"]["basis"], "suggested")
        self.assertEqual(report["embed_scheme"], current_embed_scheme())
        self.assertEqual(report["dataset_sha256"], hashlib.sha256(dataset.read_bytes()).hexdigest())

    def test_legacy_index_exits_one_before_collect(self):
        self.retriever_cls.return_value.store.legacy_points_count.return_value = 3
        with mock.patch("evals.retrieval_eval.collect") as collect_mock:
            out = self.runner.invoke(self.cli, ["retrieval-eval"])
        self.assertEqual(out.exit_code, 1, out.output)
        self.assertIn("Índice com esquema anterior; rode 'cli.py sync --rebuild --yes'.", out.output)
        collect_mock.assert_not_called()
        self.assertFalse(self.reports_dir.exists() and list(self.reports_dir.iterdir()))

    def test_connection_error_prints_message_without_traceback(self):
        with mock.patch("evals.retrieval_eval.collect", side_effect=ConnectionError("recusada")):
            out = self.runner.invoke(self.cli, ["retrieval-eval"])
        self.assertEqual(out.exit_code, 1)
        self.assertIn("Qdrant", out.output)
        self.assertNotIn("Traceback", out.output)


if __name__ == "__main__":
    unittest.main()

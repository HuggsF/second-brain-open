"""Tests for T3 — chunker ontology enrichment and search filtering."""
import pytest
from pathlib import Path
from core.chunker import MarkdownChunker
from config import settings


class TestChunkerFrontmatter:
    def test_extracts_related_field(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\ntype: system\nstatus: active\nrelated: [hub-ontologia, hub-mapa]\n---\n# Test\nContent here.\n", encoding="utf-8")
        chunks = MarkdownChunker().chunk_file(md, tmp_path)
        assert len(chunks) >= 1
        meta = chunks[0]["metadata"]
        assert "related" in meta
        assert "hub-ontologia" in meta["related"]

    def test_extracts_bounded_context(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\ntype: system\nbounded_context: Fiscal\n---\n# Test\nContent.\n", encoding="utf-8")
        chunks = MarkdownChunker().chunk_file(md, tmp_path)
        assert chunks[0]["metadata"].get("bounded_context") == "Fiscal"

    def test_extracts_entities(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\ntype: system\nentities: [NfeSnapshot, DispatchJob]\n---\n# Test\nContent.\n", encoding="utf-8")
        chunks = MarkdownChunker().chunk_file(md, tmp_path)
        assert "NfeSnapshot" in chunks[0]["metadata"].get("entities", "")

    def test_backward_compatible_no_extra_fields(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\ntype: system\nstatus: active\n---\n# Test\nContent.\n", encoding="utf-8")
        chunks = MarkdownChunker().chunk_file(md, tmp_path)
        meta = chunks[0]["metadata"]
        assert "related" not in meta
        assert "bounded_context" not in meta
        assert "entities" not in meta


class TestRetrieverIncludeContent:
    def test_query_signature_accepts_bounded_context(self):
        from core.retriever import BrainRetriever
        import inspect
        sig = inspect.signature(BrainRetriever.query)
        assert "bounded_context" in sig.parameters
        assert "include_content" in sig.parameters

    def test_qdrant_search_accepts_bounded_context(self):
        from core.qdrant_store import QdrantStore
        import inspect
        sig = inspect.signature(QdrantStore.search)
        assert "bounded_context" in sig.parameters

"""Prefixos de tarefa do embedding e identificador do esquema (spec 2.1, CA-1)."""
import re
import unittest
from unittest import mock

from config import settings
from core.embeddings import OllamaEmbeddingClient, current_embed_scheme, embed_scheme_id


def _client_sending(calls):
    """httpx.Client falso: guarda o `input` de cada POST e responde um vetor."""
    response = mock.Mock(status_code=200)
    response.json.return_value = {"embeddings": [[0.1, 0.2]]}
    http = mock.MagicMock()
    http.__enter__.return_value = http
    http.post.side_effect = lambda url, json: calls.append(json["input"]) or response
    return mock.patch("core.embeddings.httpx.Client", return_value=http)


class TestPrefixes(unittest.TestCase):
    def setUp(self):
        self.client = OllamaEmbeddingClient(
            base_url="http://ollama.invalid", model="m",
            query_prefix="search_query: ", document_prefix="search_document: ",
        )

    def test_embed_query_adds_prefix(self):
        calls = []
        with _client_sending(calls):
            self.assertEqual(self.client.embed_query("pergunta"), [0.1, 0.2])
        self.assertEqual(calls, ["search_query: pergunta"])

    def test_embed_document_adds_prefix(self):
        calls = []
        with _client_sending(calls):
            self.client.embed_document("trecho")
        self.assertEqual(calls, ["search_document: trecho"])

    def test_get_embedding_stays_raw(self):
        calls = []
        with _client_sending(calls):
            self.client.get_embedding("cru")
        self.assertEqual(calls, ["cru"])

    def test_defaults_come_from_settings(self):
        client = OllamaEmbeddingClient(base_url="http://ollama.invalid")
        self.assertEqual(client.query_prefix, settings.embed_query_prefix)
        self.assertEqual(client.document_prefix, settings.embed_document_prefix)

    def test_settings_defaults(self):
        self.assertEqual(settings.embed_query_prefix, "search_query: ")
        self.assertEqual(settings.embed_document_prefix, "search_document: ")


class TestScheme(unittest.TestCase):
    def test_scheme_is_twelve_hex_and_stable(self):
        scheme = embed_scheme_id("nomic-embed-text", "search_query: ", "search_document: ")
        self.assertRegex(scheme, re.compile(r"^[0-9a-f]{12}$"))
        self.assertEqual(scheme, embed_scheme_id("nomic-embed-text", "search_query: ", "search_document: "))

    def test_scheme_changes_with_each_part(self):
        variants = [
            ("nomic-embed-text", "search_query: ", "search_document: "),
            ("outro-modelo", "search_query: ", "search_document: "),
            ("nomic-embed-text", "query: ", "search_document: "),
            ("nomic-embed-text", "search_query: ", "doc: "),
            ("nomic-embed-text", "", ""),
            ("nomic-embed-text", "search_query:", "search_document: "),
        ]
        self.assertEqual(len({embed_scheme_id(*v) for v in variants}), len(variants))

    def test_current_scheme_follows_settings(self):
        expected = embed_scheme_id(settings.embedding_model, settings.embed_query_prefix, settings.embed_document_prefix)
        self.assertEqual(current_embed_scheme(), expected)
        with mock.patch.object(settings, "embed_query_prefix", "outro: "):
            self.assertNotEqual(current_embed_scheme(), expected)


if __name__ == "__main__":
    unittest.main()

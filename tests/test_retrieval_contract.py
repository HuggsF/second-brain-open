import unittest
from unittest import mock

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from core.qdrant_store import QdrantStore

VECTOR_SIZE = 4


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


if __name__ == "__main__":
    unittest.main()

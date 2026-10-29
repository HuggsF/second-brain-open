import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, 
    VectorParams, 
    PointStruct, 
    Filter, 
    FieldCondition, 
    MatchValue
)
from qdrant_client import models
from config import settings
from core.embeddings import current_embed_scheme

class QdrantStore:
    def __init__(self, url: str = settings.qdrant_url, collection_name: str = settings.qdrant_collection):
        self.url = url
        self.collection_name = collection_name
        self.client = QdrantClient(url=self.url)

    def ensure_collection(self, vector_size: int = settings.vector_size) -> bool:
        """Cria a colecao se nao existir. Devolve True so quando criou.

        Usa collection_exists (que resolve aliases); get_collections() nao lista
        aliases e criaria uma colecao real homonima do alias.
        """
        if self.client.collection_exists(self.collection_name):
            return False
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )
        return True

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    @staticmethod
    def point_ids(chunks: List[Dict[str, Any]]) -> set:
        """IDs de ponto dos chunks, pela mesma regra de upsert_chunks."""
        return {QdrantStore._point_id(chunk["id"]) for chunk in chunks}

    def delete_stale(self, rel_path: str, keep_ids: set) -> None:
        """Remove os pontos de rel_path cujo ID nao esta em keep_ids."""
        must_not = [models.HasIdCondition(has_id=list(keep_ids))] if keep_ids else None
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[FieldCondition(key="file_path", match=MatchValue(value=rel_path))],
                    must_not=must_not,
                )
            ),
        )

    def indexed_files(self) -> Dict[str, int]:
        """Contagem de pontos por file_path, via scroll paginado."""
        counts: Dict[str, int] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=["file_path"],
                with_vectors=False,
            )
            for point in points:
                file_path = (point.payload or {}).get("file_path")
                if file_path is not None:
                    counts[file_path] = counts.get(file_path, 0) + 1
            if offset is None:
                return counts

    def points_count(self) -> int:
        """Total exato de pontos da coleção (sem scroll)."""
        return self.client.count(collection_name=self.collection_name, exact=True).count

    def legacy_points_count(self, expected_scheme: Optional[str] = None) -> int:
        """Total exato de pontos sem `space_id` (anteriores à onda B) ou de outro esquema de embedding.

        IsEmptyCondition casa chave ausente, null ou lista vazia; o `must_not` do esquema também
        casa pontos sem `embed_scheme`. `expected_scheme` ausente: o esquema da configuração atual.
        """
        scheme = expected_scheme if expected_scheme is not None else current_embed_scheme()
        legacy = models.Filter(
            should=[
                models.IsEmptyCondition(is_empty=models.PayloadField(key="space_id")),
                models.Filter(must_not=[
                    models.FieldCondition(key="embed_scheme", match=models.MatchValue(value=scheme))
                ]),
            ]
        )
        return self.client.count(
            collection_name=self.collection_name, count_filter=legacy, exact=True
        ).count

    def space_points_count(self, space_id: str) -> int:
        """Total exato de pontos com este `space_id`; 0 quando o espaco nao existe ou esta vazio."""
        space_filter = models.Filter(
            must=[FieldCondition(key="space_id", match=MatchValue(value=space_id))]
        )
        return self.client.count(
            collection_name=self.collection_name, count_filter=space_filter, exact=True
        ).count

    def alias_target(self, alias: str) -> Optional[str]:
        for item in self.client.get_aliases().aliases:
            if item.alias_name == alias:
                return item.collection_name
        return None

    def index_version(self) -> str:
        """Colecao real atras do alias (ou o proprio nome, se nao for alias)."""
        return self.alias_target(self.collection_name) or self.collection_name

    def is_real_collection(self, name: str) -> bool:
        return name in [c.name for c in self.client.get_collections().collections]

    def create_named_collection(self, name: str, vector_size: int) -> None:
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )

    def swap_alias(self, alias: str, new_collection: str, has_old_alias: bool) -> None:
        """Aponta o alias para new_collection numa unica chamada atomica."""
        operations = []
        if has_old_alias:
            operations.append(models.DeleteAliasOperation(
                delete_alias=models.DeleteAlias(alias_name=alias)))
        operations.append(models.CreateAliasOperation(
            create_alias=models.CreateAlias(collection_name=new_collection, alias_name=alias)))
        self.client.update_collection_aliases(change_aliases_operations=operations)

    def drop_collection(self, name: str) -> None:
        self.client.delete_collection(collection_name=name)

    def collections_with_prefix(self, prefix: str) -> List[str]:
        return [c.name for c in self.client.get_collections().collections
                if c.name.startswith(prefix)]

    def delete_by_file_path(self, rel_file_path: str) -> None:
        """Remove todos os vetores indexados de um determinado arquivo."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="file_path",
                            match=MatchValue(value=rel_file_path)
                        )
                    ]
                )
            )
        except Exception as e:
            # Antes isto era silencioso e deixava vetores de ficheiros apagados no índice.
            raise RuntimeError(f"Falha ao remover vetores de '{rel_file_path}' do Qdrant: {e}") from e

    def upsert_chunks(self, chunks: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = self._point_id(chunk["id"])
            payload = {
                "chunk_id": chunk["id"],
                "content": chunk["content"],
                **chunk["metadata"]
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def search(
        self, 
        query_vector: List[float], 
        limit: int = 4, 
        category: Optional[str] = None,
        bounded_context: Optional[str] = None,
        space_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        conditions = []
        if space_id is not None:
            conditions.append(FieldCondition(key="space_id", match=MatchValue(value=space_id)))
        if category:
            conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))
        if bounded_context:
            conditions.append(FieldCondition(key="bounded_context", match=MatchValue(value=bounded_context)))
        query_filter = Filter(must=conditions) if conditions else None

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True
        )

        formatted_results = []
        for point in results.points:
            formatted_results.append({
                "score": point.score,
                "payload": point.payload
            })
        return formatted_results

    def get_stats(self) -> Dict[str, Any]:
        try:
            info = self.client.get_collection(collection_name=self.collection_name)
            return {
                "collection": self.collection_name,
                "points_count": info.points_count,
                "status": info.status.name if hasattr(info.status, 'name') else str(info.status)
            }
        except Exception as e:
            return {"error": str(e)}

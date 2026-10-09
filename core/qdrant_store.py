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
from config import settings

class QdrantStore:
    def __init__(self, url: str = settings.qdrant_url, collection_name: str = settings.qdrant_collection):
        self.url = url
        self.collection_name = collection_name
        self.client = QdrantClient(url=self.url)

    def ensure_collection(self, vector_size: int = settings.vector_size) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )

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
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["id"]))
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
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query_filter = None
        if category:
            query_filter = Filter(
                must=[FieldCondition(key="category", match=MatchValue(value=category))]
            )

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

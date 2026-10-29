import hashlib
import json
import httpx
from typing import List, Optional
from config import settings


def embed_scheme_id(model: str, query_prefix: str, document_prefix: str) -> str:
    """Identificador estavel do esquema de embedding (12 hex): muda com o modelo ou qualquer prefixo."""
    raw = json.dumps([model, query_prefix, document_prefix], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def current_embed_scheme() -> str:
    """Esquema da configuracao atual; e o que o sync grava e o que o indice precisa ter."""
    return embed_scheme_id(settings.embedding_model, settings.embed_query_prefix, settings.embed_document_prefix)


class OllamaEmbeddingClient:
    def __init__(self, base_url: str = settings.ollama_url, model: str = settings.embedding_model,
                 query_prefix: Optional[str] = None, document_prefix: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.query_prefix = settings.embed_query_prefix if query_prefix is None else query_prefix
        self.document_prefix = settings.embed_document_prefix if document_prefix is None else document_prefix

    def embed_query(self, text: str) -> List[float]:
        """Vetor de uma pergunta (prefixo de busca)."""
        return self.get_embedding(self.query_prefix + text)

    def embed_document(self, text: str) -> List[float]:
        """Vetor de um trecho do vault (prefixo de documento)."""
        return self.get_embedding(self.document_prefix + text)

    def get_embedding(self, text: str) -> List[float]:
        """
        Gera o vetor de embedding para o texto fornecido utilizando a API do Ollama local.
        Tenta primeiro o endpoint moderno /api/embed e faz fallback para /api/embeddings.
        """
        payload = {
            "model": self.model,
            "input": text
        }
        
        try:
            with httpx.Client(timeout=60.0) as client:
                # Tenta endpoint /api/embed (Ollama >= 0.1.34)
                resp = client.post(f"{self.base_url}/api/embed", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    embeddings = data.get("embeddings")
                    if embeddings and len(embeddings) > 0:
                        return embeddings[0]
                
                # Fallback para endpoint /api/embeddings legado
                legacy_payload = {"model": self.model, "prompt": text}
                resp_legacy = client.post(f"{self.base_url}/api/embeddings", json=legacy_payload)
                if resp_legacy.status_code == 200:
                    return resp_legacy.json().get("embedding", [])
                
                raise RuntimeError(f"Falha ao gerar embedding no Ollama: {resp.text or resp_legacy.text}")
        except Exception as e:
            raise RuntimeError(f"Erro de comunicação com Ollama em {self.base_url}: {e}")

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

import httpx
from typing import List
from config import settings

class OllamaEmbeddingClient:
    def __init__(self, base_url: str = settings.ollama_url, model: str = settings.embedding_model):
        self.base_url = base_url.rstrip("/")
        self.model = model

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

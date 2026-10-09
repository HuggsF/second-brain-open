import httpx
from typing import Dict, Any, List, Optional
from config import settings
from core.embeddings import OllamaEmbeddingClient
from core.qdrant_store import QdrantStore

class BrainRetriever:
    def __init__(self):
        self.embedder = OllamaEmbeddingClient()
        self.store = QdrantStore()

    def query(
        self, 
        user_question: str, 
        limit: int = 4, 
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Recupera os blocos mais relevantes no Qdrant para uma pergunta."""
        query_vector = self.embedder.get_embedding(user_question)
        hits = self.store.search(query_vector=query_vector, limit=limit, category=category)
        
        context_parts = []
        sources = []

        for hit in hits:
            payload = hit["payload"]
            score = hit["score"]
            context_parts.append(
                f"--- Fonte: {payload.get('file_path')} | Seção: {payload.get('section')} (Relevância: {score:.2f}) ---\n"
                f"{payload.get('content')}\n"
            )
            sources.append({
                "file_path": payload.get("file_path"),
                "doc_title": payload.get("doc_title"),
                "section": payload.get("section"),
                "category": payload.get("category"),
                "score": score
            })

        context_text = "\n".join(context_parts)
        return {
            "question": user_question,
            "context": context_text,
            "sources": sources
        }

    def answer(
        self, 
        user_question: str, 
        limit: int = 4, 
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gera resposta via Ollama local com contexto recuperado do Qdrant (RAG)."""
        retrieved = self.query(user_question, limit=limit, category=category)
        
        if not retrieved["sources"]:
            return {
                "answer": "Nenhum documento relevante encontrado na sua base de conhecimento para essa pergunta.",
                "sources": []
            }

        prompt = (
            "Você é o assistente técnico corporativo da holding KIOSK Brands (segundo cérebro local).\n"
            "Responda à pergunta do usuário baseando-se estritamente no contexto técnico fornecido abaixo.\n"
            "Se a informação não estiver clara no contexto, indique honestamente o que falta.\n"
            "Mantenha um tom profissional, técnico e objetivo (nível desenvolvedor pleno).\n\n"
            f"### CONTEXTO RECUPERADO:\n{retrieved['context']}\n\n"
            f"### PERGUNTA DO USUÁRIO:\n{user_question}\n\n"
            "### RESPOSTA TÉCNICA:"
        )

        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{settings.ollama_url}/api/generate",
                    json={
                        "model": settings.chat_model,
                        "prompt": prompt,
                        "stream": False
                    }
                )
                if resp.status_code == 200:
                    answer_text = resp.json().get("response", "").strip()
                else:
                    answer_text = f"Contexto recuperado com sucesso, mas o modelo local retornou código {resp.status_code}."
        except Exception as e:
            answer_text = (
                f"Contexto recuperado com sucesso do Qdrant, porém não foi possível conectar ao chat do Ollama: {e}\n\n"
                f"**Trecho relevante mais próximo:**\n{retrieved['context'][:400]}..."
            )

        return {
            "answer": answer_text,
            "sources": retrieved["sources"]
        }

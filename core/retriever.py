import httpx
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import settings
from core.citations import build_citations, gaps_for, select_hits
from core.embeddings import OllamaEmbeddingClient
from core.qdrant_store import QdrantStore

NO_EVIDENCE_ANSWER = "Nenhum documento relevante encontrado na sua base de conhecimento para essa pergunta."


class BrainRetriever:
    def __init__(self, *, embedder=None, store=None, vault_dir: Optional[Path] = None):
        self.embedder = embedder if embedder is not None else OllamaEmbeddingClient()
        self.store = store if store is not None else QdrantStore()
        self.vault_dir = Path(vault_dir) if vault_dir is not None else settings.vault_dir

    def query(
        self,
        user_question: str,
        limit: int = 4,
        category: Optional[str] = None,
        bounded_context: Optional[str] = None,
        include_content: bool = False,
        apply_floor: bool = True
    ) -> Dict[str, Any]:
        """Recupera os blocos relevantes do espaco atual, com piso, diversidade e citacoes.

        `apply_floor=False` devolve os `limit` primeiros hits brutos (so para a avaliacao).
        """
        query_vector = self.embedder.get_embedding(user_question)
        raw_hits = self.store.search(
            query_vector=query_vector,
            limit=limit * 3,
            category=category,
            bounded_context=bounded_context,
            space_id=settings.space_id,
        )
        top_score = raw_hits[0]["score"] if raw_hits else None
        if apply_floor:
            hits = select_hits(
                raw_hits,
                min_score=settings.retrieval_min_score,
                max_drop=settings.retrieval_max_drop,
                max_per_doc=settings.retrieval_max_per_doc,
                limit=limit,
            )
        else:
            hits = raw_hits[:limit]
        citations = build_citations(hits, self.vault_dir)

        context_parts = []
        sources = []

        for hit, citation in zip(hits, citations):
            payload = hit["payload"]
            score = hit["score"]
            context_parts.append(
                f"--- Fonte: {payload.get('file_path')} | Seção: {payload.get('section')} (Relevância: {score:.2f}) ---\n"
                f"{payload.get('content')}\n"
            )
            source = {
                "file_path": payload.get("file_path"),
                "doc_title": payload.get("doc_title"),
                "section": payload.get("section"),
                "category": payload.get("category"),
                "score": score,
                "sha256": citation.sha256,
                "line_start": citation.line_start,
                "line_end": citation.line_end,
                "stale": citation.stale,
            }
            if include_content:
                source["content"] = payload.get("content", "")
            sources.append(source)

        context_text = "\n".join(context_parts)
        return {
            "question": user_question,
            "context": context_text,
            "sources": sources,
            "citations": [asdict(citation) for citation in citations],
            "gaps": gaps_for(citations, top_score, settings.retrieval_min_score),
            "index_version": self.store.index_version(),
        }

    def answer(
        self,
        user_question: str,
        limit: int = 4,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gera resposta via Ollama local com contexto recuperado do Qdrant (RAG).

        `status`: `ok`, `no_evidence` (sem citacao; o modelo nao e chamado) ou `model_error`.
        """
        retrieved = self.query(user_question, limit=limit, category=category)

        if not retrieved["citations"]:
            return {
                "answer": NO_EVIDENCE_ANSWER,
                "sources": [],
                "status": "no_evidence",
                "citations": [],
                "gaps": retrieved["gaps"],
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
                    status = "ok"
                else:
                    answer_text = f"Contexto recuperado com sucesso, mas o modelo local retornou código {resp.status_code}."
                    status = "model_error"
        except Exception as e:
            answer_text = (
                f"Contexto recuperado com sucesso do Qdrant, porém não foi possível conectar ao chat do Ollama: {e}\n\n"
                f"**Trecho relevante mais próximo:**\n{retrieved['context'][:400]}..."
            )
            status = "model_error"

        return {
            "answer": answer_text,
            "sources": retrieved["sources"],
            "status": status,
            "citations": retrieved["citations"],
            "gaps": retrieved["gaps"],
        }

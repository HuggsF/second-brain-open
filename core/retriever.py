from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import settings
from core.citations import build_citations, gaps_for, select_hits
from core.embeddings import OllamaEmbeddingClient
from core.local_tasks.answer import AnswerResult, default_budget_tracker, generate_answer
from core.qdrant_store import QdrantStore
from core.vault_vocab import unknown_entities, vault_vocabulary

NO_EVIDENCE_ANSWER = "Nenhum documento relevante encontrado na sua base de conhecimento para essa pergunta."


def _profile_generator(system: str, user: str) -> AnswerResult:
    """Gera pela cadeia do perfil ativo, com o orcamento dele; perfil ilegivel vira `model_error`."""
    from core.local_tasks.profile import load_profile
    try:
        profile = load_profile()
    except Exception:
        from core.cost import CostRecord
        return AnswerResult("model_error", None, "profile_not_found", None,
                            CostRecord(model=settings.chat_model, tier="deterministic", tokens_in=0,
                                       tokens_out=0, ms=0, paid_equivalent_usd=0.0))
    return generate_answer(system, user, profile=profile, budget_tracker=default_budget_tracker(profile))


class BrainRetriever:
    def __init__(self, *, embedder=None, store=None, vault_dir: Optional[Path] = None, generator=None):
        self.embedder = embedder if embedder is not None else OllamaEmbeddingClient()
        self.store = store if store is not None else QdrantStore()
        self.vault_dir = Path(vault_dir) if vault_dir is not None else settings.vault_dir
        # generator(system, user) -> AnswerResult; padrao: cadeia de provedores do perfil (ADR-038).
        self.generator = generator if generator is not None else _profile_generator

    def query(
        self,
        user_question: str,
        limit: int = 4,
        category: Optional[str] = None,
        bounded_context: Optional[str] = None,
        include_content: bool = False,
        apply_floor: bool = True,
        entity_gate: bool = True
    ) -> Dict[str, Any]:
        """Recupera os blocos relevantes do espaco atual, com piso, diversidade e citacoes.

        `apply_floor=False` devolve os `limit` primeiros hits brutos (so para a avaliacao) e tambem
        desliga o gate de entidade. Com `entity_gate`, nome proprio da pergunta ausente do vault zera
        a selecao e vira aviso em `gaps`.
        """
        unknown = (unknown_entities(user_question, vault_vocabulary(self.vault_dir))
                   if apply_floor and entity_gate else [])
        query_vector = self.embedder.embed_query(user_question)
        raw_hits = self.store.search(
            query_vector=query_vector,
            limit=limit * 3,
            category=category,
            bounded_context=bounded_context,
            space_id=settings.space_id,
        )
        top_score = raw_hits[0]["score"] if raw_hits else None
        space_has_points = bool(raw_hits) or bool(
            self.store.space_points_count(settings.space_id)
        )
        if apply_floor:
            hits = select_hits(
                raw_hits,
                min_score=settings.retrieval_min_score,
                max_drop=settings.retrieval_max_drop,
                max_per_doc=settings.retrieval_max_per_doc,
                limit=limit,
                unknown=unknown,
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
            "gaps": gaps_for(citations, top_score, settings.retrieval_min_score,
                            space_has_points=space_has_points, unknown=unknown),
            "index_version": self.store.index_version(),
        }

    def answer(
        self,
        user_question: str,
        limit: int = 4,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gera a resposta pela cadeia de provedores do perfil, com o contexto recuperado (RAG, ADR-038).

        `status`: `ok`, `no_evidence` (sem citacao; nenhum provedor e chamado) ou `model_error`
        (todos os provedores da cadeia falharam). `provider` e `cost_usd` dizem quem respondeu e o custo.
        """
        retrieved = self.query(user_question, limit=limit, category=category)

        if not retrieved["citations"]:
            return {
                "answer": NO_EVIDENCE_ANSWER,
                "sources": [],
                "status": "no_evidence",
                "citations": [],
                "gaps": retrieved["gaps"],
                "provider": None,
                "cost_usd": 0.0,
            }

        system = (
            "Você é o assistente técnico corporativo da holding KIOSK Brands (segundo cérebro local).\n"
            "Responda à pergunta do usuário baseando-se estritamente no contexto técnico fornecido.\n"
            "Se a informação não estiver clara no contexto, indique honestamente o que falta.\n"
            "Mantenha um tom profissional, técnico e objetivo (nível desenvolvedor pleno).\n"
            'Devolva JSON no formato {"answer": "<resposta em português>"}.'
        )
        user = (
            f"### CONTEXTO RECUPERADO:\n{retrieved['context']}\n\n"
            f"### PERGUNTA DO USUÁRIO:\n{user_question}"
        )
        generated = self.generator(system, user)
        if generated.status == "ok":
            answer_text = generated.text
        else:
            answer_text = (
                f"Contexto recuperado, mas nenhum provedor de resposta respondeu ({generated.reason}).\n\n"
                f"**Trecho relevante mais próximo:**\n{retrieved['context'][:400]}..."
            )

        return {
            "answer": answer_text,
            "sources": retrieved["sources"],
            "status": generated.status,
            "citations": retrieved["citations"],
            "gaps": retrieved["gaps"],
            "provider": generated.provider,
            "cost_usd": generated.cost.actual_usd,
        }

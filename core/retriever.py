"""Recuperação no índice de texto e resposta gerada por um gerador injetável."""
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx

from config import settings
from core.citations import build_citations, gaps_for, select_hits
from core.indice_texto import IndiceTexto
from core.vault_vocab import unknown_entities, vault_vocabulary

NO_EVIDENCE_ANSWER = "Nenhum documento relevante encontrado na sua base de conhecimento para essa pergunta."
SEM_GERADOR_ANSWER = ("As fontes foram encontradas, mas a resposta não pôde ser gerada: "
                      "o servidor local de modelos não respondeu.")
SISTEMA = (
    "Você é o assistente técnico da organização (segundo cérebro local).\n"
    "Responda à pergunta do usuário baseando-se estritamente no contexto técnico fornecido.\n"
    "Se a informação não estiver clara no contexto, indique honestamente o que falta.\n"
    "Mantenha um tom profissional, técnico e objetivo."
)


class GeradorIndisponivel(RuntimeError):
    """O gerador de resposta não pôde produzir texto (servidor fora do ar, erro ou resposta vazia)."""


def gerador_local(sistema: str, usuario: str) -> str:
    """Gera a resposta no servidor local de modelos; toda falha vira GeradorIndisponivel, sem o erro cru."""
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": settings.chat_model, "system": sistema, "prompt": usuario, "stream": False},
            )
    except httpx.HTTPError as exc:
        raise GeradorIndisponivel("servidor local de modelos inacessível") from exc
    if resp.status_code != 200:
        raise GeradorIndisponivel(f"servidor local de modelos devolveu o código {resp.status_code}")
    try:
        texto = resp.json().get("response")
    except (ValueError, AttributeError) as exc:
        raise GeradorIndisponivel("servidor local de modelos devolveu uma resposta ilegível") from exc
    if not isinstance(texto, str) or not texto.strip():
        raise GeradorIndisponivel("servidor local de modelos devolveu uma resposta vazia")
    return texto.strip()


class BrainRetriever:
    def __init__(self, *, store: Optional[IndiceTexto] = None, vault_dir: Optional[Path] = None,
                 generator: Optional[Callable[[str, str], str]] = None):
        self.store = store if store is not None else IndiceTexto()
        self.vault_dir = Path(vault_dir) if vault_dir is not None else settings.vault_dir
        # generator(sistema, usuario) -> texto; levanta GeradorIndisponivel quando não consegue gerar.
        self.generator = generator if generator is not None else gerador_local

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

        `apply_floor=False` devolve os `limit` primeiros hits sem piso (so para a avaliacao), ja com o
        limite de trechos por documento da busca, e tambem desliga o gate de entidade. Com `entity_gate`, nome proprio da pergunta ausente do vault zera
        a selecao e vira aviso em `gaps`.
        """
        unknown = (unknown_entities(user_question, vault_vocabulary(self.vault_dir))
                   if apply_floor and entity_gate else [])
        raw_hits = self.store.buscar(
            user_question,
            limit=limit * 3,
            category=category,
            bounded_context=bounded_context,
            space_id=settings.space_id,
            per_doc=settings.retrieval_max_per_doc,
        )
        top_score = raw_hits[0]["score"] if raw_hits else None
        space_has_points = bool(raw_hits) or bool(
            self.store.total_trechos(settings.space_id)
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
            "index_version": self.store.versao(),
        }

    def answer(self, user_question: str, limit: int = 4, category: Optional[str] = None) -> Dict[str, Any]:
        """Responde com base no que a busca achou. `status`: ok, sem_fontes ou sem_gerador."""
        achado = self.query(user_question, limit=limit, category=category)
        base = {"sources": achado["sources"], "citations": achado["citations"], "gaps": achado["gaps"]}
        if not achado["sources"]:
            return {"answer": NO_EVIDENCE_ANSWER, "status": "sem_fontes", **base}
        usuario = (
            f"### CONTEXTO RECUPERADO:\n{achado['context']}\n\n"
            f"### PERGUNTA DO USUÁRIO:\n{user_question}\n\n"
            "### RESPOSTA TÉCNICA:"
        )
        try:
            texto = self.generator(SISTEMA, usuario)
        except GeradorIndisponivel:
            return {"answer": SEM_GERADOR_ANSWER, "status": "sem_gerador", **base}
        return {"answer": texto, "status": "ok", **base}

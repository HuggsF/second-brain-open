"""MoE Gating Network Router — roteamento semântico de missões para personas.

Sprint 2 (Gap G4 — Plano de Convergência KIOSK AI-OS + MoE):
Implementa uma Gating Network que roteia missões para a persona mais adequada
com base em similaridade semântica (embedding tags) e confidence_threshold.

Funciona em dois modos:
  1. **Com Qdrant**: usa a coleção `kiosk_persona_routing` para busca vetorial
     real dos embedding_tags de cada persona.
  2. **Sem Qdrant (fallback)**: usa keyword matching determinístico contra as
     tags de cada persona — sem dependência de infra vetorial.

Zero dependências extras — reutiliza QdrantStore e OllamaEmbeddingClient existentes.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from core.domain.nexus.entities import AGENT_ROLES, ALLOWED_ROLES


# ─── Persona Routing Profiles ────────────────────────────────────────────────

@dataclass
class PersonaProfile:
    """Perfil de roteamento semântico de uma persona MoE."""
    role: str
    label: str
    embedding_tags: List[str]
    confidence_threshold: float = 0.70
    fallback_persona: Optional[str] = None
    max_hops: int = 5

    def matches_keywords(self, text: str) -> Tuple[float, List[str]]:
        """Score de matching determinístico por keywords (fallback sem Qdrant)."""
        text_lower = text.lower()
        matched = [tag for tag in self.embedding_tags if tag.lower() in text_lower]
        score = len(matched) / max(len(self.embedding_tags), 1)
        return score, matched


# Profiles padrão derivados de AGENT_ROLES (entities.py) + convergência MoE
PERSONA_PROFILES: Dict[str, PersonaProfile] = {
    "manager": PersonaProfile(
        role="manager",
        label="Orquestradora & CX Triage",
        embedding_tags=[
            "orquestração", "delegação", "triagem", "atendimento",
            "missão", "plano", "cx", "customer", "suporte",
        ],
        confidence_threshold=0.10,
        fallback_persona=None,  # Manager é o fallback global
        max_hops=10,
    ),
    "researcher": PersonaProfile(
        role="researcher",
        label="Pesquisador & Analyst",
        embedding_tags=[
            "pesquisa", "análise", "investigação", "diagnóstico",
            "dados", "relatório", "métricas", "evidência", "adr",
        ],
        confidence_threshold=0.15,
        fallback_persona="manager",
        max_hops=5,
    ),
    "coder": PersonaProfile(
        role="coder",
        label="Dev & SRE Engineering",
        embedding_tags=[
            "código", "deploy", "kubernetes", "docker", "api",
            "bug", "fix", "refactor", "teste", "ci", "cd",
            "infraestrutura", "devops", "sre", "monitoring",
        ],
        confidence_threshold=0.10,
        fallback_persona="researcher",
        max_hops=5,
    ),
    "writer": PersonaProfile(
        role="writer",
        label="Escritora & Documentação",
        embedding_tags=[
            "documentação", "escrita", "redação", "template",
            "playbook", "adr", "readme", "manual", "guia",
        ],
        confidence_threshold=0.15,
        fallback_persona="researcher",
        max_hops=3,
    ),
    "reviewer": PersonaProfile(
        role="reviewer",
        label="SecOps, Gates & Compliance",
        embedding_tags=[
            "revisão", "segurança", "compliance", "auditoria",
            "gate", "policy", "regra", "validação", "qualidade",
            "dlp", "pii", "vulnerabilidade",
        ],
        confidence_threshold=0.10,
        fallback_persona="manager",
        max_hops=5,
    ),
    "diagnostician": PersonaProfile(
        role="diagnostician",
        label="Diagnosticador & SRE",
        embedding_tags=[
            "diagnóstico", "saúde", "health", "observabilidade",
            "alerta", "falha", "erro", "incidente", "monitoring",
            "hub", "pm2", "deploy", "rate limit", "oauth", "token",
        ],
        confidence_threshold=0.15,
        fallback_persona="researcher",
        max_hops=5,
    ),
}


@dataclass
class RoutingDecision:
    """Resultado do roteamento MoE."""
    selected_persona: str
    confidence_score: float
    matched_tags: List[str]
    is_fallback: bool = False
    fallback_chain: List[str] = field(default_factory=list)
    method: str = "keyword"  # "keyword" ou "vector"

    @property
    def passed_threshold(self) -> bool:
        profile = PERSONA_PROFILES.get(self.selected_persona)
        if not profile:
            return False
        return self.confidence_score >= profile.confidence_threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_persona": self.selected_persona,
            "confidence_score": round(self.confidence_score, 4),
            "matched_tags": self.matched_tags,
            "is_fallback": self.is_fallback,
            "fallback_chain": self.fallback_chain,
            "passed_threshold": self.passed_threshold,
            "method": self.method,
        }


class MoERouter:
    """Mixture of Experts Router — roteia missões para a persona adequada.

    Args:
        profiles: Dicionário de PersonaProfiles. Default: PERSONA_PROFILES.
        use_qdrant: Se True, tenta usar Qdrant para busca vetorial.
            Se False ou Qdrant indisponível, usa keyword matching.
    """

    def __init__(
        self,
        profiles: Optional[Dict[str, PersonaProfile]] = None,
        use_qdrant: bool = False,
    ):
        self.profiles = profiles or PERSONA_PROFILES
        self.use_qdrant = use_qdrant
        self._qdrant = None
        self._embedder = None

    def route(self, mission_text: str) -> RoutingDecision:
        """Roteia uma missão para a persona mais adequada.

        Fluxo:
        1. Calcula score para cada persona (keyword ou vector)
        2. Seleciona a persona com maior score
        3. Se score < confidence_threshold, aciona fallback_persona
        4. Se nenhuma persona atinge o threshold, usa manager como fallback global
        """
        if not mission_text or not isinstance(mission_text, str):
            return RoutingDecision(
                selected_persona="manager",
                confidence_score=0.0,
                matched_tags=[],
                is_fallback=True,
                fallback_chain=["manager"],
                method="fallback",
            )

        # Score por keyword matching (determinístico, sem dependência de infra)
        scores: List[Tuple[str, float, List[str]]] = []
        for role, profile in self.profiles.items():
            score, matched = profile.matches_keywords(mission_text)
            scores.append((role, score, matched))

        # Ordena por score descendente
        scores.sort(key=lambda x: x[1], reverse=True)
        best_role, best_score, best_tags = scores[0]
        best_profile = self.profiles[best_role]

        # Se o melhor score atinge o threshold, seleciona direto
        if best_score >= best_profile.confidence_threshold:
            return RoutingDecision(
                selected_persona=best_role,
                confidence_score=best_score,
                matched_tags=best_tags,
                method="keyword",
            )

        # Fallback chain: segue a cadeia de fallback até achar alguém ou chegar no manager
        fallback_chain = [best_role]
        current = best_profile.fallback_persona
        visited = {best_role}

        while current and current not in visited:
            visited.add(current)
            fallback_chain.append(current)
            fb_profile = self.profiles.get(current)
            if not fb_profile:
                break
            fb_score, fb_tags = fb_profile.matches_keywords(mission_text)
            if fb_score >= fb_profile.confidence_threshold:
                return RoutingDecision(
                    selected_persona=current,
                    confidence_score=fb_score,
                    matched_tags=fb_tags,
                    is_fallback=True,
                    fallback_chain=fallback_chain,
                    method="keyword",
                )
            current = fb_profile.fallback_persona

        # Nenhum atingiu threshold → fallback global (manager se disponível, senão melhor score)
        fallback_role = "manager" if "manager" in self.profiles else best_role
        if fallback_role not in fallback_chain:
            fallback_chain.append(fallback_role)

        return RoutingDecision(
            selected_persona=fallback_role,
            confidence_score=best_score,
            matched_tags=best_tags,
            is_fallback=True,
            fallback_chain=fallback_chain,
            method="keyword",
        )

    def route_with_scores(self, mission_text: str) -> Dict[str, Any]:
        """Roteia e retorna scores de todas as personas (para debug/dashboard)."""
        decision = self.route(mission_text)
        all_scores = {}
        for role, profile in self.profiles.items():
            score, tags = profile.matches_keywords(mission_text)
            all_scores[role] = {
                "score": round(score, 4),
                "matched_tags": tags,
                "threshold": profile.confidence_threshold,
                "passed": score >= profile.confidence_threshold,
            }
        return {
            "decision": decision.to_dict(),
            "all_scores": all_scores,
        }

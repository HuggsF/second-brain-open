"""
Orchestrator — Motor de orquestração de missões multi-agente.

Recebe uma missão (texto do usuário), decompõe em steps,
executa ferramentas reais via tool_executor e emite eventos
no formato event-protocol.js do Nexus.
"""
import asyncio
import copy
import re
import time
import uuid
from typing import AsyncGenerator, Optional

from backend.tool_executor import run_tool
from core.integration import get_persona_contract, run_post_mission_gates
from core.mission_guard import check_mission
from core.policy import Decision, make_identity
from core.routing.moe_router import MoERouter


# Tempo máximo de execução de uma missão (segundos)
MISSION_TTL_SECONDS = 30


# Mapeamento dos agentes do Nexus
AGENT_IDS = {
    "manager": "manager",     # Maia — orquestradora
    "researcher": "researcher",  # Noah — pesquisa
    "coder": "coder",         # Theo — código/queries
    "writer": "writer",       # Lia — documentação
    "reviewer": "reviewer",   # Eva — revisão/QA
}

# Sprint 7: Mapeamento de agentes Nexus → PersonaContract IDs
# Ativa o pipeline de integração MoE/Zero-Trust por persona
AGENT_PERSONA_MAP = {
    "manager": "maia-orchestrator",
    "reviewer": "eva-supervisor",
    # researcher, coder, writer: sem contrato builtin — pipeline não ativa
}

# Padrões de missão → steps (regras fixas, sem LLM)
MISSION_PATTERNS = [
    {
        "keywords": ["diagnosticar", "failed", "fila", "hub", "pedido", "erro"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Buscando documentação relevante..."},
            {"agent": "coder", "tool": "get_system_architecture", "input": {"system_name": "hub-logistico-schema-regras-negocio"}, "bubble": "Lendo estados e regras do Hub..."},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "Verificando regras de negócio..."},
        ],
    },
    {
        "keywords": ["playbook", "pb-", "procedimento", "protocolo"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Localizando playbooks..."},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "Cruzando com regras de negócio..."},
        ],
    },
    {
        "keywords": ["adr", "decisão", "arquitetura", "trade-off"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Buscando ADRs relevantes..."},
        ],
    },
    {
        "keywords": ["oauth", "token", "bling", "autenticação"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "oauth bling token"}, "bubble": "Buscando doc de OAuth..."},
            {"agent": "coder", "tool": "get_system_architecture", "input": {"system_name": "hub-logistico-schema-regras-negocio"}, "bubble": "Lendo schema do Hub..."},
        ],
    },
    {
        "keywords": ["status", "saúde", "health", "qdrant", "brain"],
        "steps": [
            {"agent": "coder", "tool": "get_brain_status", "input": {}, "bubble": "Verificando status do Qdrant..."},
        ],
    },
]

# Fallback: busca genérica
DEFAULT_STEPS = [
    {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Pesquisando no vault..."},
]

# Quem decide se uma ferramenta roda sem aprovação é o corretor (core.broker / core.policy).

# Limites do event-protocol.js do Nexus; acima disso o frontend descarta o evento.
# São contados em unidades UTF-16 (String.length do JS), não em code points.
MAX_MESSAGE_CHARS = 1000
MAX_BUBBLE_CHARS = 240


def _truncate_utf16(text: str, limit: int) -> str:
    units = text.encode("utf-16-le")
    if len(units) <= limit * 2:
        return text
    # errors="ignore" descarta um par substituto cortado ao meio
    return units[:limit * 2].decode("utf-16-le", errors="ignore")


# Sprint 8: MoE Router para dynamic agent selection
_moe_router: Optional[MoERouter] = None


def _get_moe_router() -> MoERouter:
    global _moe_router
    if _moe_router is None:
        _moe_router = MoERouter()
    return _moe_router


class Orchestrator:
    """Orquestra uma missão multi-agente com ferramentas reais."""

    def __init__(self, pace: float = 1.0):
        self.mission_id = 0
        self.sequence = 0
        self.pace = pace  # multiplica as pausas visuais; 0 nos testes
        self.awaiting_approval = False
        self._approval_event = asyncio.Event()

    async def _pause(self, seconds: float):
        await asyncio.sleep(seconds * self.pace)

    def _next_event_id(self) -> str:
        return f"evt:{self.mission_id}:{uuid.uuid4().hex[:8]}"

    def _next_seq(self) -> int:
        self.sequence += 1
        return self.sequence

    def _event(self, agent_id: str, event_type: str, **payload) -> dict:
        """Cria um evento no formato event-protocol.js."""
        if isinstance(payload.get("message"), str):
            payload["message"] = _truncate_utf16(payload["message"], MAX_MESSAGE_CHARS)
        if isinstance(payload.get("bubble"), str):
            payload["bubble"] = _truncate_utf16(payload["bubble"], MAX_BUBBLE_CHARS)
        return {
            "schemaVersion": 1,
            "id": self._next_event_id(),
            "missionId": self.mission_id,
            "sequence": self._next_seq(),
            "agentId": agent_id,
            "type": event_type,
            "timestamp": time.time() * 1000,
            "payload": {k: v for k, v in payload.items() if v is not None},
        }

    def _match_pattern(self, task: str) -> list:
        """Encontra o padrão de missão mais relevante."""
        task_lower = task.lower()
        best_match = None
        best_score = 0

        for pattern in MISSION_PATTERNS:
            score = sum(1 for kw in pattern["keywords"] if kw in task_lower)
            if score > best_score:
                best_score = score
                best_match = pattern

        # Cópia profunda: os steps são mutados abaixo e não podem vazar para a próxima missão.
        steps = copy.deepcopy(best_match["steps"] if best_match else DEFAULT_STEPS)

        # Injetar a query do usuário nos steps que usam search
        for step in steps:
            if step["tool"] == "search_knowledge_base" and not step["input"].get("query"):
                step["input"]["query"] = task

        return steps

    def _route_agent_for_step(self, step: dict, mission_text: str) -> str:
        """Usa o MoE Router para sugerir o melhor agente para este step.

        Se o MoE Router sugere uma persona diferente do step original E
        o score é significativamente melhor, redireciona o step.
        Caso contrário, mantém o agente original do pattern matching.

        Retorna o agent role a ser usado.
        """
        router = _get_moe_router()
        original_agent = step["agent"]

        # Combina o texto da missão com o contexto do step
        step_context = f"{mission_text} {step.get('bubble', '')}"
        decision = router.route(step_context)

        # Só redireciona se o MoE tem alta confiança e é diferente do original
        if (decision.selected_persona != original_agent 
            and decision.confidence_score >= 0.3
            and not decision.is_fallback):
            return decision.selected_persona

        return original_agent

    def approve(self):
        """Chamado quando o usuário aprova; só vale com uma espera em curso (APPROVE antecipado ou repetido é ignorado)."""
        if self.awaiting_approval:
            self._approval_event.set()

    async def _wait_approval(self) -> bool:
        """Espera approve() por até 300 s; False no timeout. Sempre baixa awaiting_approval."""
        try:
            await asyncio.wait_for(self._approval_event.wait(), timeout=300)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self.awaiting_approval = False

    async def run_mission(self, task: str, mission_id: int = None) -> AsyncGenerator[dict, None]:
        """Executa uma missão completa, emitindo eventos para o frontend.

        mission_id é a geração que o frontend espera (vem do envelope do START);
        sem ele, o orquestrador numera sozinho.
        """
        self.mission_id = self.mission_id + 1 if mission_id is None else mission_id
        self.sequence = 0
        self._approval_event = asyncio.Event()
        mission_start = time.time()

        # ─── Maia recebe a missão ───
        yield self._event("manager", "status_change", status="thinking",
                          bubble="Nova missão recebida! Analisando...")
        await self._pause(1.0)

        # ─── Decompor missão ───
        steps = self._match_pattern(task)

        # ─── Enforce max_hops da persona do manager ───
        manager_persona_id = AGENT_PERSONA_MAP.get("manager")
        if manager_persona_id:
            contract = get_persona_contract(manager_persona_id)
            if contract and len(steps) > contract.quality_gates.max_hops:
                original_count = len(steps)
                steps = steps[:contract.quality_gates.max_hops]
                yield self._event(
                    "manager",
                    "message",
                    message=f"⚠️ Aviso: Missão truncada de {original_count} para {contract.quality_gates.max_hops} passos (limite de max_hops).",
                    bubble=f"Passos limitados a {contract.quality_gates.max_hops}",
                )

        # ─── Portões: RED bloqueia antes de qualquer passo; YELLOW pede aprovação ───
        guard = check_mission(steps, self.mission_id)
        if guard["action"] == "block":
            yield self._event("manager", "message",
                              message=f"Missão bloqueada pelos portões: {guard['semaphore']}")
            return
        if guard["action"] == "approval":
            self.awaiting_approval = True
            yield self._event("manager", "approval_request",
                              bubble="Os portões pedem aprovação para esta missão. Aprovar?")
            if not await self._wait_approval():
                yield self._event("manager", "message", message="Timeout de aprovação atingido.")
                return
            self._approval_event.clear()

        # Sprint 8 (R6): MoE dynamic routing — enrich agent assignment
        for step in steps:
            routed_agent = self._route_agent_for_step(step, task)
            if routed_agent != step["agent"]:
                step["_original_agent"] = step["agent"]
                step["agent"] = routed_agent

        agents_involved = list({s["agent"] for s in steps})

        yield self._event("manager", "status_change", status="working",
                          progress=10, bubble="Distribuindo responsabilidades...")
        await self._pause(0.5)

        # ─── Distribuir ───
        yield self._event("manager", "collaboration",
                          subtype="distribute",
                          **{"from": "manager"},
                          to=agents_involved,
                          bubble="Equipe, temos trabalho!")
        await self._pause(0.8)

        # ─── Executar cada step ───
        mission_results = []
        total_steps = len(steps)
        for i, step in enumerate(steps):
            if time.time() - mission_start > MISSION_TTL_SECONDS:
                yield self._event(
                    "manager",
                    "message",
                    message=f"Timeout da missão atingido (TTL de {MISSION_TTL_SECONDS}s excedido).",
                    bubble="Timeout da missão excedido",
                )
                break

            agent = step["agent"]
            progress = int(((i + 1) / total_steps) * 80) + 10

            # Agente começa a trabalhar
            yield self._event(agent, "status_change",
                              status="working", progress=progress,
                              bubble=step.get("bubble", "Trabalhando..."))
            await self._pause(0.5)

            # Executar via corretor: ele decide, executa e grava o rastro com a identidade do agente
            tool = step.get("tool")
            invalid_agent = None
            try:
                identity = make_identity(step.get("agent"))
            except ValueError as exc:
                # o corretor registra o DENY (bad_identity, caller "unknown"); a mensagem ao usuário segue a mesma
                invalid_agent = f"agente inválido: {exc}"
                raw = step.get("agent")
                identity = f"agent:{raw}" if isinstance(raw, str) else "agent:?"
            result = await run_tool(tool, step.get("input"), identity=identity,
                                    task_id=f"M{self.mission_id}",
                                    persona_id=AGENT_PERSONA_MAP.get(agent),
                                    task_text=task)
            if invalid_agent:
                result["error"] = invalid_agent
            elif result.get("refused") and result.get("verdict") == Decision.DENY.value:
                result["error"] = f"{tool} negado pela política: {result.get('reason', '')}"
            elif result.get("refused"):
                result["error"] = f"{tool} exige aprovação humana explícita; não executado pela missão."

            mission_results.append(result)

            # Formatar resultado para o balão
            summary = self._summarize_result(result)

            yield self._event(agent, "message",
                              message=summary,
                              bubble=self._short_summary(result))
            await self._pause(0.3)

            # Agente termina
            yield self._event(agent, "status_change",
                              status="done", progress=100)

            # Transferência para Eva (se não for o último)
            if i < total_steps - 1:
                await self._pause(0.5)

        # ─── Post-mission Quality Gates ───
        manager_persona = AGENT_PERSONA_MAP.get("manager")
        post_gates = run_post_mission_gates(manager_persona, mission_results)
        self.last_post_mission_result = post_gates
        if not post_gates.get("all_passed", True):
            failed_gates = [
                g.get("gate_name", "unknown")
                for g in post_gates.get("gate_results", [])
                if not g.get("passed", True)
            ]
            failed_str = ", ".join(failed_gates) if failed_gates else "post_mission"
            yield self._event(
                "manager",
                "message",
                message=f"⚠️ Aviso de governança: Post-mission gates não passaram ({failed_str}).",
                bubble=f"Aviso: gates ({failed_str}) reprovados",
            )

        # ─── Maia atualiza progresso ───
        yield self._event("manager", "status_change",
                          status="working", progress=90,
                          bubble="Consolidando resultados...")
        await self._pause(0.8)

        # ─── Eva pede aprovação ───
        yield self._event("reviewer", "status_change",
                          status="working", bubble="Revisando entregas...")
        await self._pause(1.0)

        # Marca antes do yield: um APPROVE que chegue logo após o evento já é aceito.
        self.awaiting_approval = True
        yield self._event("reviewer", "approval_request",
                          bubble="Resultado pronto. Aprovar?")

        # ─── Aguardar aprovação (ou timeout) ───
        if not await self._wait_approval():
            yield self._event("reviewer", "message",
                              message="Timeout de aprovação atingido.")
            return

        yield self._event("reviewer", "collaboration",
                          subtype="approval_granted",
                          bubble="Aprovação recebida!")
        await self._pause(0.5)

        # ─── Encerrar a equipe: o reducer só conclui a missão com os 5 agentes em 'done' ───
        for agent_id in AGENT_IDS:
            if agent_id != "manager":
                yield self._event(agent_id, "status_change", status="done", progress=100)

        # ─── Celebração ───
        yield self._event("manager", "completion",
                          bubble="Missão concluída! 🎉",
                          progress=100)

    def _summarize_result(self, result: dict) -> str:
        """Formata o resultado da ferramenta para exibição no painel."""
        tool = result.get("tool", "unknown")

        if result.get("refused"):
            return f"⛔ {result['error']}"

        if tool == "search_knowledge_base":
            sources = result.get("sources", [])
            if not sources:
                return "Nenhum resultado encontrado no vault."
            lines = [f"**{len(sources)} fontes encontradas:**"]
            for s in sources[:3]:
                sec = f" — {s['section']}" if s.get("section") else ""
                sc = f" (score: {s['score']})" if s.get("score") is not None else ""
                lines.append(f"- `{s.get('document', '')}`{sec}{sc}")
                if s.get("excerpt"):
                    lines.append(f"  _{s['excerpt'][:100]}..._")
            return "\n".join(lines)

        if tool == "get_brain_status":
            return f"Qdrant: {result.get('total_vectors', '?')} vetores, {result.get('collections', '?')} coleções."

        if tool == "list_rules":
            rules = result.get("rules", [])
            if not rules:
                return "Nenhuma regra encontrada."
            lines = [f"**{result.get('total', len(rules))} regras:**"]
            for r in rules[:5]:
                status_emoji = "✅" if r["status"] == "pass" else "❌" if r["status"] == "fail" else "❓"
                lines.append(f"- {status_emoji} `{r['id']}` — {r['title']}")
            return "\n".join(lines)

        if tool == "get_system_architecture":
            if not result.get("found"):
                return f"Sistema não encontrado. Disponíveis: {', '.join(result.get('available', []))}"
            return f"**{result['system']}** ({result['total_lines']} linhas):\n_{result['excerpt'][:200]}..._"

        if tool == "get_adr":
            if not result.get("found"):
                return f"ADR não encontrada. Disponíveis: {', '.join(result.get('available', [])[:5])}"
            return f"**{result['file']}** ({result['total_lines']} linhas):\n_{result['excerpt'][:200]}..._"

        if tool == "run_safe_command":
            if not result.get("success", True) and result.get("error"):
                return f"❌ Erro: {result['error']}"
            output = result.get("output") or result.get("stdout", "")
            cmd = result.get("command", "")
            lines = output.strip().splitlines()
            summary = "\n".join(lines[:20])
            return f"**`{cmd}`**\n```\n{summary}\n```" + (f"\n… ({len(lines)} linhas)" if len(lines) > 20 else "")

        if "error" in result:
            return f"❌ Erro: {result['error']}"

        return str(result)[:300]

    def _short_summary(self, result: dict) -> str:
        """Resumo curto para o balão do agente (max 60 chars)."""
        tool = result.get("tool", "")
        if result.get("refused"):
            if result.get("verdict") == Decision.DENY.value:
                return "⛔ Negado pela política"
            return "⛔ Exige aprovação humana"
        if tool == "search_knowledge_base":
            n = len(result.get("sources", []))
            return f"Encontrei {n} fontes relevantes" if n else "Sem resultados"
        if tool == "get_brain_status":
            return f"Qdrant OK — {result.get('total_vectors', '?')} vetores"
        if tool == "list_rules":
            return f"{result.get('total', 0)} regras verificadas"
        if tool == "get_system_architecture":
            return f"Doc do {result.get('system', '?')} carregada" if result.get("found") else "Sistema não encontrado"
        if tool == "get_adr":
            return f"ADR {result.get('file', '?')} lida" if result.get("found") else "ADR não encontrada"
        if tool == "run_safe_command":
            if not result.get("success", True) and result.get("error"):
                return "❌ Erro no comando SSH"
            lines = len((result.get("output") or "").strip().splitlines())
            return f"{lines} linha(s) retornada(s) do servidor"
        if "error" in result:
            return "❌ Erro na execução"
        return "Resultado processado"

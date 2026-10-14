"""
Orchestrator — Motor de orquestração de missões multi-agente.

Recebe uma missão (texto do usuário), decompõe em steps,
executa ferramentas reais via tool_executor e emite eventos
no formato event-protocol.js do Nexus.
"""
import asyncio
import copy
import uuid
import re
from typing import AsyncGenerator

from backend.tool_executor import run_tool
from core.mission_guard import check_mission
from core.policy import Decision, make_identity


# Mapeamento dos agentes do Nexus
AGENT_IDS = {
    "manager": "manager",     # Maia — orquestradora
    "researcher": "researcher",  # Noah — pesquisa
    "coder": "coder",         # Theo — código/queries
    "writer": "writer",       # Lia — documentação
    "reviewer": "reviewer",   # Eva — revisão/QA
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
        import time
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

    def approve(self):
        """Chamado quando o usuário aprova a entrega."""
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

        # ─── Maia recebe a missão ───
        yield self._event("manager", "status_change", status="thinking",
                          bubble="Nova missão recebida! Analisando...")
        await self._pause(1.0)

        # ─── Decompor missão ───
        steps = self._match_pattern(task)

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
        total_steps = len(steps)
        for i, step in enumerate(steps):
            agent = step["agent"]
            progress = int(((i + 1) / total_steps) * 80) + 10

            # Agente começa a trabalhar
            yield self._event(agent, "status_change",
                              status="working", progress=progress,
                              bubble=step.get("bubble", "Trabalhando..."))
            await self._pause(0.5)

            # Executar via corretor: ele decide, executa e grava o rastro com a identidade do agente
            tool = step.get("tool")
            try:
                identity = make_identity(step.get("agent"))
            except ValueError as exc:
                result = {"tool": str(tool), "refused": True, "error": f"agente inválido: {exc}"}
            else:
                result = await run_tool(tool, step.get("input"), identity=identity,
                                        task_id=f"M{self.mission_id}")
                if result.get("refused") and result.get("verdict") == Decision.DENY.value:
                    result["error"] = f"{tool} negado pela política: {result.get('reason', '')}"
                elif result.get("refused"):
                    result["error"] = f"{tool} exige aprovação humana explícita; não executado pela missão."

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
                lines.append(f"- `{s['document']}` — {s['section']} (score: {s['score']})")
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

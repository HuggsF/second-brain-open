"""
Orchestrator — Motor de orquestração de missões multi-agente.

Recebe uma missão (texto do usuário), decompõe em steps,
executa ferramentas reais via tool_executor e emite eventos
no formato event-protocol.js do Nexus.
"""
import asyncio
import uuid
import re
from typing import AsyncGenerator

from backend.tool_executor import execute as exec_tool


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
            {"agent": "coder", "tool": "run_safe_command", "input": {"command": "sqlite3 /opt/hub-logistico/hub.db \"SELECT situacao, COUNT(*) as total FROM pedidos GROUP BY situacao ORDER BY total DESC LIMIT 10\""}, "bubble": "Consultando fila de pedidos no Hub..."},
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


class Orchestrator:
    """Orquestra uma missão multi-agente com ferramentas reais."""

    def __init__(self):
        self.mission_id = 0
        self.sequence = 0
        self._approval_event = asyncio.Event()

    def _next_event_id(self) -> str:
        return f"evt:{self.mission_id}:{uuid.uuid4().hex[:8]}"

    def _next_seq(self) -> int:
        self.sequence += 1
        return self.sequence

    def _event(self, agent_id: str, event_type: str, **payload) -> dict:
        """Cria um evento no formato event-protocol.js."""
        import time
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

        steps = (best_match["steps"] if best_match else DEFAULT_STEPS).copy()

        # Injetar a query do usuário nos steps que usam search
        for step in steps:
            if step["tool"] == "search_knowledge_base" and not step["input"].get("query"):
                step["input"]["query"] = task

        return [dict(s) for s in steps]

    def approve(self):
        """Chamado quando o usuário aprova a entrega."""
        self._approval_event.set()

    async def run_mission(self, task: str) -> AsyncGenerator[dict, None]:
        """Executa uma missão completa, emitindo eventos para o frontend."""
        self.mission_id += 1
        self.sequence = 0
        self._approval_event = asyncio.Event()

        # ─── Maia recebe a missão ───
        yield self._event("manager", "status_change", status="thinking",
                          bubble="Nova missão recebida! Analisando...")
        await asyncio.sleep(1.0)

        # ─── Decompor missão ───
        steps = self._match_pattern(task)
        agents_involved = list({s["agent"] for s in steps})

        yield self._event("manager", "status_change", status="working",
                          progress=10, bubble="Distribuindo responsabilidades...")
        await asyncio.sleep(0.5)

        # ─── Distribuir ───
        yield self._event("manager", "collaboration",
                          subtype="distribute",
                          from_="manager",
                          to=agents_involved,
                          bubble="Equipe, temos trabalho!")
        await asyncio.sleep(0.8)

        # ─── Executar cada step ───
        total_steps = len(steps)
        for i, step in enumerate(steps):
            agent = step["agent"]
            progress = int(((i + 1) / total_steps) * 80) + 10

            # Agente começa a trabalhar
            yield self._event(agent, "status_change",
                              status="working", progress=progress,
                              bubble=step.get("bubble", "Trabalhando..."))
            await asyncio.sleep(0.5)

            # Executar ferramenta real
            result = await exec_tool(step["tool"], **step["input"])

            # Formatar resultado para o balão
            summary = self._summarize_result(result)

            yield self._event(agent, "message",
                              message=summary,
                              bubble=self._short_summary(result))
            await asyncio.sleep(0.3)

            # Agente termina
            yield self._event(agent, "status_change",
                              status="done", progress=100)

            # Transferência para Eva (se não for o último)
            if i < total_steps - 1:
                await asyncio.sleep(0.5)

        # ─── Maia atualiza progresso ───
        yield self._event("manager", "status_change",
                          status="working", progress=90,
                          bubble="Consolidando resultados...")
        await asyncio.sleep(0.8)

        # ─── Eva pede aprovação ───
        yield self._event("reviewer", "status_change",
                          status="working", bubble="Revisando entregas...")
        await asyncio.sleep(1.0)

        yield self._event("reviewer", "approval_request",
                          bubble="Resultado pronto. Aprovar?")

        # ─── Aguardar aprovação (ou timeout) ───
        try:
            await asyncio.wait_for(self._approval_event.wait(), timeout=300)
        except asyncio.TimeoutError:
            yield self._event("reviewer", "message",
                              message="Timeout de aprovação atingido.")
            return

        yield self._event("reviewer", "collaboration",
                          subtype="approval_granted",
                          bubble="Aprovação recebida!")
        await asyncio.sleep(0.5)

        # ─── Celebração ───
        yield self._event("manager", "completion",
                          bubble="Missão concluída! 🎉",
                          progress=100)

    def _summarize_result(self, result: dict) -> str:
        """Formata o resultado da ferramenta para exibição no painel."""
        tool = result.get("tool", "unknown")

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

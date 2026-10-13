"""
Tool Executor — Ponte entre o Orquestrador e as ferramentas MCP/Qdrant/SSH.

Cada ferramenta é exposta como uma função async que retorna um dict com resultado.
O executor não importa os MCP servers diretamente — chama as funções core.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import re
import os

from core.retriever import BrainRetriever
from core.qdrant_store import QdrantStore
from core import evidence
from core.evidence_store import EvidenceStore
from config import settings

# ── SSH config (mesmas vars do srv_api_gateway_mcp) ──────────────────────────
_SSH_HOST = os.getenv("SRV_API_HOST", "191.233.18.195")
_SSH_USER = os.getenv("SRV_API_USER", "ti-kiosk")
_SSH_PORT = int(os.getenv("SRV_API_PORT", "22"))
_SSH_KEY  = os.getenv("SRV_API_KEY_PATH", r"C:\KIOSK\SRV-API_key.pem")
_SHELL_META = re.compile(r"[;&|<>`$(){}\\\n\r]")
_READ_ONLY = {
    "ls", "cat", "head", "tail", "ps", "df", "du", "free", "uptime",
    "hostname", "uname", "whoami", "date", "journalctl", "grep",
    "wc", "docker", "systemctl", "find", "sqlite3",
}


async def search_knowledge(query: str, category: str = None) -> dict:
    """Busca vetorial no Qdrant."""
    retriever = BrainRetriever()
    result = retriever.query(query, limit=5, category=category)
    sources = result.get("sources", [])
    return {
        "tool": "search_knowledge_base",
        "query": query,
        "total": len(sources),
        "sources": [
            {
                "document": s.get("document", ""),
                "section": s.get("section", ""),
                "score": round(s.get("score", 0), 3),
                "excerpt": (s.get("content", "") or "")[:200],
            }
            for s in sources
        ],
    }


async def get_adr(identifier: str) -> dict:
    """Recupera uma ADR pelo número ou nome."""
    adrs_dir = settings.adrs_dir
    matches = list(adrs_dir.glob(f"*{identifier}*.md"))
    if not matches:
        all_adrs = [f.name for f in adrs_dir.glob("*.md")]
        return {"tool": "get_adr", "found": False, "available": all_adrs}
    content = matches[0].read_text(encoding="utf-8")
    return {
        "tool": "get_adr",
        "found": True,
        "file": matches[0].name,
        "excerpt": content[:500],
        "total_lines": content.count("\n"),
    }


async def get_brain_status() -> dict:
    """Status do Qdrant."""
    store = QdrantStore()
    stats = store.get_stats()
    return {"tool": "get_brain_status", **stats}


async def list_rules_with_evidence() -> dict:
    """Lista regras de negócio com evidências."""
    try:
        rules = evidence.list_rules(evidence.load_definitions(), EvidenceStore())
        return {
            "tool": "list_rules",
            "total": len(rules),
            "rules": [
                {
                    "id": r.get("id", ""),
                    "title": r.get("title", ""),
                    "status": r.get("last_result", "unknown"),
                }
                for r in rules[:10]
            ],
        }
    except Exception as exc:
        return {"tool": "list_rules", "error": str(exc)}


async def get_system_doc(system_name: str) -> dict:
    """Documentação de um sistema."""
    name = (system_name or "").lower().strip()
    system_file = settings.systems_dir / f"{name}.md"
    if not system_file.exists():
        available = [f.stem for f in settings.systems_dir.glob("*.md")]
        return {"tool": "get_system_architecture", "found": False, "available": available}
    content = system_file.read_text(encoding="utf-8")
    return {
        "tool": "get_system_architecture",
        "found": True,
        "system": name,
        "excerpt": content[:500],
        "total_lines": content.count("\n"),
    }


async def read_vault_file(path: str) -> dict:
    """Lê um arquivo do vault."""
    vault = settings.vault_dir
    target = (vault / path).resolve()
    if not target.is_relative_to(vault.resolve()) or not target.is_file():
        return {"tool": "read_vault_file", "found": False, "path": path}
    content = target.read_text(encoding="utf-8")
    return {
        "tool": "read_vault_file",
        "found": True,
        "path": path,
        "lines": content.count("\n"),
        "excerpt": content[:800],
    }



async def run_safe_command(command: str) -> dict:
    """Executa comando de inspeção (só-leitura) no servidor via SSH.

    Aceita: ls, cat, head, tail, ps, df, du, free, uptime, hostname,
    uname, whoami, date, journalctl, grep, wc, docker, systemctl, find,
    sqlite3. Sem encadeamento de shell (;, &, |, <, >, etc.).
    """
    if _SHELL_META.search(command or ""):
        return {"tool": "run_safe_command", "success": False,
                "error": "Encadeamento de shell não permitido (;, &, |, <, >, etc.)"}

    parts = (command or "").split()
    if not parts:
        return {"tool": "run_safe_command", "success": False, "error": "Comando vazio"}

    prog = parts[0]
    if prog not in _READ_ONLY:
        return {"tool": "run_safe_command", "success": False,
                "error": f"'{prog}' não está na lista de comandos de inspeção: {sorted(_READ_ONLY)}"}

    try:
        import paramiko
    except ImportError:
        return {"tool": "run_safe_command", "success": False,
                "error": "paramiko não instalado. Execute: pip install paramiko"}

    if not Path(_SSH_KEY).is_file():
        return {"tool": "run_safe_command", "success": False,
                "error": f"Chave SSH não encontrada em {_SSH_KEY}"}

    import asyncio
    loop = asyncio.get_event_loop()

    def _ssh_exec():
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        key = paramiko.RSAKey.from_private_key_file(_SSH_KEY)
        client.connect(hostname=_SSH_HOST, port=_SSH_PORT,
                       username=_SSH_USER, pkey=key, timeout=15)
        try:
            _, stdout, stderr = client.exec_command(command, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()
            return {"success": exit_code == 0, "stdout": out,
                    "stderr": err, "exit_code": exit_code}
        finally:
            client.close()

    try:
        result = await loop.run_in_executor(None, _ssh_exec)
        return {
            "tool": "run_safe_command",
            "command": command,
            **result,
            "output": result["stdout"] or result["stderr"],
        }
    except Exception as exc:
        return {"tool": "run_safe_command", "success": False,
                "command": command, "error": str(exc)}


# Registry
TOOLS = {
    "search_knowledge_base": search_knowledge,
    "get_adr": get_adr,
    "get_brain_status": get_brain_status,
    "list_rules": list_rules_with_evidence,
    "get_system_architecture": get_system_doc,
    "read_vault_file": read_vault_file,
    "run_safe_command": run_safe_command,
}


async def execute(tool_name: str, **kwargs) -> dict:
    """Executa uma ferramenta pelo nome."""
    fn = TOOLS.get(tool_name)
    if not fn:
        return {"tool": tool_name, "error": f"Tool '{tool_name}' not found", "available": list(TOOLS.keys())}
    try:
        return await fn(**kwargs)
    except Exception as exc:
        return {"tool": tool_name, "error": str(exc)}

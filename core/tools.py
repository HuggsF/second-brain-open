"""Implementações das ferramentas do corretor (sem política: quem decide é core.policy)."""
import asyncio
from typing import Any, Callable, Dict

from config import settings
from core import evidence
from core.evidence_store import EvidenceStore
from core.qdrant_store import QdrantStore
from core.retriever import BrainRetriever


async def search_knowledge(query: str, category: str = None) -> dict:
    """Busca vetorial no Qdrant."""
    retriever = BrainRetriever()
    result = retriever.query(query, limit=5, category=category, include_content=True)
    sources = result.get("sources", [])
    return {
        "tool": "search_knowledge_base",
        "query": query,
        "total": len(sources),
        "sources": [
            {
                "document": s.get("file_path") or "",
                "title": s.get("doc_title") or "",
                "section": s.get("section") or "",
                "score": round(s.get("score", 0), 3),
                "excerpt": (s.get("content") or "")[:200],
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
                    "status": r.get("state", "unknown"),  # "state" from evidence.list_rules() (fix: was "last_result")
                }
                for r in rules[:10]
            ],
        }
    except Exception as exc:
        return {"tool": "list_rules", "error": type(exc).__name__}


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


async def get_rule_evidence(rule_id: str) -> dict:
    """Estado de uma regra e seus playbooks (últimas execuções)."""
    defs = evidence.load_definitions()
    store = EvidenceStore()
    payload = evidence.rule_evidence(defs, store, rule_id)
    if "error" in payload:
        return {"tool": "get_rule_evidence", "found": False, "rule_id": rule_id}
    row = next((r for r in evidence.list_rules(defs, store) if r["id"] == rule_id), {})
    return {
        "tool": "get_rule_evidence",
        "found": True,
        "rule_id": rule_id,
        "state": row.get("state", "unknown"),
        "playbooks": payload["playbooks"],
    }


async def run_safe_command(command: str) -> dict:
    """Executa o comando no servidor via SSH. A política já aprovou o comando."""
    try:
        from mcp_servers.srv_api_gateway_mcp import _exec_command
    except ImportError as exc:
        return {"tool": "run_safe_command", "command": command, "success": False,
                "error": f"SSH indisponível: {type(exc).__name__}"}
    res = await asyncio.to_thread(_exec_command, command)  # copia o contexto: o rastro filho se anexa
    return {
        "tool": "run_safe_command",
        "command": command,
        "success": res["success"],
        "exit_code": res["exit_code"],
        "stdout": res["stdout"],
        "stderr": res["stderr"],
    }


IMPLEMENTATIONS: Dict[str, Callable[..., Any]] = {
    "search_knowledge_base": search_knowledge,
    "get_adr": get_adr,
    "get_brain_status": get_brain_status,
    "list_rules": list_rules_with_evidence,
    "get_rule_evidence": get_rule_evidence,
    "get_system_architecture": get_system_doc,
    "read_vault_file": read_vault_file,
    "run_safe_command": run_safe_command,
}

import re
from typing import Optional, Dict, Any, List
from fastmcp import FastMCP
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.trace_middleware import TraceMiddleware
from config import settings
from core.retriever import BrainRetriever
from core.qdrant_store import QdrantStore
from core import evidence, tracing
from core.evidence_store import EvidenceStore, EvidenceStoreError

mcp =FastMCP("KIOSK Second Brain")
mcp.add_middleware(TraceMiddleware('KIOSK Second Brain'))

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")

@mcp.tool()
def search_knowledge_base(query: str, category: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Pesquisa a base de conhecimento técnica e arquitetural da holding KIOSK Brands.
    Categorias válidas: 'adrs', 'systems', 'domain', 'daily'.
    task_id: optional label that groups this call with others of the same task
    """
    retriever = BrainRetriever()
    result = retriever.query(query, limit=5, category=category)
    return result["sources"]

@mcp.tool()
def get_adr(adr_identifier: str, task_id: Optional[str] = None) -> str:
    """
    Recupera o conteúdo completo de uma Architecture Decision Record (ADR) pelo número ou nome (ex: '001' ou 'salesforce').
    task_id: optional label that groups this call with others of the same task
    """
    adrs_dir = settings.adrs_dir
    if not _SAFE_NAME.match(adr_identifier or "") or ".." in adr_identifier:
        return "Identificador inválido. Use o número ou parte do nome da ADR (ex: '001' ou 'salesforce')."
    matches = list(adrs_dir.glob(f"*{adr_identifier}*.md"))
    if not matches:
        all_adrs = [f.name for f in adrs_dir.glob("*.md")]
        return f"ADR não encontrada. ADRs existentes: {', '.join(all_adrs)}"
    
    return matches[0].read_text(encoding="utf-8")

@mcp.tool()
def get_system_architecture(system_name: str, task_id: Optional[str] = None) -> str:
    """
    Recupera a documentação técnica de um sistema específico da holding: 'sap', 'sults', 'holmes', 'salesforce'.
    task_id: optional label that groups this call with others of the same task
    """
    name = (system_name or "").lower().strip()
    if not _SAFE_NAME.match(name) or ".." in name:
        return "Nome de sistema inválido. Use só o nome (ex: 'sap', 'sults', 'holmes', 'salesforce')."
    system_file = settings.systems_dir / f"{name}.md"
    if not system_file.resolve().is_relative_to(settings.systems_dir.resolve()) or not system_file.exists():
        available = [f.stem for f in settings.systems_dir.glob("*.md")]
        return f"Sistema '{system_name}' não encontrado. Disponíveis: {', '.join(available)}"

    return system_file.read_text(encoding="utf-8")

@mcp.tool()
def get_brain_status(task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna o status do Qdrant e a quantidade de vetores indexados no Second Brain.
    task_id: optional label that groups this call with others of the same task
    """
    store = QdrantStore()
    return store.get_stats()

@mcp.tool()
def list_rules(task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista as regras de negócio (vault/rules) com os playbooks que as validam e a data e o resultado da última execução.
    task_id: optional label that groups this call with others of the same task
    """
    try:
        return evidence.list_rules(evidence.load_definitions(), EvidenceStore())
    except EvidenceStoreError as exc:
        return [{"error": str(exc)}]

@mcp.tool()
def get_rule_evidence(rule_id: str, limit: int = 5, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Devolve uma regra (ex: 'RULE-001'), os playbooks que a validam e as últimas execuções de cada um (limit de 1 a 20).
    Playbook sem execuções traz a nota 'sem evidência ainda'.
    task_id: optional label that groups this call with others of the same task
    """
    try:
        return evidence.rule_evidence(evidence.load_definitions(), EvidenceStore(), rule_id, limit)
    except EvidenceStoreError as exc:
        return {"error": str(exc)}

@mcp.tool()
def record_test_execution(
    playbook_id: str, result: str, summary: str, evidence_ref: str, environment: str, task_id: Optional[str] = None,
    commit_sha: Optional[str] = None, run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Regista o resultado de um teste que alguém já executou (não executa nada). result: pass, fail, error ou skipped;
    environment: hml, production ou local; summary: até 500 caracteres; evidence_ref: caminho:linha, URL http(s) ou id de ticket.
    Nunca inclua dados de pedidos, CPF, chaves ou tokens: só referência e resumo. A execução fica ligada ao trace_id desta chamada.
    task_id: optional label that groups this call with others of the same task
    commit_sha: optional, hash do commit testado (7 a 40 hex minúsculos); run_id: optional, id da execução (ex.: gha:98765)
    """
    call = tracing.current_call.get()
    trace_id = call.trace_id if call else None
    clean, error = evidence.validate_execution(
        evidence.load_definitions(), playbook_id, result, summary, evidence_ref, environment,
        commit_sha=commit_sha, run_id=run_id)
    if error:
        tracing.emit_child("evidence.refused", "refused", {"reason": error})  # marks the call as refused in the trace
        return {"error": error, "trace_id": trace_id}
    try:
        new_id = EvidenceStore().record(
            playbook_id=playbook_id, result=result, environment=environment,
            evidence_ref=clean["evidence_ref"], summary=clean["summary"], source="reported",
            recorded_by=call.caller if call else "cli", trace_id=trace_id,
            task_label=call.task_label if call else None,
            commit_sha=clean["commit_sha"], run_id=clean["run_id"])
    except EvidenceStoreError as exc:
        return {"error": str(exc)}
    return {"recorded": new_id, "trace_id": trace_id}

if __name__ == "__main__":
    mcp.run()

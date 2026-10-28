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
from core.vault_docs import DocError, resolve_named, resolve_numbered
from core.evidence_store import EvidenceStore, EvidenceStoreError
from core.ontology import resolve_term, list_bounded_contexts, list_entities
from core.operational_rules import (
    list_rules as list_op_rules_fn,
    get_details as get_op_rule_details_fn,
)
from core.analytics_etl import (
    extract_and_store as etl_extract,
    get_emission_trends,
    get_error_analysis,
    get_throughput_analysis,
    get_logistics_health,
)

mcp =FastMCP("KIOSK Second Brain")
mcp.add_middleware(TraceMiddleware('KIOSK Second Brain'))

@mcp.tool()
def search_knowledge_base(query: str, category: Optional[str] = None, bounded_context: Optional[str] = None, include_content: bool = False, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Pesquisa a base de conhecimento técnica e arquitetural da holding KIOSK Brands.
    Categorias válidas: 'adrs', 'systems', 'domain', 'daily'.
    bounded_context: filtra por bounded context DDD (ex: 'Fiscal', 'Expedição e Remessas').
    include_content: se True, inclui o conteúdo completo de cada chunk no resultado.
    task_id: optional label that groups this call with others of the same task
    """
    retriever = BrainRetriever()
    result = retriever.query(query, limit=5, category=category, bounded_context=bounded_context, include_content=include_content)
    return result["sources"]

@mcp.tool()
def get_adr(adr_identifier: str, task_id: Optional[str] = None) -> str:
    """
    Recupera o conteúdo completo de uma Architecture Decision Record (ADR) pelo número ou nome (ex: '001' ou 'salesforce').
    task_id: optional label that groups this call with others of the same task
    """
    adrs_dir = settings.adrs_dir
    try:
        matches = resolve_numbered(adrs_dir, adr_identifier, prefix="ADR")
    except DocError:
        return "Identificador inválido. Use o número ou parte do nome da ADR (ex: '001' ou 'salesforce')."
    if not matches:
        all_adrs = [f.name for f in adrs_dir.glob("*.md")]
        return f"ADR não encontrada. ADRs existentes: {', '.join(all_adrs)}"
    if len(matches) > 1:
        return "Identificador ambíguo. Candidatas: " + ", ".join(m.name for m in matches)
    return matches[0].read_text(encoding="utf-8")

@mcp.tool()
def get_system_architecture(system_name: str, task_id: Optional[str] = None) -> str:
    """
    Recupera a documentação técnica de um sistema específico da holding.
    Exemplos: 'sap', 'sults', 'holmes', 'salesforce', 'hub-ontologia-ddd-proposta',
    'hub-mapa-entidades-dominios', 'hub-regras-operacionais-codex',
    'hub-gatilho-nfe-e-politicas-de-emissao', 'protecoes-processamento-emissao-hub'.
    task_id: optional label that groups this call with others of the same task
    """
    try:
        system_file = resolve_named(settings.systems_dir, system_name)
    except DocError:
        return "Nome de sistema inválido. Use só o nome (ex: 'sap', 'sults', 'holmes', 'salesforce')."
    if system_file is None:
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

# --- Ontology Tools (T1) ---

@mcp.tool()
def resolve_ontology_term(term: str, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Busca fuzzy (substring, case-insensitive) de um termo na ontologia DDD proposta do Hub Logístico.
    Retorna até 10 matches com nome atual, nome proposto, bounded context e natureza.
    Útil para descobrir o nome canônico de uma entidade, porta ou use case.
    task_id: optional label that groups this call with others of the same task
    """
    return resolve_term(term)

@mcp.tool()
def list_ddd_bounded_contexts(task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista os 5 bounded contexts do Hub Logístico (Pedidos, Fiscal, Expedição, Configuração, Consulta)
    com suas entidades, use cases, portas e implementações atuais (JS e TS).
    task_id: optional label that groups this call with others of the same task
    """
    return list_bounded_contexts()

@mcp.tool()
def list_domain_entities(bounded_context: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista entidades de domínio da ontologia DDD proposta, opcionalmente filtradas por bounded context.
    Exemplo: bounded_context='Fiscal' retorna NfeSnapshot, NfeDispatchPolicy, ValidatedInvoice.
    task_id: optional label that groups this call with others of the same task
    """
    return list_entities(bounded_context)

# --- Operational Rules Tools (T2) ---

@mcp.tool()
def list_operational_rules(category: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista as 74 regras operacionais do Hub Logístico catalogadas pelo agente Codex.
    Categorias: emission, preflight, nfe, recovery, weight, monitor, logging, deploy.
    Sem filtro retorna todas as regras. Cada regra tem: id, descrição, categoria, documento-fonte, branch.
    task_id: optional label that groups this call with others of the same task
    """
    return list_op_rules_fn(category)

@mcp.tool()
def get_operational_rule_details(rule_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna detalhes completos de uma regra operacional pelo ID (ex: 'INV-01', 'PREFLIGHT-03', 'NFE-07').
    Inclui descrição completa, categoria, documento-fonte e branch de origem.
    task_id: optional label that groups this call with others of the same task
    """
    return get_op_rule_details_fn(rule_id)

# --- ETL & Analytics Tools (T5) ---

@mcp.tool()
def etl_run(days: int = 7, environment: str = "production", task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executa o pipeline ETL: extrai dados agregados do Hub Logístico via SSH e armazena localmente.
    Não armazena PII (NEG-03). Não altera o Hub (NEG-02). days: janela de extração (1-90).
    environment: 'production' ou 'hml'. task_id: optional label.
    """
    days = max(1, min(int(days), 90))
    if environment not in ("production", "hml"):
        return {"error": "environment must be 'production' or 'hml'"}
    return etl_extract(days, environment)

@mcp.tool()
def predict_emission_trends(days: int = 30, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Analisa tendências de emissão dos últimos N dias e projeta volume do dia seguinte.
    Retorna médias, taxa de sucesso/falha, tendência (increasing/stable/decreasing) e dados diários.
    Requer ETL prévio (etl_run). task_id: optional label.
    """
    return get_emission_trends(max(1, min(int(days), 365)))

@mcp.tool()
def analyze_error_patterns(days: int = 14, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Analisa padrões de erro (RATE_LIMIT, TIMEOUT, REVIEW_REQUIRED, UNCERTAIN_STATE, CANCELLATION)
    dos últimos N dias. Identifica o problema mais frequente. Requer ETL prévio. task_id: optional label.
    """
    return get_error_analysis(max(1, min(int(days), 365)))

@mcp.tool()
def analyze_throughput(days: int = 7, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Analisa throughput por hora do dia, identifica pico e vale de operação,
    sugere janela de manutenção. Requer ETL prévio. task_id: optional label.
    """
    return get_throughput_analysis(max(1, min(int(days), 365)))

@mcp.tool()
def analyze_logistics_health(days: int = 14, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Analisa saúde do objeto logístico: cobertura, LOGISTICS_OBJECT_MISSING e MULTIPLE_VOLUMES.
    Requer ETL prévio. task_id: optional label.
    """
    return get_logistics_health(max(1, min(int(days), 365)))

if __name__ == "__main__":
    mcp.run()

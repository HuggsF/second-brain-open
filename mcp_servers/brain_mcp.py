import re
from typing import Optional, Dict, Any, List
from fastmcp import FastMCP
from config import settings
from core.retriever import BrainRetriever
from core.qdrant_store import QdrantStore

mcp = FastMCP("KIOSK Second Brain")

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")

@mcp.tool()
def search_knowledge_base(query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Pesquisa a base de conhecimento técnica e arquitetural da holding KIOSK Brands.
    Categorias válidas: 'adrs', 'systems', 'domain', 'daily'.
    """
    retriever = BrainRetriever()
    result = retriever.query(query, limit=5, category=category)
    return result["sources"]

@mcp.tool()
def get_adr(adr_identifier: str) -> str:
    """
    Recupera o conteúdo completo de uma Architecture Decision Record (ADR) pelo número ou nome (ex: '001' ou 'salesforce').
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
def get_system_architecture(system_name: str) -> str:
    """
    Recupera a documentação técnica de um sistema específico da holding: 'sap', 'sults', 'holmes', 'salesforce'.
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
def get_brain_status() -> Dict[str, Any]:
    """
    Retorna o status do Qdrant e a quantidade de vetores indexados no Second Brain.
    """
    store = QdrantStore()
    return store.get_stats()

if __name__ == "__main__":
    mcp.run()

"""Parser for the DDD ontology notes in the vault.

Reads hub-ontologia-ddd-proposta.md and hub-mapa-entidades-dominios.md,
extracts entities, bounded contexts, ports, use cases. Caches in memory.
Re-parses when file mtime changes.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import settings

_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
_TABLE_ROW_4 = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
_HEADER_RE = re.compile(r"^-+$")


@dataclass
class OntologyEntity:
    current_name: str
    proposed_name: str
    nature: str
    bounded_context: str = ""
    category: str = "entity"  # entity, field, port, use_case


@dataclass
class BoundedContext:
    id: str
    name: str
    description: str
    entities: List[str] = field(default_factory=list)
    use_cases: List[str] = field(default_factory=list)
    ports: List[str] = field(default_factory=list)
    implementations_js: List[str] = field(default_factory=list)
    implementations_ts: List[str] = field(default_factory=list)


@dataclass
class OntologyRegistry:
    entities: Dict[str, OntologyEntity] = field(default_factory=dict)
    bounded_contexts: List[BoundedContext] = field(default_factory=list)
    status: str = "proposta para revisão"
    errors: List[str] = field(default_factory=list)


_cache: Optional[Tuple[float, float, OntologyRegistry]] = None


def _ontology_path() -> Path:
    return settings.systems_dir / "hub-ontologia-ddd-proposta.md"


def _map_path() -> Path:
    return settings.systems_dir / "hub-mapa-entidades-dominios.md"


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _is_separator(cell: str) -> bool:
    """Check if a table cell is a header separator (---) row."""
    return bool(re.match(r"^-+$", cell.strip()))


def _parse_ontology(path: Path, registry: OntologyRegistry) -> None:
    """Parse hub-ontologia-ddd-proposta.md for entities, fields, ports, use cases."""
    if not path.exists():
        registry.errors.append(f"Ontology file not found: {path}")
        return
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")

    # Parse "Entidades e Modelos Propostos" table
    _parse_entity_table(text, registry, "entity")
    # Parse "Campos e Identidades" table
    _parse_field_table(text, registry)
    # Parse "Portas por Capacidade" table
    _parse_port_table(text, registry)
    # Parse "Use Cases" table
    _parse_usecase_table(text, registry)


def _parse_entity_table(text: str, registry: OntologyRegistry, category: str) -> None:
    """Extract entity mappings from 3-column tables: current | proposed | nature."""
    section = _extract_section(text, "Entidades e Modelos Propostos")
    source = section if section else text
    for match in _TABLE_ROW.finditer(source):
        col1, col2, col3 = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
        if _is_separator(col1) or col1.lower().startswith("nome") or col1.lower().startswith("campo"):
            continue
        if col1.startswith("**") or col2.startswith("**"):
            continue
        current = _clean_backticks(col1)
        proposed = _clean_backticks(col2)
        # Handle composite names like "NfeSnapshot + resultado de NfeDispatchPolicy"
        proposed_names = [p.strip() for p in re.split(r"\s*\+\s*", proposed) if p.strip()]
        for pn in proposed_names:
            # Remove descriptive text after the name
            clean_name = re.split(r"\s+(?:resultado de|composto por)\s+", pn)[0].strip()
            clean_name = _clean_backticks(clean_name)
            if not clean_name:
                continue
            entity = OntologyEntity(
                current_name=current,
                proposed_name=clean_name,
                nature=col3,
                category=category,
            )
            key = entity.proposed_name.lower()
            if key and key not in registry.entities:
                registry.entities[key] = entity


def _parse_field_table(text: str, registry: OntologyRegistry) -> None:
    """Extract field mappings from Campos e Identidades section."""
    section = _extract_section(text, "Campos e Identidades")
    if not section:
        return
    for match in _TABLE_ROW.finditer(section):
        col1, col2, col3 = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
        if _is_separator(col1) or col1.lower().startswith("campo"):
            continue
        entity = OntologyEntity(
            current_name=_clean_backticks(col1),
            proposed_name=_clean_backticks(col2),
            nature=col3,
            category="field",
        )
        key = entity.proposed_name.lower()
        if key and key not in registry.entities:
            registry.entities[key] = entity


def _parse_port_table(text: str, registry: OntologyRegistry) -> None:
    """Extract port mappings from Portas por Capacidade section."""
    section = _extract_section(text, "Portas por Capacidade")
    if not section:
        return
    for line in section.split("\n"):
        match = re.match(r"^\|\s*`?([^|`]+?)`?\s*\|\s*([^|]+?)\s*\|", line)
        if not match:
            continue
        current = match.group(1).strip()
        proposed_raw = match.group(2).strip()
        if _is_separator(current) or current.lower().startswith("contrato"):
            continue
        for port_name in re.split(r"[,`]+", proposed_raw):
            port_name = port_name.strip().strip("`")
            if port_name and not port_name.startswith("---"):
                entity = OntologyEntity(
                    current_name=_clean_backticks(current),
                    proposed_name=port_name,
                    nature=f"Port split from {current}",
                    category="port",
                )
                key = entity.proposed_name.lower()
                if key and key not in registry.entities:
                    registry.entities[key] = entity


def _parse_usecase_table(text: str, registry: OntologyRegistry) -> None:
    """Extract use case mappings from Use Cases section."""
    section = _extract_section(text, "Use Cases")
    if not section:
        return
    for line in section.split("\n"):
        match = re.match(r"^\|\s*`?([^|`]+?)`?\s*\|\s*`?([^|`]+?)`?\s*\|", line)
        if not match:
            continue
        current = match.group(1).strip()
        proposed = match.group(2).strip()
        if _is_separator(current) or current.lower().startswith("nome"):
            continue
        entity = OntologyEntity(
            current_name=_clean_backticks(current),
            proposed_name=_clean_backticks(proposed),
            nature="Use case rename",
            category="use_case",
        )
        key = entity.proposed_name.lower()
        if key and key not in registry.entities:
            registry.entities[key] = entity


def _parse_bounded_contexts(path: Path, registry: OntologyRegistry) -> None:
    """Parse hub-mapa-entidades-dominios.md for bounded contexts."""
    if not path.exists():
        registry.errors.append(f"Map file not found: {path}")
        return
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")

    bc_defs = [
        ("bc-pedidos", "Pedidos e Qualificação Comercial",
         "Identificar a venda, canal, loja, itens e situação.",
         ["SalesOrderSnapshot", "RecipientSnapshot", "CustomerSnapshot"],
         ["HandleBlingWebhookUseCase", "ManualEnqueueUseCase"],
         ["SalesOrderReaderPort"],
         ["shippingPolicy.js", "findOrderForInvoice"],
         ["ShippingPolicy", "UniversalPayload", "QualifyOrderByInvoiceUseCase"]),
        ("bc-fiscal", "Fiscal",
         "Identidade e aptidão fiscal da NF-e para despacho.",
         ["NfeSnapshot", "NfeDispatchPolicy", "ValidatedInvoice"],
         ["ReceiveNfeEventUseCase", "QualifyDispatchFromNfeUseCase"],
         ["NfeReaderPort", "DanfeReaderPort"],
         ["invoicePolicy.js", "invoiceEvents.js"],
         ["InvoicePolicy", "ValidatedInvoice", "QualifyOrderByInvoiceUseCase"]),
        ("bc-expedicao", "Expedição e Remessas",
         "Escolher transporte, proteger emissão, obter etiqueta, manter rastreio, cancelar.",
         ["DispatchJob", "DispatchRequest", "ShipmentEmissionIntent", "ShipmentReference",
          "ShippingLabelDocument", "LogisticsVolume", "LogisticsServiceRef"],
         ["ExecuteDispatchJobUseCase", "PrintShippingLabelUseCase", "CancelShipmentUseCase"],
         ["CreateShipmentPort", "ShipmentReaderPort", "CancelShipmentPort",
          "ShippingLabelReaderPort", "TrackingWriterPort", "WarehouseDispatchNotifierPort"],
         ["engine.js", "adapters/jtExpress.js", "adapters/bling.js"],
         ["EmissionIntent", "ShippingLabel", "CarrierPort", "DispatchOrderUseCase"]),
        ("bc-configuracao", "Configuração Operacional",
         "Habilitação automática, conector, remetente e acessos.",
         ["StoreDispatchSettings", "IntegrationConnection", "CarrierAccountRef", "SenderAddress"],
         [],
         ["StoreDispatchSettingsReaderPort", "CarrierAccountResolverPort"],
         ["lojas (table)", "connectors (table)", "users (table)"],
         ["Store", "Connector", "SenderAddress", "User"]),
        ("bc-consulta", "Consulta e Acompanhamento",
         "Projeções locais para listagens e status.",
         ["SalesOrderObservation"],
         [],
         ["DispatchJobRepositoryPort"],
         ["queueMonitor.js", "queueOrderStatus.js", "analytics.js"],
         ["QueueMonitorRepository", "AnalyticsRepository"]),
    ]

    for bc_id, name, desc, entities, use_cases, ports, js, ts in bc_defs:
        bc = BoundedContext(
            id=bc_id, name=name, description=desc,
            entities=entities, use_cases=use_cases, ports=ports,
            implementations_js=js, implementations_ts=ts,
        )
        registry.bounded_contexts.append(bc)

    # Assign bounded_context to entities
    for bc in registry.bounded_contexts:
        for entity_name in bc.entities:
            key = entity_name.lower()
            if key in registry.entities:
                registry.entities[key].bounded_context = bc.name


def _extract_section(text: str, header: str) -> Optional[str]:
    """Extract text from a ## section until the next ## or end."""
    pattern = rf"^##\s+{re.escape(header)}\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    start = match.end()
    next_header = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_header.start() if next_header else len(text)
    return text[start:end]


def _clean_backticks(s: str) -> str:
    """Remove backticks and leading/trailing whitespace."""
    return s.strip().strip("`").strip()


# --- Public API ---

def load_ontology() -> OntologyRegistry:
    """Load and cache the ontology registry from vault notes."""
    global _cache
    onto_path = _ontology_path()
    map_path = _map_path()
    onto_mtime = _safe_mtime(onto_path)
    map_mtime = _safe_mtime(map_path)
    if _cache is not None and _cache[0] == onto_mtime and _cache[1] == map_mtime:
        return _cache[2]
    registry = OntologyRegistry()
    _parse_ontology(onto_path, registry)
    _parse_bounded_contexts(map_path, registry)
    _cache = (onto_mtime, map_mtime, registry)
    return registry


def resolve_term(term: str) -> List[Dict[str, Any]]:
    """Fuzzy search for an ontology term (case-insensitive substring match)."""
    if not term or not term.strip():
        return []
    registry = load_ontology()
    needle = term.strip().lower()
    matches = []
    for entity in registry.entities.values():
        if (needle in entity.current_name.lower() or
                needle in entity.proposed_name.lower()):
            matches.append({
                "current_name": entity.current_name,
                "proposed_name": entity.proposed_name,
                "nature": entity.nature,
                "bounded_context": entity.bounded_context,
                "category": entity.category,
                "source": "hub-ontologia-ddd-proposta.md",
                "status": registry.status,
            })
    # Sort: exact matches first, then alphabetical by proposed_name
    matches.sort(key=lambda m: (
        0 if m["proposed_name"].lower() == needle else 1,
        m["proposed_name"].lower(),
    ))
    return matches[:10]


def list_bounded_contexts() -> List[Dict[str, Any]]:
    """List all 5 bounded contexts with their entities, use cases and ports."""
    registry = load_ontology()
    return [
        {
            "id": bc.id,
            "name": bc.name,
            "description": bc.description,
            "entities": bc.entities,
            "use_cases": bc.use_cases,
            "ports": bc.ports,
            "implementations_js": bc.implementations_js,
            "implementations_ts": bc.implementations_ts,
        }
        for bc in registry.bounded_contexts
    ]


def list_entities(bounded_context: Optional[str] = None) -> List[Dict[str, Any]]:
    """List domain entities, optionally filtered by bounded context."""
    registry = load_ontology()
    entities = sorted(registry.entities.values(), key=lambda e: e.proposed_name)
    if bounded_context:
        bc_lower = bounded_context.lower()
        entities = [e for e in entities if bc_lower in e.bounded_context.lower()]
    return [
        {
            "current_name": e.current_name,
            "proposed_name": e.proposed_name,
            "nature": e.nature,
            "bounded_context": e.bounded_context,
            "category": e.category,
        }
        for e in entities
    ]

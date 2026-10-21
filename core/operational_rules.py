"""Parser for the consolidated operational rules document (vault/systems/hub-regras-operacionais-codex.md).

Reads the markdown, extracts rule tables, caches in memory. Re-parses when file mtime changes.
"""
import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from config import settings

_RULE_ID_RE = re.compile(r'^(INV|PREFLIGHT|NFE|RECOVERY|WEIGHT|QMON|LOG|DEPLOY)-(\d{2})$')
_TABLE_ROW_RE = re.compile(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|')
_CATEGORY_MAP = {
    'INV': 'emission', 'PREFLIGHT': 'preflight', 'NFE': 'nfe',
    'RECOVERY': 'recovery', 'WEIGHT': 'weight', 'QMON': 'monitor',
    'LOG': 'logging', 'DEPLOY': 'deploy',
}
_CATEGORY_HEADER_MAP = {
    'Emissão e Segurança': 'emission', 'Preflight Logístico': 'preflight',
    'Admissão NF-e': 'nfe', 'Recuperação Logística Bling': 'recovery',
    'Cache de Produtos e Peso': 'weight', 'Monitor de Fila': 'monitor',
    'Logging de Integração': 'logging', 'Deploy e Rollback': 'deploy',
}

@dataclass
class OperationalRule:
    id: str
    description: str
    category: str
    source_doc: str
    source_branch: str
    full_text: str = ""
    dem_ref: Optional[str] = None

@dataclass  
class OperationalRulesRegistry:
    rules: Dict[str, OperationalRule] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
_cache: Optional[Tuple[float, OperationalRulesRegistry]] = None

def _rules_path() -> Path:
    return settings.systems_dir / "hub-regras-operacionais-codex.md"

def load_operational_rules() -> OperationalRulesRegistry:
    global _cache
    path = _rules_path()
    if not path.exists():
        return OperationalRulesRegistry(errors=[f"Rules file not found: {path}"])
    mtime = path.stat().st_mtime
    if _cache is not None and _cache[0] == mtime:
        return _cache[1]
    registry = OperationalRulesRegistry()
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    # Remove frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end+4:]
    current_category = ""
    current_source_doc = ""
    current_branch = ""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        # Detect section headers (## A. Category Name)
        header_match = re.match(r'^##\s+[A-H]\.\s+(.+?)(?:\s*\(.*\))?\s*$', line)
        if header_match:
            header_name = header_match.group(1).strip()
            for key, cat in _CATEGORY_HEADER_MAP.items():
                if key.lower() in header_name.lower():
                    current_category = cat
                    break
            continue
        # Detect source doc lines
        source_match = re.match(r'^Documento-fonte:\s*`(.+?)`.*Branch:\s*`(.+?)`', line)
        if source_match:
            current_source_doc = source_match.group(1)
            current_branch = source_match.group(2)
            continue
        # Detect table rows
        row_match = _TABLE_ROW_RE.match(line)
        if row_match:
            rule_id = row_match.group(1).strip()
            if not _RULE_ID_RE.match(rule_id):
                continue  # header row or invalid
            description = row_match.group(2).strip()
            doc = row_match.group(3).strip() or current_source_doc
            branch = row_match.group(4).strip() or current_branch
            prefix = rule_id.split("-")[0]
            category = _CATEGORY_MAP.get(prefix, current_category)
            rule = OperationalRule(
                id=rule_id, description=description, category=category,
                source_doc=doc, source_branch=branch, full_text=description,
            )
            if rule_id in registry.rules:
                registry.errors.append(f"Duplicate rule: {rule_id}")
            else:
                registry.rules[rule_id] = rule
    _cache = (mtime, registry)
    return registry

def list_rules(category: Optional[str] = None) -> List[Dict[str, Any]]:
    registry = load_operational_rules()
    rules = sorted(registry.rules.values(), key=lambda r: r.id)
    if category:
        rules = [r for r in rules if r.category == category]
    return [{"id": r.id, "description": r.description, "category": r.category,
             "source_doc": r.source_doc, "source_branch": r.source_branch} for r in rules]

def get_details(rule_id: str) -> Dict[str, Any]:
    registry = load_operational_rules()
    rule = registry.rules.get(rule_id)
    if rule is None:
        known = sorted(registry.rules.keys())
        return {"error": f"Unknown rule '{rule_id}' (known: {', '.join(known[:10])}...)"}
    return {"id": rule.id, "description": rule.description, "full_text": rule.full_text,
            "category": rule.category, "source_doc": rule.source_doc,
            "source_branch": rule.source_branch, "dem_ref": rule.dem_ref}

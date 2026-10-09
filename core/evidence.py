"""Evidence tree: business rules and playbooks (Markdown notes in the vault) and, in the same
module, the validation and queries over their execution history (see core/evidence_store.py).

Nothing here runs a test; it only reads definitions and links recorded results to them.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from config import settings
from core.evidence_store import EvidenceStore, EvidenceStoreError

RESULTS = ("pass", "fail", "error", "skipped")
ENVIRONMENTS = ("hml", "production", "local")
STATUSES = ("draft", "active", "retired")

_RULE_ID = re.compile(r"^RULE-\d{3}$")
_PLAYBOOK_ID = re.compile(r"^PB-\d{3}$")
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


@dataclass
class Rule:
    id: str
    title: str
    status: str
    source: str
    domain: str
    path: str


@dataclass
class Playbook:
    id: str
    title: str
    status: str
    validates: List[str]
    environment: str
    targets: List[str]
    path: str


@dataclass
class Definitions:
    rules: Dict[str, Rule] = field(default_factory=dict)
    playbooks: Dict[str, Playbook] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


def _vault_dir() -> Path:
    return settings.vault_dir


def _front_matter(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    text = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    match = _FRONT_MATTER.match(text)
    if not match:
        return None, "missing front matter (a block fenced by ---, first in the file)"
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return None, f"malformed front matter ({type(exc).__name__})"
    if not isinstance(data, dict):
        return None, "front matter is not a mapping"
    return data, None


def _text_field(data: Dict[str, Any], name: str, problems: List[str]) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"missing or empty field '{name}'")
        return ""
    return value.strip()


def _text_list(data: Dict[str, Any], name: str, problems: List[str], non_empty: bool) -> List[str]:
    value = data.get(name)
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        problems.append(f"field '{name}' must be a list of texts")
        return []
    if non_empty and not value:
        problems.append(f"field '{name}' must not be empty")
    return [v.strip() for v in value]


def _check_enum(value: str, allowed: Tuple[str, ...], name: str, problems: List[str]) -> None:
    if value and value not in allowed:
        problems.append(f"invalid {name} '{value}' (allowed: {', '.join(allowed)})")


def _parse_rule(data: Dict[str, Any], rel: str) -> Tuple[Optional[Rule], List[str]]:
    problems: List[str] = []
    rule = Rule(
        id=_text_field(data, "id", problems), title=_text_field(data, "title", problems),
        status=_text_field(data, "status", problems), source=_text_field(data, "source", problems),
        domain=_text_field(data, "domain", problems), path=rel,
    )
    if rule.id and not _RULE_ID.match(rule.id):
        problems.append(f"invalid id '{rule.id}' (expected RULE-NNN)")
    _check_enum(rule.status, STATUSES, "status", problems)
    return (None if problems else rule), problems


def _parse_playbook(data: Dict[str, Any], rel: str) -> Tuple[Optional[Playbook], List[str]]:
    problems: List[str] = []
    playbook = Playbook(
        id=_text_field(data, "id", problems), title=_text_field(data, "title", problems),
        status=_text_field(data, "status", problems),
        validates=_text_list(data, "validates", problems, non_empty=True),
        environment=_text_field(data, "environment", problems),
        targets=_text_list(data, "targets", problems, non_empty=False), path=rel,
    )
    if playbook.id and not _PLAYBOOK_ID.match(playbook.id):
        problems.append(f"invalid id '{playbook.id}' (expected PB-NNN)")
    _check_enum(playbook.status, STATUSES, "status", problems)
    _check_enum(playbook.environment, ENVIRONMENTS, "environment", problems)
    return (None if problems else playbook), problems


def load_definitions(vault_dir: Optional[Path] = None) -> Definitions:
    """Read every rule and playbook note. A malformed note adds an error and is skipped; never raises."""
    root = Path(vault_dir) if vault_dir else _vault_dir()
    defs = Definitions()
    for folder, parse, store in (("rules", _parse_rule, defs.rules), ("playbooks", _parse_playbook, defs.playbooks)):
        try:
            notes = sorted((root / folder).glob("*.md"))
        except OSError as exc:
            defs.errors.append(f"{folder}: cannot list folder ({type(exc).__name__})")
            continue
        for note in notes:
            rel = note.relative_to(root).as_posix()
            try:
                data, problem = _front_matter(note)
                problems = [problem] if problem else []
                item = None
                if data is not None:
                    item, problems = parse(data, rel)
                if item is not None and item.id in store:
                    item, problems = None, [f"duplicate id '{item.id}'"]
                if item is not None:
                    store[item.id] = item
            except Exception as exc:  # a broken note must never stop the others
                problems = [f"unreadable note ({type(exc).__name__})"]
            defs.errors.extend(f"{rel}: {p}" for p in problems)
    return defs


# --- execution validation -------------------------------------------------------------------------

_REF_SHAPE = re.compile(r"^(https?://\S+|[\w./-]+:\d+(?:-\d+)?|[A-Z][A-Z0-9]*-\d+)$")
_SENSITIVE = (
    ("token", re.compile(r"ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|-----BEGIN")),
    ("cpf", re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|(?<!\d)\d{11}(?!\d)")),
    ("nf-key", re.compile(r"(?<!\d)\d{44}(?!\d)")),
)
SUMMARY_MAX = 500
EVIDENCE_REF_MAX = 300
LIMIT_MAX = 20


def _clean_text(value: str) -> str:
    """Tabs and line breaks become spaces; every other control character is dropped."""
    value = re.sub(r"[\r\n\t]", " ", value)
    return "".join(c for c in value if unicodedata.category(c) != "Cc").strip()


def _sensitive(text: str, field_name: str) -> Optional[str]:
    for name, pattern in _SENSITIVE:
        if pattern.search(text):
            return f"possible sensitive data ({name}) in {field_name}"  # never echo the value
    return None


def validate_execution(
    defs: Definitions, playbook_id: str, result: str, summary: str, evidence_ref: str, environment: str
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Return (clean fields, None) or (None, error message). Never raises."""
    if not isinstance(playbook_id, str) or not _PLAYBOOK_ID.match(playbook_id):
        return None, "invalid playbook id (expected PB-NNN)"
    playbook = defs.playbooks.get(playbook_id)
    if playbook is None:
        return None, f"unknown playbook '{playbook_id}' (known: {', '.join(sorted(defs.playbooks)) or 'none'})"
    if playbook.status == "retired":
        return None, f"playbook '{playbook_id}' is retired"
    if result not in RESULTS:
        return None, f"invalid result (allowed: {', '.join(RESULTS)})"
    if environment not in ENVIRONMENTS:
        return None, f"invalid environment (allowed: {', '.join(ENVIRONMENTS)})"
    if environment not in (playbook.environment, "local"):
        return None, f"environment '{environment}' does not match the playbook ({playbook.environment}) nor local"
    if not isinstance(summary, str):
        return None, "summary must be text"
    if not isinstance(evidence_ref, str):
        return None, "evidence_ref must be text"
    summary, evidence_ref = _clean_text(summary), _clean_text(evidence_ref)
    for text, name in ((summary, "summary"), (evidence_ref, "evidence_ref")):
        problem = _sensitive(text, name)
        if problem:
            return None, problem
    if not 1 <= len(summary) <= SUMMARY_MAX:
        return None, f"summary must have 1 to {SUMMARY_MAX} characters"
    if not 1 <= len(evidence_ref) <= EVIDENCE_REF_MAX or not _REF_SHAPE.match(evidence_ref):
        return None, f"evidence_ref must be path:line, an http(s) URL or a ticket id, up to {EVIDENCE_REF_MAX} characters"
    return {"summary": summary, "evidence_ref": evidence_ref}, None


# --- queries --------------------------------------------------------------------------------------

def rule_evidence(defs: Definitions, store: EvidenceStore, rule_id: str, limit: int = 5) -> Dict[str, Any]:
    rule = defs.rules.get(rule_id) if isinstance(rule_id, str) else None
    if rule is None:
        return {"error": f"unknown rule (known: {', '.join(sorted(defs.rules)) or 'none'})"}
    limit = max(1, min(int(limit), LIMIT_MAX))
    playbooks = []
    for playbook in sorted(defs.playbooks.values(), key=lambda p: p.id):
        if rule.id not in playbook.validates:
            continue
        executions = store.latest(playbook.id, limit)
        entry: Dict[str, Any] = {"id": playbook.id, "title": playbook.title, "status": playbook.status,
                                 "environment": playbook.environment, "executions": executions}
        if not executions:
            entry["note"] = "sem evidência ainda"
        playbooks.append(entry)
    return {
        "rule": {"id": rule.id, "title": rule.title, "status": rule.status, "source": rule.source, "domain": rule.domain},
        "playbooks": playbooks,
    }


def list_rules(defs: Definitions, store: EvidenceStore) -> List[Dict[str, Any]]:
    out = []
    for rule in sorted(defs.rules.values(), key=lambda r: r.id):
        playbook_ids = sorted(p.id for p in defs.playbooks.values() if rule.id in p.validates)
        newest = None
        for playbook_id in playbook_ids:
            for row in store.latest(playbook_id, 1):
                if newest is None or (row["ts"], row["id"]) > (newest["ts"], newest["id"]):
                    newest = row
        out.append({
            "id": rule.id, "title": rule.title, "status": rule.status, "playbooks": playbook_ids,
            "latest": None if newest is None else {"ts": newest["ts"], "result": newest["result"], "playbook_id": newest["playbook_id"]},
        })
    return out


# --- lint and seed import -------------------------------------------------------------------------

def lint(defs: Definitions, store: Optional[EvidenceStore] = None) -> List[str]:
    problems = list(defs.errors)
    for playbook in sorted(defs.playbooks.values(), key=lambda p: p.id):
        for rule_id in playbook.validates:
            rule = defs.rules.get(rule_id)
            if rule is None:
                problems.append(f"{playbook.path}: playbook {playbook.id} validates unknown rule {rule_id}")
            elif rule.status == "retired" and playbook.status == "active":
                problems.append(f"{playbook.path}: active playbook {playbook.id} validates retired rule {rule_id}")
    for rule in sorted(defs.rules.values(), key=lambda r: r.id):
        if rule.status == "active" and not any(
            p.status == "active" and rule.id in p.validates for p in defs.playbooks.values()
        ):
            problems.append(f"{rule.path}: active rule {rule.id} has no active playbook")
    if store is not None:
        try:
            for playbook_id in sorted(store.all_playbook_ids() - set(defs.playbooks)):
                problems.append(f"evidence store: executions reference unknown playbook {playbook_id}")
        except EvidenceStoreError as exc:
            problems.append(f"evidence store unavailable: {exc}")
    return problems


def import_seed(defs: Definitions, store: EvidenceStore, seed_path: Path) -> Tuple[int, int]:
    """Load tracked seed executions. Returns (added, skipped); skipped = already imported or invalid."""
    try:
        rows = json.loads(Path(seed_path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"seed file is not valid JSON ({exc.msg})") from exc
    if not isinstance(rows, list):
        raise ValueError("seed file must contain a list of executions")
    added = skipped = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("import_key"), str) or not isinstance(row.get("ts"), str):
            skipped += 1
            continue
        clean, error = validate_execution(
            defs, row.get("playbook_id"), row.get("result"), row.get("summary"), row.get("evidence_ref"), row.get("environment"))
        if error:
            skipped += 1
            continue
        new_id = store.record(
            playbook_id=row["playbook_id"], result=row["result"], environment=row["environment"],
            evidence_ref=clean["evidence_ref"], summary=clean["summary"], source="imported",
            recorded_by="cli", ts=row["ts"], import_key=row["import_key"])
        if new_id is None:
            skipped += 1
        else:
            added += 1
    return added, skipped

"""Evidence tree: business rules and playbooks (Markdown notes in the vault) and, in the same
module, the validation and queries over their execution history (see core/evidence_store.py).

Nothing here runs a test; it only reads definitions and links recorded results to them.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from config import settings

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

"""Evidence tree: business rules and playbooks (Markdown notes in the vault) and, in the same
module, the validation and queries over their execution history (see core/evidence_store.py).

Nothing here runs a test; it only reads definitions and links recorded results to them.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from config import settings
from core import tracing
from core.evidence_store import EvidenceStore, EvidenceStoreError

RESULTS = ("pass", "fail", "error", "skipped")
ENVIRONMENTS = ("hml", "production", "local")
STATUSES = ("draft", "active", "retired")
KINDS = ("test", "runbook")
DEFAULT_TTL_HOURS = 168
MAX_TTL_HOURS = 8760

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
    params: List[Dict[str, Any]] = field(default_factory=list)
    kind: str = "runbook"
    ttl_hours: int = DEFAULT_TTL_HOURS


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


def _ttl_hours(data: Dict[str, Any], problems: List[str]) -> int:
    value = data.get("ttl_hours", DEFAULT_TTL_HOURS)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_TTL_HOURS:
        problems.append(f"invalid ttl_hours (expected an integer from 1 to {MAX_TTL_HOURS})")
        return DEFAULT_TTL_HOURS
    return value


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
    raw_params = data.get("params")
    params_list = []
    if raw_params is not None:
        if isinstance(raw_params, list):
            for p in raw_params:
                if isinstance(p, dict) and "name" in p:
                    params_list.append(p)
                else:
                    problems.append("each item in 'params' must be a mapping with a 'name'")
        else:
            problems.append("field 'params' must be a list of parameter definitions")

    playbook = Playbook(
        id=_text_field(data, "id", problems), title=_text_field(data, "title", problems),
        status=_text_field(data, "status", problems),
        validates=_text_list(data, "validates", problems, non_empty=True),
        environment=_text_field(data, "environment", problems),
        targets=_text_list(data, "targets", problems, non_empty=False), path=rel,
        params=params_list, ttl_hours=_ttl_hours(data, problems),
    )
    kind = data.get("kind", "runbook")
    if isinstance(kind, str) and kind.strip() in KINDS:
        playbook.kind = kind.strip()
    else:
        shown = f" '{kind}'" if isinstance(kind, str) else ""
        problems.append(f"invalid kind{shown} (allowed: {', '.join(KINDS)})")
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
_NO_EVIDENCE = "sem evidência ainda"
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9._:/#-]{1,80}$")
SUMMARY_MAX = 500
EVIDENCE_REF_MAX = 300
LIMIT_MAX = 20


def _clean_text(value: str) -> str:
    """Tabs and line breaks become spaces; every other control character is dropped."""
    value = re.sub(r"[\r\n\t]", " ", value)
    return "".join(c for c in value if unicodedata.category(c) != "Cc").strip()


def _sensitive(text: str, field_name: str) -> Optional[str]:
    name = tracing.find_sensitive(text)  # the same matcher that masks the trace log
    return f"possible sensitive data ({name}) in {field_name}" if name else None  # never echo the value


def validate_execution(
    defs: Definitions, playbook_id: str, result: str, summary: str, evidence_ref: str, environment: str,
    commit_sha: Optional[str] = None, run_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Optional[str]]], Optional[str]]:
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
    if commit_sha is not None and not isinstance(commit_sha, str):
        return None, "commit_sha must be text"
    if run_id is not None and not isinstance(run_id, str):
        return None, "run_id must be text"
    commit_sha, run_id = commit_sha or "", run_id or ""
    summary, evidence_ref = _clean_text(summary), _clean_text(evidence_ref)
    commit_sha, run_id = _clean_text(commit_sha), _clean_text(run_id)
    for text, name in ((summary, "summary"), (evidence_ref, "evidence_ref"), (commit_sha, "commit_sha"), (run_id, "run_id")):
        problem = _sensitive(text, name)
        if problem:
            return None, problem
    if not 1 <= len(summary) <= SUMMARY_MAX:
        return None, f"summary must have 1 to {SUMMARY_MAX} characters"
    if not 1 <= len(evidence_ref) <= EVIDENCE_REF_MAX or not _REF_SHAPE.match(evidence_ref):
        return None, f"evidence_ref must be path:line, an http(s) URL or a ticket id, up to {EVIDENCE_REF_MAX} characters"
    if commit_sha and not _COMMIT_SHA.match(commit_sha):
        return None, "commit_sha must be 7 to 40 lowercase hex characters"
    if run_id and not _RUN_ID.match(run_id):
        return None, "run_id must have 1 to 80 characters from A-Z a-z 0-9 . _ : / # -"
    return {"summary": summary, "evidence_ref": evidence_ref,
            "commit_sha": commit_sha or None, "run_id": run_id or None}, None


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
                                 "environment": playbook.environment, "kind": playbook.kind,
                                 "ttl_hours": playbook.ttl_hours, "executions": executions}
        if not executions:
            entry["note"] = _NO_EVIDENCE
        playbooks.append(entry)
    rule_playbooks = sorted((p for p in defs.playbooks.values() if rule.id in p.validates), key=lambda p: p.id)
    light = rule_light(rule_playbooks, store)
    return {
        "rule": {"id": rule.id, "title": rule.title, "status": rule.status, "source": rule.source, "domain": rule.domain},
        "playbooks": playbooks,
        "light": light["light"],
        "light_reason": light["reason"],
    }


_LIGHT_FETCH = 5  # rows per query: latest overall and latest in the playbook's own environment
_FUTURE_TOLERANCE = timedelta(minutes=5)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Aware datetime from an ISO-8601 string (a trailing Z is UTC, naive is treated as UTC); None if unparseable."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _playbook_light(playbook: Playbook, store: EvidenceStore, now: datetime) -> Tuple[str, str]:
    """(light, reason) of one counted playbook; "none" means it has no execution at all.

    Two small queries instead of one fixed window: the latest rows overall and the latest rows in the
    playbook's own environment, so many newer runs elsewhere can neither hide nor fake own-environment evidence.
    """
    overall = store.latest(playbook.id, _LIGHT_FETCH)
    if not overall:
        return "none", f"{playbook.id} sem execução em {playbook.environment}"
    rows = {r["id"]: r for r in overall}
    rows.update({r["id"]: r for r in store.latest(playbook.id, _LIGHT_FETCH, environment=playbook.environment)})
    usable = []
    invalid = False
    for row in rows.values():
        stamp = _parse_ts(row.get("ts"))
        if stamp is None or stamp > now + _FUTURE_TOLERANCE:
            invalid = True
        else:
            usable.append((stamp, row))
    usable.sort(key=lambda item: item[0], reverse=True)
    own = [(s, r) for s, r in usable if r["environment"] == playbook.environment]
    # red: the latest run overall OR the latest run in the playbook's own environment failed/errored
    for stamp, row in (usable[:1] + own[:1]):
        if row["result"] in ("fail", "error"):
            verb = "reprovou" if row["result"] == "fail" else "falhou com erro"
            return "red", f"{playbook.id} {verb} em {row['environment']} em {stamp.date().isoformat()}"
    if invalid:  # conservative: one unusable row keeps the playbook from being green
        return "yellow", f"{playbook.id} com data de execução inválida"
    if not own:
        return "yellow", f"{playbook.id} sem execução em {playbook.environment}"
    own_stamp, own_row = own[0]
    if own_row["result"] == "skipped":  # a skipped run elsewhere does not decide
        return "yellow", f"{playbook.id} ignorado na última execução em {playbook.environment}"
    if own_row["result"] != "pass":
        return "yellow", f"{playbook.id} sem aprovação em {playbook.environment}"
    if now - own_stamp > timedelta(hours=playbook.ttl_hours):
        return "yellow", f"{playbook.id} expirou ({playbook.ttl_hours} h)"
    return "green", f"{playbook.id} aprovado em {playbook.environment}"


def rule_light(playbooks: List[Playbook], store: EvidenceStore, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Test light of a rule from its ACTIVE playbooks of kind "test" (precedence red, grey, yellow, green).

    red: the latest execution (any environment) of a counted playbook failed or errored. grey: no counted
    playbook has any execution. yellow: some counted playbook has no execution, is skipped, expired,
    only ran in an environment other than its own, or has invalid data. green: every counted playbook has
    a pass inside its TTL in its OWN environment.
    """
    moment = now if now is not None else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    counted = sorted((p for p in playbooks if p.status == "active" and p.kind == "test"), key=lambda p: p.id)
    result: Dict[str, Any] = {"light": "grey", "reason": "", "test_playbooks": [p.id for p in counted],
                              "test_environments": sorted({p.environment for p in counted})}
    if not counted:
        result["reason"] = "sem playbook de teste ativo"
        return result
    verdicts = [_playbook_light(p, store, moment) for p in counted]
    red = next((v for v in verdicts if v[0] == "red"), None)
    if red:
        result["light"], result["reason"] = red
        return result
    if all(v[0] == "none" for v in verdicts):
        result["reason"] = "sem execução de teste registrada"
        return result
    hit = next((v for v in verdicts if v[0] in ("yellow", "none")), None)
    if hit:
        result["light"], result["reason"] = "yellow", hit[1]
        return result
    result["light"] = "green"
    result["reason"] = "todos os playbooks de teste aprovados" if len(verdicts) > 1 else verdicts[0][1]
    return result


def list_rules(defs: Definitions, store: EvidenceStore, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """One row per rule: its playbooks, the latest execution of EACH playbook and an overall state.

    state: "falha" if any active playbook's latest execution failed or errored; "ok" if every active
    playbook's latest execution passed; "parcial" if some active playbook has no execution yet (or only
    a skipped one); "sem evidência ainda" if no active playbook has any execution.
    light / light_reason / test_playbooks / test_environments: see rule_light (test playbooks only).
    """
    out = []
    for rule in sorted(defs.rules.values(), key=lambda r: r.id):
        playbooks = sorted((p for p in defs.playbooks.values() if rule.id in p.validates), key=lambda p: p.id)
        latest: Dict[str, Optional[Dict[str, Any]]] = {}
        for playbook in playbooks:
            rows = store.latest(playbook.id, 1)
            latest[playbook.id] = None if not rows else {
                k: rows[0][k] for k in ("ts", "result", "source", "environment")}
        results = [latest[p.id]["result"] if latest[p.id] else None for p in playbooks if p.status == "active"]
        if not any(r is not None for r in results):
            state = _NO_EVIDENCE
        elif any(r in ("fail", "error") for r in results):
            state = "falha"
        elif all(r == "pass" for r in results):
            state = "ok"
        else:
            state = "parcial"
        light = rule_light(playbooks, store, now)
        out.append({"id": rule.id, "title": rule.title, "status": rule.status,
                    "playbooks": [p.id for p in playbooks], "playbook_latest": latest, "state": state,
                    "light": light["light"], "light_reason": light["reason"],
                    "test_playbooks": light["test_playbooks"], "test_environments": light["test_environments"]})
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

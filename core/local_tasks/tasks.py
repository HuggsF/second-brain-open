"""Tarefas locais: prompts, schema de saída e pós-processamento por tarefa."""
from __future__ import annotations

import datetime as _dt
import json
import re

import yaml
from jsonschema import Draft202012Validator

from core.local_tasks.profile import Profile
from core.protocol import registry

REVIEW_SCHEMA = {"type": "object", "required": ["review"],
                 "properties": {"review": {"type": "array", "items": {"type": "string"}}},
                 "additionalProperties": False}
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_PARAGRAPHS = re.compile(r"\r?\n[ \t]*\r?\n")


def output_schema(task: str, template: str | None) -> dict:
    if task == "classify":
        return registry.load_schema("classification@1")
    if task == "extract":
        return registry.load_schema(template)
    if task == "summarize":
        return registry.load_schema("summary@1")
    if task == "validate":
        return REVIEW_SCHEMA
    raise NotImplementedError(task)


def prompt(task: str, text: str, profile: Profile, schema: dict, target_words: int) -> tuple[str, str]:
    if task == "classify":
        vocab = "\n".join(f"- {k}: {', '.join(v)}" for k, v in profile.labels.items())
        system = (
            "Classify the text. Answer only with JSON that follows the schema. "
            "Use exactly one value of each allowed list for `type` and `team`; "
            "`tags` are short lowercase keywords. `confidence` is between 0 and 1.\n"
            f"Allowed values:\n{vocab}"
        )
        return system, text
    if task == "extract":
        system = (
            "Extract the fields of the template from the text. Answer only with JSON "
            "that follows the schema. Use only information present in the text; "
            "do not invent values."
        )
        return system, text
    if task == "summarize":
        system = (
            f"Summarize the text in about {target_words} words. Answer only with JSON that "
            "follows the schema: `summary` is the summary, `key_points` lists the main points. "
            "Use only information present in the text."
        )
        return system, text
    if task == "validate":
        system = (
            "Compare the free-text fields of the document with the source. Answer only with "
            "JSON that follows the schema: `review` lists, one string each, the statements "
            "in the document that contradict or are not supported by the source. "
            "Use an empty list when there are none."
        )
        return system, text
    raise NotImplementedError(task)


def _canon(value, vocabulary: list[str]) -> str:
    if not isinstance(value, str):
        return ""
    wanted = value.strip().casefold()
    for item in vocabulary:
        if item.casefold() == wanted:
            return item
    return ""


def postprocess(task: str, obj: dict, profile: Profile) -> tuple[dict | None, str | None]:
    """Devolve (payload, None) ou (None, reason)."""
    if task == "classify":
        labels = obj.get("labels") if isinstance(obj.get("labels"), dict) else {}
        kind = _canon(labels.get("type"), profile.labels.get("type", []))
        team = _canon(labels.get("team"), profile.labels.get("team", []))
        if not kind and not team:
            return None, "no_valid_label"
        tags: list[str] = []
        for tag in labels.get("tags") or []:
            if isinstance(tag, str) and tag.strip():
                low = tag.strip().lower()
                if low not in tags:
                    tags.append(low)
        # classification@1 exige strings em type/team (null não é aceito): "" = sem rótulo válido.
        return {"labels": {"type": kind, "team": team, "tags": tags},
                "confidence": obj.get("confidence")}, None
    if task in ("extract", "summarize", "validate"):
        return obj, None
    raise NotImplementedError(task)


def split_blocks(text: str, max_chars: int) -> list[str]:
    """Corta em parágrafos; parágrafo grande vira linhas e, por fim, fatias de caracteres."""
    max_chars = max(1, int(max_chars))

    def pieces(chunk: str) -> list[str]:
        if len(chunk) <= max_chars:
            return [chunk]
        lines = chunk.splitlines()
        if len(lines) > 1:
            out: list[str] = []
            for line in lines:
                out.extend(pieces(line))
            return out
        return [chunk[i:i + max_chars] for i in range(0, len(chunk), max_chars)]

    blocks: list[str] = []
    current = ""
    for para in _PARAGRAPHS.split(text):
        if not para.strip():
            continue
        parts = pieces(para)
        sep = "\n\n" if len(parts) == 1 else "\n"
        for part in parts:
            if not part.strip():
                continue
            joined = f"{current}{sep}{part}" if current else part
            if len(joined) <= max_chars:
                current = joined
            else:
                if current:
                    blocks.append(current)
                current = part
        if len(parts) > 1 and current:
            blocks.append(current)
            current = ""
    if current:
        blocks.append(current)
    return blocks


def _iso(value):
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _iso(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_iso(v) for v in value]
    return value


def _split_document(document: str) -> tuple[dict | None, str, str]:
    """Devolve (frontmatter, corpo, erro)."""
    text = document.lstrip("﻿")
    match = _FRONTMATTER.match(text)
    if not match:
        return None, text, "documento sem frontmatter YAML"
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return None, text, f"frontmatter YAML inválido: {str(exc).splitlines()[0]}"
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        return None, text, "frontmatter não é um mapeamento"
    return _iso(meta), text[match.end():], ""


def _document_object(document: str | dict) -> tuple[dict | None, str, str]:
    if isinstance(document, dict):
        return _iso(document), "", ""
    # Texto que começa com "{" e é um objeto JSON vale como objeto (ex.: o payload de extract).
    stripped = document.lstrip("﻿").strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return _iso(parsed), "", ""
    obj, body, why = _split_document(document)
    if obj is not None:
        for line in body.splitlines():
            if line.startswith("# "):
                obj["title"] = line[2:].strip()
                break
    return obj, body, why


def validate_document(document: str | dict, template: str) -> dict:
    """Validação determinística contra o schema do template. Levanta UnknownTemplate."""
    schema = registry.load_schema(template)
    obj, _, why = _document_object(document)
    if obj is None:
        return {"valid": False, "missing": [], "errors": [why], "review": []}
    missing = [k for k in schema.get("required", []) if k not in obj]
    errors = []
    for err in sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.absolute_path)):
        if err.validator == "required" and not err.absolute_path:  # raiz: já está em missing
            continue
        errors.append(f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}")
    return {"valid": not missing and not errors, "missing": missing, "errors": errors, "review": []}


def review_input(document: str | dict, source: str) -> str:
    """Campos de texto livre do documento + a fonte, para a conferência pelo modelo."""
    obj, body, _ = _document_object(document)
    fields = {k: v for k, v in (obj or {}).items() if isinstance(v, str)}
    return (f"DOCUMENT FIELDS:\n{json.dumps(fields, ensure_ascii=False)}\n\n"
            f"DOCUMENT BODY:\n{body}\n\nSOURCE:\n{source}")

"""Registro de schemas de template versionados (ref = "adr@1")."""
from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

_DIR = Path(__file__).parent / "schemas" / "templates"
_REF = re.compile(r"^[a-z][a-z0-9-]*@\d+$")


class UnknownTemplate(ValueError):
    pass


def load_schema(ref: str) -> dict:
    if not isinstance(ref, str) or not _REF.match(ref):
        raise UnknownTemplate(f"referência de template inválida: {ref!r}")
    path = _DIR / f"{ref}.schema.json"
    if not path.is_file():
        raise UnknownTemplate(f"template desconhecido: {ref}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(ref: str, obj: dict) -> list[str]:
    validator = Draft202012Validator(load_schema(ref))
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def available() -> list[str]:
    return sorted(p.name[: -len(".schema.json")] for p in _DIR.glob("*@*.schema.json"))

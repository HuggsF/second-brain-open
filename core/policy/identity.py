"""Identidade de agente: 'agent:<role>[/<SPECIALTY>]'."""
from typing import Optional, Tuple

from core.domain.nexus.entities import ALLOWED_ROLES

SPECIALTIES = frozenset({"DEV", "DEVOPS", "QA", "PRODUTO"})
_PREFIX = "agent:"


def make_identity(role: str, specialty: Optional[str] = None) -> str:
    if role not in ALLOWED_ROLES:
        raise ValueError(f"role inválido: {role!r}")
    if specialty is None:
        return f"{_PREFIX}{role}"
    if specialty not in SPECIALTIES:
        raise ValueError(f"specialty inválida: {specialty!r}")
    return f"{_PREFIX}{role}/{specialty}"


def parse_identity(identity: object) -> Optional[Tuple[str, Optional[str]]]:
    if not isinstance(identity, str) or not identity.startswith(_PREFIX):
        return None
    role, sep, specialty = identity[len(_PREFIX):].partition("/")
    if role not in ALLOWED_ROLES:
        return None
    if not sep:
        return role, None
    if specialty not in SPECIALTIES:
        return None
    return role, specialty

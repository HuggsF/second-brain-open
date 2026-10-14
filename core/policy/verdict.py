"""Vereditos da política: decisão + motivo de vocabulário fechado."""
from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    APPROVE = "APPROVE"
    ESCALATE = "ESCALATE"
    DENY = "DENY"


class Reason(str, Enum):
    read_auto = "read_auto"
    write_local_traced = "write_local_traced"
    prod_read_needs_human = "prod_read_needs_human"
    prod_mutating_never_auto = "prod_mutating_never_auto"
    unknown_tool = "unknown_tool"
    role_not_allowed = "role_not_allowed"
    bad_identity = "bad_identity"
    command_refused = "command_refused"
    malformed_args = "malformed_args"
    policy_error = "policy_error"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: Reason
    detail: str = ""

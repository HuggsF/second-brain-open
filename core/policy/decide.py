"""decide(): identidade -> classe -> permissão do papel -> argumentos -> classe decide."""
from core.domain.nexus.entities import TOOL_REGISTRY
from core.policy.classes import TOOL_CLASSES, ToolClass
from core.policy.commands import blocked_phrase, check_read_only
from core.policy.identity import parse_identity
from core.policy.verdict import Decision, Reason, Verdict


def _decide(identity: object, tool: object, args: object) -> Verdict:
    parsed = parse_identity(identity)
    if parsed is None:
        return Verdict(Decision.DENY, Reason.bad_identity)
    role, _ = parsed

    if not isinstance(tool, str) or tool not in TOOL_CLASSES:
        return Verdict(Decision.DENY, Reason.unknown_tool)
    tool_class = TOOL_CLASSES[tool]

    if tool not in TOOL_REGISTRY.get(role, ()):
        return Verdict(Decision.DENY, Reason.role_not_allowed, f"{role} -> {tool}")

    if tool == "run_safe_command":
        command = args.get("command") if isinstance(args, dict) else None
        if not isinstance(command, str):
            return Verdict(Decision.DENY, Reason.malformed_args, "command deve ser texto")
        phrase = blocked_phrase(command)
        if phrase:
            return Verdict(Decision.DENY, Reason.command_refused, f"blocked: {phrase}")
        refusal = check_read_only(command)
        if refusal:
            return Verdict(Decision.DENY, Reason.command_refused, refusal)

    if tool_class is ToolClass.READ:
        return Verdict(Decision.APPROVE, Reason.read_auto)
    if tool_class is ToolClass.WRITE_LOCAL:
        return Verdict(Decision.APPROVE, Reason.write_local_traced)
    if tool_class is ToolClass.PROD_READ:
        return Verdict(Decision.ESCALATE, Reason.prod_read_needs_human)
    return Verdict(Decision.DENY, Reason.prod_mutating_never_auto)


def decide(identity: object, tool: object, args: object) -> Verdict:
    try:
        return _decide(identity, tool, args)
    except Exception as exc:  # a política nunca levanta
        return Verdict(Decision.DENY, Reason.policy_error, type(exc).__name__)

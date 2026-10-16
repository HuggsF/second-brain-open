"""Corretor único: decide (core.policy), executa (core.tools) e grava um rastro com a identidade do agente.

Sprint 7 (Integração): O pipeline MoE/Zero-Trust é opcionalmente ativado passando
persona_id= ao call(). Sem persona_id, o comportamento é idêntico ao anterior.
"""
import sys
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core import events, tracing
from core.events import publish
from core.policy import Decision, Reason, Verdict, decide, parse_identity
from core.tools import IMPLEMENTATIONS

_SERVER = "broker"


def _name(value: object) -> str:
    return value if isinstance(value, str) else type(value).__name__


def _write(record: Dict[str, Any], path: Optional[Path]) -> None:
    try:
        tracing.write_record(record, path or tracing.TRACE_LOG)
    except Exception as exc:
        print(f"trace: could not write broker record ({type(exc).__name__})", file=sys.stderr)


def _publish_event(event: Dict[str, Any]) -> None:
    try:
        publish(event)
    except Exception as exc:
        print(f"broker: could not publish event ({type(exc).__name__})", file=sys.stderr)


def _validate_persona(persona_id: str):
    """Valida que persona_id corresponde a um contrato builtin (INV-N14)."""
    from core.schema.persona_contract import get_builtin_contract
    contract = get_builtin_contract(persona_id)
    if contract is None:
        raise ValueError(f"Unknown persona: {persona_id}")
    return contract

def record_event(identity: str, event: str, status: str, args: Optional[dict] = None,
                 task_id: Optional[str] = None, trace_path: Optional[Path] = None) -> None:
    """Grava um evento solto no rastro (portões). Nunca lança."""
    try:
        trace_id, label = tracing.derive_trace_id(task_id)
        _write({
            "schema_version": 1,
            "ts": tracing.now_iso(),
            "trace_id": trace_id,
            "span_id": tracing.new_span_id(),
            "parent_span_id": None,
            "task_label": label,
            "server": _SERVER,
            "tool": event if isinstance(event, str) else "unknown",
            "event": event if isinstance(event, str) else "unknown",
            "status": status if isinstance(status, str) else "unknown",
            "caller": identity if parse_identity(identity) else "unknown",
            "args": tracing.redact_args(args if isinstance(args, dict) else None),
            "error_type": None,
        }, trace_path)
    except Exception as exc:
        print(f"trace: could not record event ({type(exc).__name__})", file=sys.stderr)


async def _execute(tool: str, args: dict) -> Tuple[Dict[str, Any], Optional[str]]:
    """(resultado, nome da classe da exceção se a ferramenta levantou)."""
    try:
        result = await IMPLEMENTATIONS[tool](**args)
    except Exception as exc:  # só o nome da classe: a mensagem pode conter segredos
        return {"error": type(exc).__name__}, type(exc).__name__
    return (result if isinstance(result, dict) else {"result": result}), None


async def call(identity: str, tool: str, args: dict, task_id: Optional[str] = None, *,
               approved: bool = False, trace_path: Optional[Path] = None,
               persona_id: Optional[str] = None, task_text: str = "") -> dict:
    started_at = tracing.now_iso()
    started = time.perf_counter()
    tool_name = _name(tool)
    status = "error"
    error_type: Optional[str] = "BrokerError"
    result: Dict[str, Any] = {"tool": tool_name, "verdict": Decision.DENY.value,
                              "reason": Reason.policy_error.value, "refused": True,
                              "error": Reason.policy_error.value}
    state = None
    executed = False
    token = None
    try:
        trace_id, label = tracing.derive_trace_id(task_id)

        # ─── INV-N14: Reject unknown persona before any gate ───
        if persona_id:
            _validate_persona(persona_id)  # ValueError se desconhecida

        # ─── Sprint 7: Pre-call pipeline (PD-OVR-006: roda SEMPRE) ───
        try:
            from core.integration import pre_call_pipeline
            pre_result = pre_call_pipeline(persona_id, tool_name, args if isinstance(args, dict) else {}, task_text)
            if not pre_result.allowed:
                _publish_event({
                    "id": str(uuid.uuid4()),
                    "type": "tool.denied",
                    "timestamp": int(time.time() * 1000),
                    "channel": "tool",
                    "agentId": persona_id or "system",
                    "missionId": label,
                    "tool_name": tool_name,
                    "status": "denied",
                    "reason": pre_result.reason,
                    "payload": {
                        "tool_name": tool_name,
                        "status": "denied",
                        "reason": pre_result.reason,
                    },
                })
                head = {"tool": tool_name, "verdict": Decision.DENY.value, "reason": pre_result.reason}
                result = {**head, "refused": True, "error": pre_result.reason, "details": pre_result.details}
                status, error_type = "refused", None
                state = tracing.CallState(
                    trace_id=trace_id, span_id=tracing.new_span_id(), server=_SERVER, tool=tool_name,
                    path=trace_path or tracing.TRACE_LOG,
                    caller=identity if parse_identity(identity) else "unknown",
                    task_label=label, started_at=started_at,
                )
                return result
        except ImportError as exc:
            _publish_event({
                "id": str(uuid.uuid4()),
                "type": "tool.denied",
                "timestamp": int(time.time() * 1000),
                "channel": "tool",
                "agentId": persona_id or "system",
                "missionId": label,
                "tool_name": tool_name,
                "status": "denied",
                "reason": "security_pipeline_unavailable",
                "payload": {
                    "tool_name": tool_name,
                    "status": "denied",
                    "reason": "security_pipeline_unavailable",
                },
            })
            # H-06: ImportError desativa TODA a pipeline de segurança.
            # BLOQUEAR execução (fail-closed) — NUNCA permitir tool sem gates.
            print(f"SECURITY DEGRADED: pre_call_pipeline unavailable ({exc}). "
                  f"BLOCKING execution for {tool_name}.", file=sys.stderr)
            result = {"tool": tool_name, "verdict": Decision.DENY.value,
                       "reason": "security_pipeline_unavailable", "refused": True,
                       "error": f"security gates unavailable: {exc}"}
            status, error_type = "refused", None
            state = tracing.CallState(
                trace_id=trace_id, span_id=tracing.new_span_id(), server=_SERVER, tool=tool_name,
                path=trace_path or tracing.TRACE_LOG,
                caller=identity if parse_identity(identity) else "unknown",
                task_label=label, started_at=started_at,
            )
            return result

        state = tracing.CallState(
            trace_id=trace_id, span_id=tracing.new_span_id(), server=_SERVER, tool=tool_name,
            path=trace_path or tracing.TRACE_LOG,
            caller=identity if parse_identity(identity) else "unknown",
            task_label=label, started_at=started_at,
        )
        verdict: Verdict = (decide(identity, tool, args) if isinstance(args, dict)
                            else Verdict(Decision.DENY, Reason.malformed_args, "args deve ser dict"))
        head = {"tool": tool_name, "verdict": verdict.decision.value, "reason": verdict.reason.value}
        if verdict.decision is Decision.DENY:
            _publish_event({
                "id": str(uuid.uuid4()),
                "type": "tool.denied",
                "timestamp": int(time.time() * 1000),
                "channel": "tool",
                "agentId": persona_id or "system",
                "missionId": label,
                "tool_name": tool_name,
                "status": "denied",
                "reason": verdict.reason.value,
                "payload": {
                    "tool_name": tool_name,
                    "status": "denied",
                    "reason": verdict.reason.value,
                },
            })
            result = {**head, "refused": True, "error": verdict.reason.value}
            status, error_type = "refused", None
        elif verdict.decision is Decision.ESCALATE and approved is not True:
            _publish_event({
                "id": str(uuid.uuid4()),
                "type": "tool.denied",
                "timestamp": int(time.time() * 1000),
                "channel": "tool",
                "agentId": persona_id or "system",
                "missionId": label,
                "tool_name": tool_name,
                "status": "denied",
                "reason": "approval_required",
                "payload": {
                    "tool_name": tool_name,
                    "status": "denied",
                    "reason": "approval_required",
                },
            })
            result = {**head, "approval_required": True, "refused": True, "error": "exige aprovação humana"}
            status, error_type = "escalated", None
        else:
            token = tracing.current_call.set(state)
            start_ms = time.time() * 1000
            args_bytes = len(json.dumps(args, default=str).encode("utf-8")) if args else 0
            _publish_event({
                "id": str(uuid.uuid4()),
                "type": "tool.start",
                "timestamp": int(start_ms),
                "channel": "tool",
                "agentId": persona_id or "system",
                "missionId": label,
                "tool_name": tool_name,
                "status": "start",
                "payload": {
                    "tool_name": tool_name,
                    "status": "start",
                    "payload_bytes": args_bytes,
                },
            })
            try:
                outcome, raised = await asyncio.wait_for(
                    _execute(tool, args), timeout=15.0
                )
            except asyncio.TimeoutError:
                outcome = {"error": "ToolTimeout", "timed_out": True}
                raised = "ToolTimeout"
            duration = int(time.time() * 1000 - start_ms)
            if raised == "ToolTimeout":
                _publish_event({
                    "id": str(uuid.uuid4()),
                    "type": "tool.timeout",
                    "timestamp": int(time.time() * 1000),
                    "channel": "tool",
                    "agentId": persona_id or "system",
                    "missionId": label,
                    "tool_name": tool_name,
                    "status": "timeout",
                    "duration_ms": duration,
                    "payload": {
                        "tool_name": tool_name,
                        "status": "timeout",
                        "duration_ms": duration,
                    },
                })
            else:
                outcome_bytes = len(json.dumps(outcome, default=str).encode("utf-8")) if outcome else 0
                _publish_event({
                    "id": str(uuid.uuid4()),
                    "type": "tool.end",
                    "timestamp": int(time.time() * 1000),
                    "channel": "tool",
                    "agentId": persona_id or "system",
                    "missionId": label,
                    "tool_name": tool_name,
                    "status": "end",
                    "duration_ms": duration,
                    "payload": {
                        "tool_name": tool_name,
                        "status": "end",
                        "duration_ms": duration,
                        "payload_bytes": outcome_bytes,
                    },
                })
            executed = True
            outcome = {k: v for k, v in outcome.items() if k not in ("refused", "approval_required")}
            failed = "error" in outcome
            if failed:
                outcome["error"] = tracing.mask_sensitive(str(outcome["error"]))
            result = {**outcome, **head}
            status = "error" if failed else ("refused" if state.refused else "ok")
            error_type = (raised or "ToolError") if failed else None
    except Exception as exc:  # o corretor nunca levanta
        result = {**result, "tool": tool_name, "error": type(exc).__name__}
        status, error_type = "error", type(exc).__name__
    finally:
        if token is not None:
            tracing.current_call.reset(token)
        if state is not None:
            _write({
                "schema_version": 1,
                "ts": state.started_at,
                "trace_id": state.trace_id,
                "span_id": state.span_id,
                "parent_span_id": None,
                "task_label": state.task_label,
                "server": _SERVER,
                "tool": tool_name,
                "event": "call",
                "status": status,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "caller": state.caller,
                "args": tracing.redact_args(args if isinstance(args, dict) else None),
                "error_type": error_type,
            }, trace_path)

        # ─── Sprint 7: Post-call pipeline (PD-OVR-006: roda SEMPRE) ───
        if state is not None:  # PD-OVR-006: post_call roda SEMPRE (não só com persona_id)
            try:
                from core.integration import post_call_pipeline
                result = post_call_pipeline(
                    tool_name=tool_name,
                    success=(status == "ok"),
                    identity=state.caller,
                    trace_id=state.trace_id,
                    result=result,
                    persona_id=persona_id,
                    executed=executed,
                )
            except ImportError as exc:
                # DD-03: NUNCA silenciar — ImportError desativa DLP, audit e CB feedback
                print(f"SECURITY DEGRADED: post_call_pipeline unavailable ({exc}). "
                      f"DLP/Audit/CB BYPASSED for {tool_name}.", file=sys.stderr)
            except Exception as exc:
                print(f"integration: post_call error ({type(exc).__name__})", file=sys.stderr)
    return result

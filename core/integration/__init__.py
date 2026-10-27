"""Pipeline de integração — conecta todos os módulos MoE/Zero-Trust.

Sprint 7 (Integração): Camada que unifica os módulos dos Sprints 0-6 em um
pipeline coeso, mantendo backward compatibility com os callers existentes.

Componentes integrados:
  - Circuit Breaker + Rate Limiter (Sprint 3 — G3/G5)
  - WORM Audit Trail (Sprint 4 — G8)
  - PersonaContract Registry (Sprint 4 — G7)
  - Forbidden Topics Gate (Sprint 5 — G9)
  - Autonomy Evaluation (Sprint 5 — G11)
  - HITL Protocol (Sprint 6 — G2)
  - Handoff Protocol (Sprint 6 — G10)
  - Explicit RBAC per Persona (Sprint 9 — R11)

O pipeline é opt-in: callers existentes continuam usando broker.call() sem mudanças.
O novo fluxo é ativado passando persona_id= ao call(), que habilita todo o pipeline.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.resilience.circuit_breaker import CircuitBreakerRegistry
from core.resilience.rate_limiter import RateLimiterRegistry
from core.audit.worm_audit import WORMAuditLog
from core.schema.persona_contract import PersonaContract, get_builtin_contract, IOContractConfig
from core.gates.forbidden_topics_gate import ForbiddenTopicsGate
from core.policy.autonomy import evaluate_autonomy
from core.governance.hitl_protocol import HITLPendingStore, HITLRequest, HITLReason
from core import tracing


# ─── Singletons de Integração ────────────────────────────────────────────────

# Registry global de circuit breakers
_cb_registry: Optional[CircuitBreakerRegistry] = None

# Registry global de rate limiters
_rl_registry: Optional[RateLimiterRegistry] = None

# Audit log WORM (lazy init)
_audit_log: Optional[WORMAuditLog] = None

# Forbidden Topics Gate (singleton)
_forbidden_gate: Optional[ForbiddenTopicsGate] = None

# HITL Pending Store (singleton)
_hitl_store: Optional[HITLPendingStore] = None

# Registry de contratos por persona_id
_persona_cache: Dict[str, PersonaContract] = {}

# Caminho padrão do audit log
DEFAULT_AUDIT_PATH = Path("data/worm_audit.jsonl")


def _get_cb_registry() -> CircuitBreakerRegistry:
    """Obtém ou cria o registry global de circuit breakers."""
    global _cb_registry
    if _cb_registry is None:
        _cb_registry = CircuitBreakerRegistry()
    return _cb_registry


def _get_rl_registry() -> RateLimiterRegistry:
    """Obtém ou cria o registry global de rate limiters."""
    global _rl_registry
    if _rl_registry is None:
        _rl_registry = RateLimiterRegistry()
    return _rl_registry


def _get_audit_log(path: Optional[Path] = None) -> WORMAuditLog:
    """Obtém ou cria o audit log WORM."""
    global _audit_log
    if _audit_log is None:
        p = path or DEFAULT_AUDIT_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        _audit_log = WORMAuditLog(p)
    return _audit_log


def _get_forbidden_gate() -> ForbiddenTopicsGate:
    """Obtém ou cria o gate de tópicos proibidos."""
    global _forbidden_gate
    if _forbidden_gate is None:
        _forbidden_gate = ForbiddenTopicsGate()
    return _forbidden_gate


def _get_hitl_store() -> HITLPendingStore:
    """Obtém ou cria o store de HITL pendentes."""
    global _hitl_store
    if _hitl_store is None:
        _hitl_store = HITLPendingStore()
    return _hitl_store


def get_persona_contract(persona_id: str) -> Optional[PersonaContract]:
    """Busca o contrato da persona, com cache."""
    if persona_id not in _persona_cache:
        contract = get_builtin_contract(persona_id)
        if contract:
            _persona_cache[persona_id] = contract
    return _persona_cache.get(persona_id)


def reset_all_singletons() -> None:
    """Reset para testes — limpa todos os singletons."""
    global _cb_registry, _rl_registry, _audit_log, _forbidden_gate, _hitl_store
    _cb_registry = None
    _rl_registry = None
    _audit_log = None
    _forbidden_gate = None
    _hitl_store = None
    _persona_cache.clear()


# ─── Pre-call Checks ─────────────────────────────────────────────────────────

class PreCallResult:
    """Resultado dos checks de pré-chamada."""
    __slots__ = ("allowed", "reason", "details")

    def __init__(self, allowed: bool, reason: str = "", details: Optional[Dict[str, Any]] = None):
        self.allowed = allowed
        self.reason = reason
        self.details = details or {}


def check_circuit_breaker(tool_name: str) -> PreCallResult:
    """Verifica se o circuit breaker permite a chamada."""
    cb = _get_cb_registry().get(tool_name)
    if not cb.allow_request():
        return PreCallResult(False, "circuit_breaker_open", cb.stats.to_dict())
    return PreCallResult(True)


def check_rate_limit(tool_name: str) -> PreCallResult:
    """Verifica se o rate limiter permite a chamada."""
    rl = _get_rl_registry()
    if not rl.try_acquire(tool_name):
        bucket = rl.get(tool_name)
        return PreCallResult(False, "rate_limit_exceeded", bucket.get_stats())
    return PreCallResult(True)


def check_rbac(persona_id: Optional[str], tool_name: str) -> PreCallResult:
    """Verifica se a persona tem permissão RBAC para esta tool.

    Ordem de verificação:
    1. Se tool está em denied_tools → bloqueia
    2. Se allowed_tools está definido e tool não está nele → bloqueia
    3. Caso contrário → permite (herda do TOOL_REGISTRY existente)
    """
    if not persona_id:
        return PreCallResult(True, "no_rbac_contract")

    contract = get_persona_contract(persona_id)
    if not contract:
        return PreCallResult(True, "no_contract")

    rbac = getattr(contract, "rbac", None)
    if not rbac:
        return PreCallResult(True, "no_rbac_contract")

    # 1. Deny list takes priority
    if tool_name in rbac.denied_tools:
        return PreCallResult(False, "rbac_denied", {
            "tool": tool_name,
            "rbac_role": rbac.rbac_role,
            "reason": f"{tool_name} está na denied_tools de {rbac.rbac_role}",
        })

    # 2. If allowed_tools defined, tool must be in it
    if rbac.allowed_tools and tool_name not in rbac.allowed_tools:
        return PreCallResult(False, "rbac_not_allowed", {
            "tool": tool_name,
            "rbac_role": rbac.rbac_role,
            "allowed": rbac.allowed_tools,
        })

    return PreCallResult(True, "rbac_ok")


def check_forbidden_topics(text: str, persona_id: Optional[str] = None) -> PreCallResult:
    """Verifica se o texto contém tópicos proibidos."""
    gate = _get_forbidden_gate()
    payload = {"input_text": text}
    # If persona has specific forbidden topics, pass them to the gate
    if persona_id:
        contract = get_persona_contract(persona_id)
        if contract and contract.forbidden_topics:
            payload["forbidden_topics"] = contract.forbidden_topics
    result = gate.evaluate(payload)
    if not result.passed:
        return PreCallResult(False, "forbidden_topic", {
            "message": result.message,
            "details": result.details,
        })
    return PreCallResult(True)


def check_autonomy(persona_id: str, tool_name: str, args: Dict[str, Any]) -> PreCallResult:
    """Avalia o nível de autonomia da persona para esta tool."""
    contract = get_persona_contract(persona_id)
    if contract is None:
        # Sem contrato: permite (backward compatible)
        return PreCallResult(True, "no_contract")

    verdict = evaluate_autonomy(
        autonomy_level=contract.security.autonomy_level,
        tool_name=tool_name,
        args=args,
        auto_approve_up_to_brl=contract.security.auto_approve_up_to_brl,
    )

    if verdict.requires_hitl:
        return PreCallResult(False, "requires_hitl", {
            "decision": verdict.decision.value,
            "level": verdict.level.value,
            "reason": verdict.reason.value,
            "detail": verdict.detail,
        })
    return PreCallResult(True, verdict.reason.value)


def validate_input_contract(persona_id: Optional[str], args: Dict[str, Any]) -> PreCallResult:
    """Valida que os campos obrigatórios do input estão presentes."""
    if not persona_id:
        return PreCallResult(True, "no_contract")
    contract = get_persona_contract(persona_id)
    if not contract or not getattr(contract, "io_contract", None) or not contract.io_contract.required_input_fields:
        return PreCallResult(True, "no_input_contract")

    args_dict = args if isinstance(args, dict) else {}
    missing = [
        f for f in contract.io_contract.required_input_fields
        if f not in args_dict
    ]
    if missing:
        return PreCallResult(False, "input_contract_violation", {
            "missing_fields": missing,
            "required": contract.io_contract.required_input_fields,
        })
    return PreCallResult(True, "input_contract_valid")


# ─── Post-call Actions ───────────────────────────────────────────────────────

def record_tool_outcome(tool_name: str, success: bool) -> None:
    """Registra o resultado da tool no circuit breaker."""
    cb = _get_cb_registry().get(tool_name)
    if success:
        cb.record_success()
    else:
        cb.record_failure()


def audit_call(
    event_type: str,
    actor: str,
    trace_id: str,
    payload: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    audit_path: Optional[Path] = None,
) -> None:
    """Registra uma chamada no WORM audit trail."""
    try:
        log = _get_audit_log(audit_path)
        log.append(
            event_type=event_type,
            actor=actor,
            trace_id=trace_id,
            payload=payload,
            metadata=metadata,
        )
    except Exception as exc:
        print(f"audit: could not write WORM record ({type(exc).__name__})", file=sys.stderr)


def validate_output_contract(persona_id: Optional[str], result: Dict[str, Any]) -> Dict[str, Any]:
    """Valida que os campos obrigatórios do output estão presentes.

    Returns:
        Dict with validation result:
        {"valid": bool, "missing_fields": [...], "strict": bool}
    """
    if not persona_id:
        return {"valid": True, "missing_fields": [], "strict": False}
    contract = get_persona_contract(persona_id)
    if not contract or not getattr(contract, "io_contract", None):
        return {"valid": True, "missing_fields": [], "strict": False}

    io = contract.io_contract
    if not io.required_output_fields:
        return {"valid": True, "missing_fields": [], "strict": io.output_schema_strict}

    result_dict = result if isinstance(result, dict) else {}
    missing = [f for f in io.required_output_fields if f not in result_dict]
    return {
        "valid": len(missing) == 0,
        "missing_fields": missing,
        "strict": io.output_schema_strict,
    }


# ─── Pipeline Completo ────────────────────────────────────────────────────────

def pre_call_pipeline(
    persona_id: Optional[str],
    tool_name: str,
    args: Dict[str, Any],
    task_text: str = "",
) -> PreCallResult:
    """Executa todos os checks de pré-chamada em sequência.

    PD-OVR-004: CB/RL fail-open; RBAC/FT/Autonomy/Input fail-closed.
    PD-OVR-006: Gates globais (CB, RL, FT) rodam SEMPRE, independente de persona_id.
    INV-N08: Exceção em gate de segurança → fail-closed.
    """
    # 1. Circuit Breaker — fail-open (PD-OVR-004)
    try:
        cb_result = check_circuit_breaker(tool_name)
        if not cb_result.allowed:
            return cb_result
    except Exception:
        print(f"warn: CB check failed for {tool_name}, allowing", file=sys.stderr)

    # 2. Rate Limiter — fail-open (PD-OVR-004)
    try:
        rl_result = check_rate_limit(tool_name)
        if not rl_result.allowed:
            return rl_result
    except Exception:
        print(f"warn: RL check failed for {tool_name}, allowing", file=sys.stderr)

    # 3. Forbidden Topics — SEMPRE, fail-closed (INV-N05, INV-N08)
    # H-08: Inspecionar task_text E args serializados (não só task_text)
    ft_text = task_text or ""
    if args:
        try:
            args_text = json.dumps(args, ensure_ascii=False, default=str)
            ft_text = f"{ft_text} {args_text}".strip()
        except (TypeError, ValueError):
            pass
    if ft_text.strip():
        try:
            ft_result = check_forbidden_topics(ft_text, persona_id=persona_id)
            if not ft_result.allowed:
                return ft_result
        except Exception:
            return PreCallResult(False, "forbidden_topics_internal_error")

    # 4-6. Security gates — só com persona_id, fail-closed
    if persona_id:
        # 4. RBAC
        try:
            rbac_result = check_rbac(persona_id, tool_name)
            if not rbac_result.allowed:
                return rbac_result
        except Exception:
            return PreCallResult(False, "rbac_internal_error")

        # 5. Autonomy
        try:
            auto_result = check_autonomy(persona_id, tool_name, args)
            if not auto_result.allowed:
                return auto_result
        except Exception:
            return PreCallResult(False, "autonomy_internal_error")

        # 6. Input Contract
        try:
            io_result = validate_input_contract(persona_id, args)
            if not io_result.allowed:
                return io_result
        except Exception:
            return PreCallResult(False, "input_contract_internal_error")

    return PreCallResult(True, "all_checks_passed")


def _redact_value(v: Any) -> Any:
    """Aplica DLP recursivamente em qualquer valor, preservando tipo.

    NEW-01: Estendido para escanear tuple, set, frozenset e qualquer iterável,
    prevenindo bypass de DLP quando PII está em tipos iteráveis não-list.
    """
    from core.security.dlp_guardrail import inspect_text
    if isinstance(v, str):
        r = inspect_text(v)
        return r.redacted_text if r.has_pii else v
    elif isinstance(v, dict):
        return _redact_dict_values(v)
    elif isinstance(v, (list, tuple, set, frozenset)):
        redacted_items = [_redact_value(item) for item in v]
        return type(v)(redacted_items)
    elif hasattr(v, '__iter__') and not isinstance(v, (str, bytes)):
        return [_redact_value(item) for item in v]
    return v


def _redact_dict_values(d: dict) -> dict:
    """Aplica DLP em cada valor do dict, preservando estrutura.

    F-04: Agora processa listas recursivamente para prevenir vazamento
    de PII em arrays de resultado (ex: {"items": ["123.456.789-00"]}).
    """
    redacted = {}
    for k, v in d.items():
        redacted[k] = _redact_value(v)
    return redacted


def post_call_pipeline(
    tool_name: str,
    success: bool,
    identity: str,
    trace_id: str,
    result: Dict[str, Any],
    persona_id: Optional[str] = None,
    audit_path: Optional[Path] = None,
    executed: bool = True,
) -> Any:
    """Executa ações pós-chamada.

    1. Atualiza Circuit Breaker com resultado
    2. Grava WORM audit trail (se persona tem audit habilitado)
    3. Validação de Output Contract (soft enforcement se strict=True)
    """
    # 1. Circuit Breaker feedback — só se a tool foi de facto executada (INV-N02)
    if executed:
        record_tool_outcome(tool_name, success)

        # DLP scan no resultado (INV-N12)
        if success and result:
            try:
                from core.security.dlp_guardrail import inspect_text
                if isinstance(result, dict):
                    # Verificar se algum valor contém PII
                    text_to_scan = json.dumps(result, ensure_ascii=False, default=str)
                    dlp_check = inspect_text(text_to_scan)
                    if dlp_check.has_pii:
                        redacted = _redact_dict_values(result)
                        result.clear()
                        result.update(redacted)
                elif isinstance(result, str):
                    dlp_check = inspect_text(result)
                    if dlp_check.has_pii:
                        result = dlp_check.redacted_text
            except Exception as exc:
                # DD-02/PD-OVR-004: DLP é fail-closed — se o scan falha, redacta o resultado
                # inteiro para prevenir vazamento de PII (INV-N12)
                print(f"error: DLP scan on result failed ({type(exc).__name__}), "
                      f"redacting result for {tool_name}", file=sys.stderr)
                if isinstance(result, dict):
                    result.clear()
                    result.update({"error": "dlp_scan_failed", "tool": tool_name})
                else:
                    # String ou outro tipo — substitui por mensagem segura
                    result = {"error": "dlp_scan_failed", "tool": tool_name}

    # 2. WORM Audit (SEMPRE, mas com event_type correto)
    should_audit = True
    if persona_id:
        contract = get_persona_contract(persona_id)
        if contract and not contract.audit.worm_enabled:
            should_audit = False

    event_type = f"broker.call.{tool_name}" if executed else f"broker.blocked.{tool_name}"
    if should_audit:
        audit_call(
            event_type=event_type,
            actor=identity,
            trace_id=trace_id,
            payload={"status": "ok" if success else "error", "tool": tool_name},
            metadata={"persona_id": persona_id or "unknown"},
            audit_path=audit_path,
        )

    # 3. Output Contract validation — só se executada
    if executed and persona_id and success:
        output_check = validate_output_contract(persona_id, result)
        if not output_check["valid"] and output_check["strict"]:
            # Log warning but don't block (soft enforcement)
            print(f"output_contract: strict violation for {persona_id} — missing {output_check['missing_fields']}", file=sys.stderr)

    return result  # OBRIGATÓRIO: chamador deve usar o retorno


def run_post_mission_gates(
    persona_id: Optional[str],
    mission_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Executa os post-mission gates declarados no contrato da persona.

    Args:
        persona_id: ID da persona para lookup do contrato.
        mission_results: Lista de resultados das tools executadas na missão.

    Returns:
        Dict com resultado dos gates. Formato:
        {
            "gates_run": ["grounding_sha256", ...],
            "all_passed": True/False,
            "gate_results": [...],
        }
    """
    if not persona_id:
        return {"gates_run": [], "all_passed": True, "gate_results": []}

    contract = get_persona_contract(persona_id)
    if not contract or not contract.quality_gates.post_mission:
        return {"gates_run": [], "all_passed": True, "gate_results": []}

    from core.gates import CompoundGatePipeline
    pipeline = CompoundGatePipeline()

    # Build payload from mission results for gate evaluation
    payload = {}
    for result in mission_results:
        # Merge citations for grounding gate
        if "sources" in result:
            existing = payload.get("citations", [])
            for src in result["sources"]:
                doc_name = src.get("document") or src.get("source", "")
                existing.append({
                    "source": doc_name,
                    "document": doc_name,
                    "hash": src.get("score", ""),
                    "sha256": src.get("sha256"),
                })
            payload["citations"] = existing

    gate_result = pipeline.run_all(payload)
    declared_gates = contract.quality_gates.post_mission

    return {
        "gates_run": declared_gates,
        "all_passed": gate_result["all_passed"],
        "gate_results": gate_result["gate_results"],
    }


# ─── Dynamic Tool Unbind (Sprint 9 — R10) ────────────────────────────────────

def get_unbound_tools() -> List[str]:
    """Retorna lista de tools que devem ser desvinculadas (CB OPEN).
    
    Consulta o CircuitBreakerRegistry para identificar tools com
    circuito aberto e retorna seus nomes para dynamic unbind.
    """
    return _get_cb_registry().get_open_tools()


def unbind_open_circuit_tools(
    steps: List[Dict[str, Any]],
    persona_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Remove tools com CB aberto dos steps e injeta fallback.
    
    Para cada step cuja tool tem circuito aberto:
    1. Substitui a tool por uma mensagem de fallback
    2. Marca o step como "unbound" para auditoria
    
    Args:
        steps: Lista de steps da missão.
        persona_id: ID da persona para lookup de fallback.
    
    Returns:
        Tupla (steps_filtrados, lista_de_tools_removidas)
    """
    unbound_tools = get_unbound_tools()
    if not unbound_tools:
        return steps, []
    
    removed = []
    filtered_steps = []
    for step in steps:
        tool = step.get("tool", "")
        if tool in unbound_tools:
            removed.append(tool)
            # Inject fallback step instead
            fallback_step = dict(step)
            fallback_step["_original_tool"] = tool
            fallback_step["_unbound_reason"] = "circuit_breaker_open"
            fallback_step["tool"] = None  # Skip execution
            fallback_step["bubble"] = f"⚡ {tool} indisponível (circuit breaker aberto)"
            filtered_steps.append(fallback_step)
        else:
            filtered_steps.append(step)
    
    return filtered_steps, removed


# ─── Dashboard / Observabilidade ─────────────────────────────────────────────

def get_resilience_dashboard() -> Dict[str, Any]:
    """Retorna dados de observabilidade de resiliência para dashboard."""
    return {
        "circuit_breakers": _get_cb_registry().get_all_stats(),
        "rate_limiters": _get_rl_registry().get_all_stats(),
        "hitl_pending": len(_get_hitl_store().get_pending()),
    }

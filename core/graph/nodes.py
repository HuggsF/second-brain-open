"""7 funções-nó async puras para o Node Loop Graph.

Cada nó segue o contrato::

    async def node_name(state: GraphState) -> GraphState

Princípios:
- **Imutabilidade** — retorna ``{**state, ...}``; nunca muta o original.
- **Lazy imports** — dependências pesadas só são importadas dentro do corpo
  da função para evitar efeitos colaterais de importação.
- **Defensividade** — erros esperados (policy denial, invalid agent) são
  capturados e registrados no state; exceções inesperadas propagam para
  o runner, que as trata com ``add_error`` + ``status="failed"``.

Nós
---
1. ``plan_node``      — Decompõe a tarefa em steps via keyword matching
2. ``gate_node``      — Executa mission guard gates (DAG, DLP, grounding)
3. ``route_node``     — MoE routing dinâmico + unbind de CB abertos
4. ``execute_node``   — Executa o step corrente via ``broker.call``
5. ``validate_node``  — Valida o resultado do último step
6. ``correct_node``   — Incrementa o contador de retry
7. ``post_gate_node`` — Executa quality gates pós-missão
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from core.state import (
    GraphState,
    add_error,
    add_message,
    increment_attempt,
    is_circuit_broken,
)

logger = logging.getLogger(__name__)

__all__: list[str] = [
    "plan_node",
    "gate_node",
    "route_node",
    "execute_node",
    "validate_node",
    "correct_node",
    "post_gate_node",
]


# ──────────────────────────────────────────────────────────────────────
# 1. plan_node
# ──────────────────────────────────────────────────────────────────────


async def plan_node(state: GraphState) -> GraphState:
    """Decompose task text into a list of execution steps.

    Replicates the keyword-based pattern matching from
    ``backend.orchestrator._match_pattern`` and enforces
    ``max_hops`` from the manager's ``PersonaContract``.

    Reads
        ``metadata["task_text"]``, ``metadata["mission_id"]``

    Writes
        ``metadata["steps"]``, ``metadata["agents_involved"]``,
        ``metadata["manager_persona_id"]``, ``metadata["current_step_index"]``,
        ``metadata["step_results"]``, ``status="running"``
    """
    # Lazy imports — backend.orchestrator has heavy module-level side effects
    from backend.orchestrator import (  # noqa: WPS433
        AGENT_PERSONA_MAP,
        DEFAULT_STEPS,
        MISSION_PATTERNS,
    )
    from core.integration import get_persona_contract  # noqa: WPS433

    metadata: dict[str, Any] = {**state.get("metadata", {})}
    task_text: str = metadata.get("task_text", "")
    mission_id: int = metadata.get("mission_id", 0)

    # ── Keyword pattern matching ──────────────────────────────────
    task_lower = task_text.lower()
    best_pattern: dict[str, Any] | None = None
    best_score = 0

    for pattern in MISSION_PATTERNS:
        score = sum(1 for kw in pattern["keywords"] if kw in task_lower)
        if score > best_score:
            best_score = score
            best_pattern = pattern

    if best_pattern is not None and best_score > 0:
        steps: list[dict[str, Any]] = copy.deepcopy(best_pattern["steps"])
    else:
        steps = copy.deepcopy(DEFAULT_STEPS)

    # Inject user query into search_knowledge_base steps with empty query
    for step in steps:
        if (
            step.get("tool") == "search_knowledge_base"
            and not step.get("input", {}).get("query")
        ):
            step.setdefault("input", {})["query"] = task_text

    # ── Enforce max_hops from manager persona contract ────────────
    manager_persona_id = AGENT_PERSONA_MAP.get("manager", "maia-orchestrator")
    contract = get_persona_contract(manager_persona_id)

    if contract is not None:
        max_hops = getattr(
            getattr(contract, "quality_gates", None), "max_hops", None
        )
        if max_hops is not None and len(steps) > max_hops:
            logger.warning(
                "plan_node: truncating %d steps to max_hops=%d (persona=%s)",
                len(steps),
                max_hops,
                manager_persona_id,
            )
            steps = steps[:max_hops]

    # ── Collect agents involved ───────────────────────────────────
    agents_involved = sorted({step.get("agent", "unknown") for step in steps})

    metadata["steps"] = steps
    metadata["agents_involved"] = agents_involved
    metadata["manager_persona_id"] = manager_persona_id
    metadata["current_step_index"] = 0
    metadata["step_results"] = []

    logger.info(
        "plan_node: %d steps, agents=%s, mission=%d",
        len(steps),
        agents_involved,
        mission_id,
    )

    state = add_message(
        {**state, "metadata": metadata, "status": "running"},
        role="system",
        content=f"Plan: {len(steps)} steps for mission M{mission_id}",
    )
    return state


# ──────────────────────────────────────────────────────────────────────
# 2. gate_node
# ──────────────────────────────────────────────────────────────────────


async def gate_node(state: GraphState) -> GraphState:
    """Run pre-execution mission guard gates.

    Calls ``check_mission(steps, mission_id)`` which runs DAG validation,
    DLP, grounding and rule gates.  Maps the semaphore to an action:

    - ``GREEN`` → ``proceed`` (continue execution)
    - ``YELLOW`` → ``approval`` (HITL: sets ``needs_approval=True``)
    - ``RED`` → ``block`` (sets ``status="failed"``)

    Reads
        ``metadata["steps"]``, ``metadata["mission_id"]``

    Writes
        ``metadata["gate_result"]``, ``metadata["needs_approval"]`` (if YELLOW),
        ``status``
    """
    from core.mission_guard import check_mission  # noqa: WPS433

    metadata: dict[str, Any] = {**state.get("metadata", {})}
    steps: list[dict[str, Any]] = metadata.get("steps", [])
    mission_id: int = metadata.get("mission_id", 0)

    result = check_mission(steps, mission_id)
    metadata["gate_result"] = result
    action: str = result.get("action", "proceed")

    if action == "block":
        logger.warning(
            "gate_node: mission BLOCKED semaphore=%s (mission=%d)",
            result.get("semaphore"),
            mission_id,
        )
        metadata["needs_approval"] = False
        return {**state, "metadata": metadata, "status": "failed"}

    if action == "approval":
        logger.info(
            "gate_node: mission requires APPROVAL semaphore=%s (mission=%d)",
            result.get("semaphore"),
            mission_id,
        )
        metadata["needs_approval"] = True
        return {**state, "metadata": metadata}

    # action == "proceed"
    logger.info(
        "gate_node: mission PROCEED semaphore=%s (mission=%d)",
        result.get("semaphore"),
        mission_id,
    )
    metadata["needs_approval"] = False
    return {**state, "metadata": metadata}


# ──────────────────────────────────────────────────────────────────────
# 3. route_node
# ──────────────────────────────────────────────────────────────────────


async def route_node(state: GraphState) -> GraphState:
    """Apply MoE dynamic routing and unbind circuit-broken tools.

    For each step, the MoE router may reassign the agent if it finds a
    better match with ``confidence_score >= 0.3`` and ``is_fallback=False``.
    Then ``unbind_open_circuit_tools`` removes tools with open circuit
    breakers, setting their ``tool`` to ``None``.

    Reads
        ``metadata["steps"]``, ``metadata["task_text"]``,
        ``metadata["manager_persona_id"]``

    Writes
        ``metadata["steps"]`` (enriched), ``metadata["unbound_tools"]``
    """
    from core.integration import unbind_open_circuit_tools  # noqa: WPS433
    from core.routing.moe_router import MoERouter  # noqa: WPS433

    metadata: dict[str, Any] = {**state.get("metadata", {})}
    steps: list[dict[str, Any]] = metadata.get("steps", [])
    task_text: str = metadata.get("task_text", "")
    manager_persona_id: str | None = metadata.get("manager_persona_id")

    # ── MoE dynamic routing per step ──────────────────────────────
    # Replicates orchestrator._route_agent_for_step logic:
    # only overrides if confidence >= 0.3 AND not fallback
    router = MoERouter()
    for step in steps:
        original_agent = step.get("agent", "")
        step_context = f"{task_text} {step.get('bubble', '')}"
        decision = router.route(step_context)

        if (
            decision.selected_persona != original_agent
            and decision.confidence_score >= 0.3
            and not decision.is_fallback
        ):
            logger.info(
                "route_node: rerouting step tool='%s' from '%s' -> '%s' "
                "(confidence=%.2f)",
                step.get("tool"),
                original_agent,
                decision.selected_persona,
                decision.confidence_score,
            )
            step["agent"] = decision.selected_persona

    # ── Unbind tools with open circuit breakers ───────────────────
    # unbind_open_circuit_tools(steps, persona_id) -> (steps, removed_names)
    steps, unbound_tools = unbind_open_circuit_tools(steps, manager_persona_id)

    if unbound_tools:
        logger.warning("route_node: unbound tools (CB open): %s", unbound_tools)

    metadata["steps"] = steps
    metadata["unbound_tools"] = unbound_tools

    return {**state, "metadata": metadata}


# ──────────────────────────────────────────────────────────────────────
# 4. execute_node
# ──────────────────────────────────────────────────────────────────────


async def execute_node(state: GraphState) -> GraphState:
    """Execute the current step via ``broker.call``.

    Handles three cases per step:
    1. **Unbound tool** (``tool is None``) — skips with a marker result.
    2. **Invalid agent** — catches ``ValueError`` from ``make_identity``.
    3. **Normal execution** — calls ``broker.call`` and records the result.

    Reads
        ``metadata["steps"]``, ``metadata["current_step_index"]``,
        ``metadata["task_text"]``, ``metadata["mission_id"]``,
        ``metadata["manager_persona_id"]``

    Writes
        ``metadata["step_results"]`` (append), ``metadata["current_step_index"]``++
    """
    from core.broker import call as broker_call  # noqa: WPS433
    from core.policy import make_identity  # noqa: WPS433

    metadata: dict[str, Any] = {**state.get("metadata", {})}
    steps: list[dict[str, Any]] = metadata.get("steps", [])
    step_index: int = metadata.get("current_step_index", 0)
    task_text: str = metadata.get("task_text", "")
    mission_id: int = metadata.get("mission_id", 0)
    persona_id: str | None = metadata.get("manager_persona_id")

    # Guard: no more steps
    if step_index >= len(steps):
        logger.warning(
            "execute_node: step_index=%d >= len(steps)=%d, nothing to execute",
            step_index,
            len(steps),
        )
        return state

    step = steps[step_index]
    agent: str = step.get("agent", "unknown")
    tool: str | None = step.get("tool")
    args: dict[str, Any] = step.get("input", {})

    # ── Case 1: Unbound tool (CB open → tool is None) ────────────
    if tool is None:
        logger.info(
            "execute_node: step %d/%d tool unbound, skipping (agent=%s)",
            step_index + 1,
            len(steps),
            agent,
        )
        result: dict[str, Any] = {
            "unbound": True,
            "agent": agent,
            "step_index": step_index,
            "reason": step.get("_unbound_reason", "tool_unavailable"),
        }
        step_results = [*metadata.get("step_results", []), result]
        metadata["step_results"] = step_results
        metadata["current_step_index"] = step_index + 1
        return {**state, "metadata": metadata}

    # ── Case 2: Build identity ────────────────────────────────────
    try:
        identity = make_identity(agent)
    except ValueError as exc:
        logger.error(
            "execute_node: invalid agent '%s' at step %d: %s",
            agent,
            step_index,
            exc,
        )
        result = {
            "error": True,
            "agent": agent,
            "tool": tool,
            "step_index": step_index,
            "reason": f"invalid_agent: {exc}",
        }
        step_results = [*metadata.get("step_results", []), result]
        metadata["step_results"] = step_results
        metadata["current_step_index"] = step_index + 1
        return add_error(
            {**state, "metadata": metadata},
            node_name="execute_node",
            error_type="InvalidAgent",
            message=f"Step {step_index} agent '{agent}': {exc}",
        )

    # ── Case 3: Normal execution via broker ───────────────────────
    task_id = f"M{mission_id}"
    logger.info(
        "execute_node: step %d/%d agent=%s tool=%s task=%s",
        step_index + 1,
        len(steps),
        agent,
        tool,
        task_id,
    )

    result = await broker_call(
        identity,
        tool,
        args,
        task_id,
        persona_id=persona_id,
        task_text=task_text,
    )

    # Enrich result with step metadata for downstream validation
    result["agent"] = agent
    result["tool"] = tool
    result["step_index"] = step_index

    step_results = [*metadata.get("step_results", []), result]
    metadata["step_results"] = step_results
    metadata["current_step_index"] = step_index + 1

    return {**state, "metadata": metadata}


# ──────────────────────────────────────────────────────────────────────
# 5. validate_node
# ──────────────────────────────────────────────────────────────────────


async def validate_node(state: GraphState) -> GraphState:
    """Validate the last step result.

    Checks for errors, policy refusals, and approval requirements.
    On failure, records an error via ``add_error`` (which does NOT
    change ``current_attempt`` — that's ``correct_node``'s job).

    Reads
        ``metadata["step_results"][-1]``

    Writes
        ``errors`` (via ``add_error``) if validation fails
    """
    metadata = state.get("metadata", {})
    step_results: list[dict[str, Any]] = metadata.get("step_results", [])

    if not step_results:
        return state

    last_result = step_results[-1]
    step_index = last_result.get("step_index", "?")
    agent = last_result.get("agent", "unknown")
    tool = last_result.get("tool", "unknown")

    # Skip validation for unbound steps (already handled in execute_node)
    if last_result.get("unbound"):
        logger.debug("validate_node: step %s unbound, skipping", step_index)
        return state

    # Check for policy refusals from broker.call first —
    # broker results have BOTH "refused" and "error" (reason string),
    # so this must come before the generic "error" check.
    if last_result.get("refused"):
        reason = last_result.get("error", last_result.get("reason", "unknown"))

        if last_result.get("approval_required"):
            logger.warning(
                "validate_node: step %s (%s/%s) needs human approval",
                step_index,
                agent,
                tool,
            )
            return add_error(
                state,
                node_name="validate_node",
                error_type="ApprovalRequired",
                message=(
                    f"Step {step_index} ({agent}/{tool}) needs approval: "
                    f"{reason}"
                ),
            )

        logger.warning(
            "validate_node: step %s (%s/%s) DENIED: %s",
            step_index,
            agent,
            tool,
            reason,
        )
        return add_error(
            state,
            node_name="validate_node",
            error_type="PolicyDenial",
            message=(
                f"Step {step_index} ({agent}/{tool}) denied: {reason}"
            ),
        )

    # Check for explicit errors from execute_node (error: True boolean)
    if last_result.get("error") is True:
        reason = last_result.get("reason", "unknown")
        logger.warning(
            "validate_node: step %s (%s/%s) has error: %s",
            step_index,
            agent,
            tool,
            reason,
        )
        return add_error(
            state,
            node_name="validate_node",
            error_type="StepError",
            message=(
                f"Step {step_index} ({agent}/{tool}) error: {reason}"
            ),
        )

    logger.debug("validate_node: step %s (%s/%s) OK", step_index, agent, tool)
    return state


# ──────────────────────────────────────────────────────────────────────
# 6. correct_node
# ──────────────────────────────────────────────────────────────────────


async def correct_node(state: GraphState) -> GraphState:
    """Increment the retry attempt counter.

    This node lives on the correction loop:
    ``validate_node → [fail] → correct_node → [retry|circuit_broken]``

    Uses ``increment_attempt`` from ``core.state`` which returns a new
    state with ``current_attempt + 1``.  The subsequent edge condition
    checks ``is_circuit_broken(state)`` to decide retry vs circuit break.

    Reads
        ``current_attempt``

    Writes
        ``current_attempt`` + 1 via ``increment_attempt``
    """
    logger.info(
        "correct_node: attempt %d -> %d (max=%d)",
        state["current_attempt"],
        state["current_attempt"] + 1,
        state["max_attempts"],
    )
    new_state = increment_attempt(state)

    # Roll back current_step_index so the retry re-executes the SAME step
    # that failed.  execute_node already incremented the index, so we
    # decrement it here to point back to the failed step.
    metadata = new_state.get("metadata", {})
    step_index = metadata.get("current_step_index", 0)
    if step_index > 0:
        updated_metadata = {**metadata, "current_step_index": step_index - 1}
        new_state = {**new_state, "metadata": updated_metadata}
        logger.debug(
            "correct_node: rolled back step_index %d -> %d for retry",
            step_index,
            step_index - 1,
        )

    # If the circuit breaker trips after increment, set terminal status
    # so the edge router can direct to END with the correct status.
    if is_circuit_broken(new_state):
        logger.warning(
            "correct_node: circuit breaker will trip (attempt %d > max %d)",
            new_state["current_attempt"],
            new_state["max_attempts"],
        )
        return {**new_state, "status": "circuit_broken"}

    return new_state


# ──────────────────────────────────────────────────────────────────────
# 7. post_gate_node
# ──────────────────────────────────────────────────────────────────────


async def post_gate_node(state: GraphState) -> GraphState:
    """Run post-mission quality gates and finalize the mission.

    Calls ``run_post_mission_gates(persona_id, mission_results)`` which
    executes gates declared in the persona contract (e.g. grounding_sha256).

    Failed gates are logged as warnings but do **not** block completion —
    this matches the existing orchestrator behavior (L372–388).

    Reads
        ``metadata["step_results"]``, ``metadata["manager_persona_id"]``

    Writes
        ``metadata["post_gate_result"]``, ``status="completed"``
    """
    from core.integration import run_post_mission_gates  # noqa: WPS433

    metadata: dict[str, Any] = {**state.get("metadata", {})}
    step_results: list[dict[str, Any]] = metadata.get("step_results", [])
    persona_id: str | None = metadata.get("manager_persona_id")

    gate_result = run_post_mission_gates(persona_id, step_results)
    metadata["post_gate_result"] = gate_result

    all_passed = gate_result.get("all_passed", True)
    gates_run = gate_result.get("gates_run", [])

    if not all_passed:
        logger.warning(
            "post_gate_node: quality gates FAILED: gates=%s, results=%s",
            gates_run,
            gate_result.get("gate_results"),
        )
        # Record warning in state but do NOT block completion
        state = add_message(
            state,
            role="system",
            content=(
                f"Post-mission gates warning: {gates_run} — "
                f"not all passed but mission completing."
            ),
        )

    logger.info(
        "post_gate_node: gates=%s, all_passed=%s",
        gates_run,
        all_passed,
    )

    return {**state, "metadata": metadata, "status": "completed"}

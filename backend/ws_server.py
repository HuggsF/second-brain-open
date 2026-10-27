"""
WebSocket Server para o Nexus Agent Office.

Recebe comandos do frontend (NEW_TASK, APPROVE, PAUSE, etc.)
e emite eventos de agentes reais via WebSocket.

Roda na porta 8848 (separado do dashboard HTTP na 8847).

Uso: python -m backend.ws_server
"""
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import websockets
except ImportError:
    print("❌ websockets não instalado. Execute: pip install websockets", file=sys.stderr)
    sys.exit(1)

from http.cookies import SimpleCookie

from backend.orchestrator import Orchestrator
from backend.store import Store
from core.domain.workflow.entities import MAX_MISSION_ID, is_valid_mission_id, validate_mission_envelope

_store = None


def get_store():
    global _store
    if _store is None:
        _store = Store(PROJECT_ROOT / ".runtime" / "brain.db")
    return _store


def set_store(store):
    global _store
    _store = store

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nexus-ws")

HOST = "127.0.0.1"
PORT = 8848
CONNECTIONS = set()

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8847",
]

# ── Strangler Fig: migration flag (temporary — remove after full cutover) ──
# Values: "legacy" (default), "graph" (new engine), "shadow" (both, return legacy)
MISSION_ENGINE = os.environ.get("MISSION_ENGINE", "legacy")

# Shared approval events for graph HITL (keyed by mission_id).
# _run_graph_mission() creates and waits on events; APPROVE handler signals them.
_graph_approval_events: dict[int, asyncio.Event] = {}


def _echoable_mission_id(value):
    """missionId seguro para ecoar no REJECT: str curta ou int JS-seguro; senão None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and len(value) <= 64:
        return value
    if isinstance(value, int) and abs(value) <= MAX_MISSION_ID:
        return value
    return None


async def handler(websocket):
    """Gerencia uma conexão WebSocket do Nexus frontend."""
    remote = websocket.remote_address
    log.info(f"🟢 Conexão aberta: {remote}")

    # ── SEC-WS: Validar sessão no handshake (INV-N01, PD-OVR-004) ──
    request = getattr(websocket, "request", None)
    if request is not None:
        cookie_header = request.headers.get("Cookie", "")
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            cookie = SimpleCookie()
        token = cookie.get("brain_session")
        token_value = token.value if token else None

        if not token_value and "?" in getattr(request, "path", ""):
            from urllib.parse import parse_qs, urlsplit
            qs = parse_qs(urlsplit(request.path).query)
            token_value = (qs.get("brain_session") or qs.get("session") or [None])[0]

        store = get_store()
        if not token_value or not store.authorize(token_value, "session"):
            await websocket.close(4001, "AUTH_REQUIRED")
            return

    CONNECTIONS.add(websocket)
    orchestrator = Orchestrator()
    mission_task = None
    revision = 0
    prepared_task = None

    try:
        async for raw in websocket:
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                log.warning(f"Mensagem inválida de {remote}: {raw[:100]}")
                continue

            # Extrair ação do envelope do adapter
            action = message.get("action", message)
            action_type = action.get("type", "")
            log.info(f"📩 Comando: {action_type} (mission={message.get('missionId', '?')})")

            if action_type == "NEW_TASK":
                raw_mission_id = message.get("missionId")
                has_mission_dict = "mission" in message and isinstance(message["mission"], dict)

                # ── Early missionId validation (legacy envelope only) ──
                # When a structured mission dict is present, mission.id is the
                # canonical ID and is validated by validate_mission_envelope().
                # When absent, missionId IS the mission id — reject if invalid.
                if not has_mission_dict and raw_mission_id is not None and not is_valid_mission_id(raw_mission_id):
                    echo_id = _echoable_mission_id(raw_mission_id)
                    revision += 1
                    await websocket.send(json.dumps({
                        "type": "REJECT",
                        "commandId": message.get("commandId", ""),
                        "missionId": echo_id,
                        "revision": revision,
                        "reason": "mission.id must be a positive integer (JS-safe)",
                    }))
                    continue

                if has_mission_dict:
                    envelope = message
                    task_text = message["mission"].get("task", "")
                    target_mission_id = message["mission"].get("id")
                else:
                    target_mission_id = raw_mission_id if raw_mission_id is not None else 1
                    task_text = action.get("payload", "")
                    envelope = {"mission": {"id": target_mission_id, "task": task_text}}

                error = validate_mission_envelope(envelope)
                if error:
                    echo_id = _echoable_mission_id(raw_mission_id)
                    revision += 1
                    await websocket.send(json.dumps({
                        "type": "REJECT",
                        "commandId": message.get("commandId", ""),
                        "missionId": echo_id,
                        "revision": revision,
                        "reason": error,
                    }))
                    continue

                prepared_task = task_text

                # Cancelar missão anterior se existir
                if mission_task and not mission_task.done():
                    mission_task.cancel()
                    try:
                        await mission_task
                    except asyncio.CancelledError:
                        pass

                # ACK do comando
                revision += 1
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": raw_mission_id if raw_mission_id is not None else target_mission_id,
                    "revision": revision,
                }))

                # ── Strangler Fig: route to graph or legacy engine ──
                orchestrator = Orchestrator()
                if MISSION_ENGINE == "graph":
                    mission_task = asyncio.create_task(
                        _run_graph_mission(websocket, task_text, target_mission_id)
                    )
                else:
                    mission_task = asyncio.create_task(
                        _run_mission(websocket, orchestrator, task_text, target_mission_id)
                    )

            elif action_type == "APPROVE":
                # ── Strangler Fig: route approval to graph or legacy ──
                approve_mid = message.get("missionId")
                if MISSION_ENGINE == "graph":
                    evt = _graph_approval_events.get(approve_mid)
                    if evt is None:
                        echo_id = _echoable_mission_id(approve_mid)
                        revision += 1
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": echo_id,
                            "revision": revision,
                            "reason": "no_mission_waiting_for_approval",
                        }))
                        continue
                    evt.set()
                    revision += 1
                    await websocket.send(json.dumps({
                        "type": "ACK",
                        "commandId": message.get("commandId", ""),
                        "missionId": approve_mid,
                        "revision": revision,
                    }))
                else:
                    if not orchestrator.awaiting_approval:
                        echo_id = _echoable_mission_id(approve_mid)
                        revision += 1
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": echo_id,
                            "revision": revision,
                            "reason": "no_mission_waiting_for_approval",
                        }))
                        continue

                    mission_id = approve_mid if approve_mid is not None else orchestrator.mission_id
                    orchestrator.approve()
                    revision += 1
                    await websocket.send(json.dumps({
                        "type": "ACK",
                        "commandId": message.get("commandId", ""),
                        "missionId": mission_id,
                        "revision": revision,
                    }))

            elif action_type == "START":
                if "mission" in message:
                    error = validate_mission_envelope(message)
                    if error:
                        echo_id = _echoable_mission_id(message.get("missionId"))
                        revision += 1
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": echo_id,
                            "revision": revision,
                            "reason": error,
                        }))
                        continue
                    mission_obj = message.get("mission", {})
                    start_mission_id = mission_obj.get("id")
                    start_task = mission_obj.get("task")
                else:
                    if not prepared_task:
                        echo_id = _echoable_mission_id(message.get("missionId"))
                        revision += 1
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": echo_id,
                            "revision": revision,
                            "reason": "envelope.mission must be an object",
                        }))
                        continue
                    start_mission_id = message.get("missionId", 0) + 2
                    start_task = prepared_task
                    prepared_task = None

                mission_id = message.get("missionId", 0)
                if start_mission_id is not None:
                    if mission_task and not mission_task.done():
                        mission_task.cancel()
                        try:
                            await mission_task
                        except asyncio.CancelledError:
                            pass
                    orchestrator = Orchestrator()
                    # ── Strangler Fig: route to graph or legacy engine ──
                    if MISSION_ENGINE == "graph":
                        mission_task = asyncio.create_task(
                            _run_graph_mission(websocket, start_task, start_mission_id)
                        )
                    else:
                        mission_task = asyncio.create_task(
                            _run_mission(websocket, orchestrator, start_task, start_mission_id)
                        )

                revision += 1
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": mission_id,
                    "revision": revision,
                }))

            elif action_type in ("PAUSE", "RESUME", "RESET"):
                mission_id = message.get("missionId", 0)
                revision += 1
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": mission_id,
                    "revision": revision,
                }))

            elif action_type == "HITL_DECISION":
                # Sprint 7: Governança — decisão HITL do operador humano
                # NEW-02: Autenticação — validar request_id contra pending store
                try:
                    from core.governance.hitl_protocol import HITLResponse, HITLDecision
                    from core.integration import _get_hitl_store
                    hitl_payload = action.get("payload", {})
                    if not isinstance(hitl_payload, dict) or not hitl_payload.get("request_id"):
                        log.warning(f"HITL_DECISION rejeitado: payload inválido de {remote}")
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": message.get("missionId", 0),
                            "reason": "invalid_hitl_payload",
                        }))
                        continue

                    # Validar decision é um enum válido antes de processar
                    raw_decision = hitl_payload.get("decision", "")
                    if raw_decision not in {d.value for d in HITLDecision}:
                        log.warning(f"HITL_DECISION rejeitado: decision inválida '{raw_decision}' de {remote}")
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": message.get("missionId", 0),
                            "reason": "invalid_hitl_decision",
                        }))
                        continue

                    response = HITLResponse.from_frame(hitl_payload)
                    store = _get_hitl_store()

                    # NEW-02: Verificar que request_id existe no pending store
                    if not store.is_pending(response.request_id):
                        log.warning(f"HITL_DECISION rejeitado: request_id '{response.request_id}' "
                                    f"não encontrado no pending store de {remote}")
                        await websocket.send(json.dumps({
                            "type": "REJECT",
                            "commandId": message.get("commandId", ""),
                            "missionId": message.get("missionId", 0),
                            "reason": "unknown_hitl_request",
                        }))
                        continue

                    store.resolve(response)
                    log.info(f"🔐 HITL decision: {response.decision.value} for {response.request_id}")
                    await websocket.send(json.dumps({
                        "type": "ACK",
                        "commandId": message.get("commandId", ""),
                        "missionId": message.get("missionId", 0),
                        "revision": orchestrator.sequence + 1,
                    }))
                except ImportError:
                    log.warning("HITL modules not available")
                except Exception as exc:
                    log.error(f"HITL decision error: {exc}")

    except websockets.exceptions.ConnectionClosed:
        log.info(f"🔴 Conexão fechada: {remote}")
    except Exception as exc:
        log.error(f"❌ Erro com {remote}: {exc}")
    finally:
        CONNECTIONS.discard(websocket)
        if mission_task and not mission_task.done():
            mission_task.cancel()


async def _run_mission(websocket, orchestrator, task_text, mission_id=None):
    """Executa uma missão e envia eventos ao frontend."""
    log.info(f"🚀 Missão iniciada (missionId={mission_id}): '{task_text[:80]}'")
    try:
        async for event in orchestrator.run_mission(task_text, mission_id=mission_id):
            payload = json.dumps(event)
            try:
                await websocket.send(payload)
                log.info(f"  📤 [{event['agentId']}] {event['type']} → {event.get('payload', {}).get('bubble', '')[:40]}")
            except websockets.exceptions.ConnectionClosed:
                log.warning("Conexão fechada durante missão")
                return
        log.info(f"✅ Missão {mission_id} concluída")
    except asyncio.CancelledError:
        log.info("🔶 Missão cancelada (nova missão recebida)")
    except Exception as exc:
        log.error(f"❌ Erro na missão: {exc}")
        try:
            await websocket.send(json.dumps({
                "schemaVersion": 1,
                "id": f"error:{id(exc)}",
                "missionId": orchestrator.mission_id,
                "sequence": orchestrator._next_seq(),
                "agentId": "manager",
                "type": "message",
                "timestamp": __import__("time").time() * 1000,
                "payload": {"message": f"Erro: {exc}", "bubble": "❌ Erro interno"},
            }))
        except Exception:
            pass


async def _run_graph_mission(websocket, task_text, mission_id):
    """Execute a mission via the Node Loop Graph with HITL support.

    Uses the lower-level graph APIs directly (instead of ``run_mission_graph``)
    to support the HITL resume loop: when the graph suspends for approval,
    waits for the APPROVE handler to signal ``_graph_approval_events[mission_id]``,
    then resumes from the suspended node.

    This is the Strangler Fig replacement for ``_run_mission()``.
    """
    log.info(f"🚀 Graph missão iniciada (missionId={mission_id}): '{task_text[:80]}'")
    try:
        from core.graph.edges import build_graph  # noqa: WPS433
        from core.graph.nexus_adapter import NexusEventAdapter  # noqa: WPS433
        from core.graph.telemetry import instrumented_run_graph  # noqa: WPS433
        from core.state import create_initial_state  # noqa: WPS433

        async def send_event(event):
            try:
                await websocket.send(json.dumps(event))
                log.info(
                    "  📤 [%s] %s → %s",
                    event.get("agentId", "?"),
                    event.get("type", "?"),
                    event.get("payload", {}).get("bubble", "")[:40],
                )
            except websockets.exceptions.ConnectionClosed:
                log.warning("Conexão fechada durante missão (graph)")

        adapter = NexusEventAdapter(mission_id, send_event)

        # Build graph and initial state
        graph = build_graph()
        state = create_initial_state()
        state = {
            **state,
            "metadata": {
                **state["metadata"],
                "task_text": task_text,
                "mission_id": mission_id,
            },
        }

        # Initial run
        result = await instrumented_run_graph(
            graph, state, on_event=adapter.on_event,
        )

        # ── HITL resume loop ──────────────────────────────────────
        while result.get("status") == "awaiting_approval":
            approval_event = asyncio.Event()
            _graph_approval_events[mission_id] = approval_event
            log.info("⏸️ Graph missão %s aguardando aprovação", mission_id)
            try:
                await asyncio.wait_for(approval_event.wait(), timeout=300)
            except asyncio.TimeoutError:
                log.warning("Graph missão %s: timeout de aprovação (300s)", mission_id)
                await adapter.on_event({
                    "type": "graph_end",
                    "trace_id": result.get("trace_id", ""),
                    "iteration": 0,
                    "status": "failed",
                    "reason": "approval_timeout",
                })
                return
            finally:
                _graph_approval_events.pop(mission_id, None)

            resume_from = result.get("metadata", {}).get("_suspended_at")
            if not resume_from:
                log.error(
                    "Graph missão %s: _suspended_at not found in state", mission_id,
                )
                return

            log.info("▶️ Graph missão %s retomada de '%s'", mission_id, resume_from)
            result = await instrumented_run_graph(
                graph, result,
                on_event=adapter.on_event,
                resume_from=resume_from,
            )

        log.info(
            "✅ Graph missão %s concluída: status=%s",
            mission_id,
            result.get("status", "?"),
        )

    except asyncio.CancelledError:
        log.info("🔶 Graph missão cancelada (nova missão recebida)")
    except Exception as exc:
        log.error(f"❌ Erro na graph missão: {exc}")
        try:
            import time as _time

            await websocket.send(json.dumps({
                "schemaVersion": 1,
                "id": f"error:{id(exc)}",
                "missionId": mission_id,
                "sequence": 0,
                "agentId": "manager",
                "type": "message",
                "timestamp": _time.time() * 1000,
                "payload": {"message": f"Erro: {exc}", "bubble": "❌ Erro interno"},
            }))
        except Exception:
            pass
    finally:
        _graph_approval_events.pop(mission_id, None)

async def serve(port=None, origins=None, store=None):
    """Factory para criar servidor WS. Usada em testes com port=0 para port aleatório."""
    if store is not None:
        set_store(store)
    _port = port if port is not None else PORT
    _origins = origins if origins is not None else ALLOWED_ORIGINS
    server = await websockets.serve(handler, HOST, _port, origins=_origins)
    return server


async def main():
    log.info(f"🟢 Nexus WebSocket Server iniciando em ws://{HOST}:{PORT}")
    log.info(f"   Ferramentas: search_knowledge_base, get_adr, list_rules, get_brain_status, get_system_architecture")

    stop = asyncio.Event()

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    async with websockets.serve(handler, HOST, PORT, origins=ALLOWED_ORIGINS):
        log.info(f"✅ WebSocket Server rodando em ws://{HOST}:{PORT}")
        log.info(f"   Aguardando conexões do Nexus frontend...")
        try:
            await stop.wait()
        except KeyboardInterrupt:
            pass

    log.info("🔴 WebSocket Server encerrado")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🔴 Encerrado")

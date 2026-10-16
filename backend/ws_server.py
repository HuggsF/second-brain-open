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
from core.domain.workflow.entities import MAX_MISSION_ID, validate_mission_envelope

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
                if "mission" in message and isinstance(message["mission"], dict):
                    envelope = message
                    task_text = message["mission"].get("task", "")
                    target_mission_id = message["mission"].get("id")
                else:
                    base_m_id = message.get("missionId", 0)
                    target_mission_id = (base_m_id + 1) if (isinstance(base_m_id, int) and base_m_id >= 0) else 1
                    task_text = action.get("payload", "")
                    envelope = {"mission": {"id": target_mission_id, "task": task_text}}

                error = validate_mission_envelope(envelope)
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
                    "missionId": message.get("missionId", 0),
                    "revision": revision,
                }))

            elif action_type == "APPROVE":
                if not orchestrator.awaiting_approval:
                    echo_id = _echoable_mission_id(message.get("missionId"))
                    revision += 1
                    await websocket.send(json.dumps({
                        "type": "REJECT",
                        "commandId": message.get("commandId", ""),
                        "missionId": echo_id,
                        "revision": revision,
                        "reason": "no_mission_waiting_for_approval",
                    }))
                    continue

                mission_id = message.get("missionId", orchestrator.mission_id)
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

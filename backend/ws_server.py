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

from backend.orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nexus-ws")

HOST = "127.0.0.1"
PORT = 8848
CONNECTIONS = set()


async def handler(websocket):
    """Gerencia uma conexão WebSocket do Nexus frontend."""
    remote = websocket.remote_address
    log.info(f"🟢 Conexão aberta: {remote}")
    CONNECTIONS.add(websocket)
    orchestrator = Orchestrator()
    mission_task = None

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
                # Cancelar missão anterior se existir
                if mission_task and not mission_task.done():
                    mission_task.cancel()
                    try:
                        await mission_task
                    except asyncio.CancelledError:
                        pass

                mission_id = message.get("missionId", 1)
                task_text = action.get("payload", "")
                if not task_text or not isinstance(task_text, str):
                    await websocket.send(json.dumps({
                        "type": "REJECT",
                        "commandId": message.get("commandId", ""),
                        "missionId": mission_id,
                        "revision": 1,
                        "reason": "Empty task",
                    }))
                    continue

                # ACK do comando
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": mission_id,
                    "revision": 1,
                }))

                # Iniciar missão em background com missionId alinhado ao frontend
                orchestrator = Orchestrator()
                mission_task = asyncio.create_task(
                    _run_mission(websocket, orchestrator, task_text, mission_id)
                )

            elif action_type == "APPROVE":
                mission_id = message.get("missionId", orchestrator.mission_id)
                orchestrator.approve()
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": mission_id,
                    "revision": orchestrator.sequence + 1,
                }))

            elif action_type == "START":
                mission_id = message.get("missionId", 1)
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": mission_id,
                    "revision": 1,
                }))

            elif action_type in ("PAUSE", "RESUME", "RESET"):
                mission_id = message.get("missionId", 0)
                await websocket.send(json.dumps({
                    "type": "ACK",
                    "commandId": message.get("commandId", ""),
                    "missionId": mission_id,
                    "revision": 1,
                }))

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

    async with websockets.serve(handler, HOST, PORT):
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

import asyncio
import pytest
import websockets
from backend import ws_server


def test_evil_origin_rejected():
    async def run():
        srv = await ws_server.serve(0)
        port = srv.sockets[0].getsockname()[1]
        try:
            with pytest.raises(websockets.exceptions.InvalidHandshake):
                async with websockets.connect(
                    f"ws://127.0.0.1:{port}",
                    origin="https://evil.example",
                ):
                    pass
        finally:
            srv.close()
            await srv.wait_closed()

    asyncio.run(run())


def test_allowed_origin_accepted():
    async def run():
        srv = await ws_server.serve(0)
        port = srv.sockets[0].getsockname()[1]
        try:
            async with websockets.connect(
                f"ws://127.0.0.1:{port}",
                origin="http://127.0.0.1:5173",
            ) as ws:
                # Connection established successfully (no exception = pass)
                assert ws is not None
        finally:
            srv.close()
            await srv.wait_closed()

    asyncio.run(run())

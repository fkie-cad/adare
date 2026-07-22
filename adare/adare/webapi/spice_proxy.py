"""Same-origin WebSocket proxy to VirtualSpice's decoded-frame stream.

The ADARE-owned SPICE viewer connects to ``/ws/vm/{vm_id}`` on ADARE's own
origin; this proxy dials VirtualSpice's ``/ws/vm/{vm_id}/frames`` on localhost
and pumps binary frames both directions. Keeping the browser same-origin fixes
cross-origin and HTTPS mixed-content problems — the browser never contacts
``:8081`` directly.
"""

import asyncio
import logging

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import WebSocketException

logger = logging.getLogger(__name__)

VIRTUALSPICE_PORT = 8081

router = APIRouter()


async def _client_to_upstream(client: WebSocket, upstream) -> None:
    """Pump binary frames from the browser client to VirtualSpice."""
    while True:
        data = await client.receive_bytes()
        await upstream.send(data)


async def _upstream_to_client(client: WebSocket, upstream) -> None:
    """Pump binary frames from VirtualSpice to the browser client."""
    async for message in upstream:
        if isinstance(message, bytes):
            await client.send_bytes(message)
        else:
            # Text frames are not part of the binary display protocol; forward
            # as bytes so the client codec sees a consistent stream.
            await client.send_bytes(message.encode("utf-8"))


@router.websocket("/ws/vm/{vm_id}")
async def spice_proxy(websocket: WebSocket, vm_id: str) -> None:
    """Proxy a viewer WebSocket to VirtualSpice's decoded-frame stream."""
    await websocket.accept()

    upstream_url = f"ws://127.0.0.1:{VIRTUALSPICE_PORT}/ws/vm/{vm_id}/frames"
    try:
        upstream = await websockets.connect(upstream_url, max_size=None)
    except (WebSocketException, ConnectionError, OSError) as e:
        logger.warning("SPICE proxy could not reach VirtualSpice at %s: %s", upstream_url, e)
        await websocket.close(code=1011, reason="VirtualSpice unavailable")
        return

    try:
        # Run both pumps until either side closes; first to finish cancels the rest.
        tasks = [
            asyncio.create_task(_client_to_upstream(websocket, upstream)),
            asyncio.create_task(_upstream_to_client(websocket, upstream)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except (WebSocketException, WebSocketDisconnect, ConnectionError, OSError) as e:
        logger.debug("SPICE proxy for vm %s ended: %s", vm_id, e)
    finally:
        await upstream.close()
        try:
            await websocket.close()
        except (WebSocketException, WebSocketDisconnect, RuntimeError):
            # Client socket may already be closed.
            pass

"""Reverse proxy for VirtualSpice VM endpoints."""
import asyncio
import logging

import httpx
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

VIRTUALSPICE_URL = "http://127.0.0.1:8081"

router = APIRouter(tags=["vm-proxy"])


@router.api_route(
    "/api/vm/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_vm_api(request: Request, path: str):
    """Forward REST requests to VirtualSpice."""
    async with httpx.AsyncClient(base_url=VIRTUALSPICE_URL, timeout=30.0) as client:
        url = f"/api/{path}"

        # Forward query params
        if request.url.query:
            url = f"{url}?{request.url.query}"

        body = await request.body()

        # Strip hop-by-hop headers
        forwarded_headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "transfer-encoding", "connection")
        }

        resp = await client.request(
            method=request.method,
            url=url,
            content=body if body else None,
            headers=forwarded_headers,
        )

        # Filter out hop-by-hop response headers
        response_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in ("transfer-encoding", "connection", "content-encoding")
        }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
        )


@router.websocket("/ws/vm/{path:path}")
async def proxy_vm_ws(ws: WebSocket, path: str):
    """Forward WebSocket connections to VirtualSpice."""
    await ws.accept()

    vs_url = f"ws://127.0.0.1:8081/ws/{path}"

    try:
        import websockets

        async with websockets.connect(vs_url) as vs_ws:

            async def client_to_server():
                try:
                    while True:
                        data = await ws.receive_bytes()
                        await vs_ws.send(data)
                except WebSocketDisconnect:
                    await vs_ws.close()

            async def server_to_client():
                try:
                    async for msg in vs_ws:
                        if isinstance(msg, bytes):
                            await ws.send_bytes(msg)
                        else:
                            await ws.send_text(msg)
                except websockets.exceptions.ConnectionClosed:
                    pass

            await asyncio.gather(client_to_server(), server_to_client())
    except ImportError:
        logger.error("websockets package not installed; WebSocket proxy unavailable")
        await ws.close(code=1011, reason="websockets package not installed")
    except ConnectionRefusedError:
        logger.warning("VirtualSpice not reachable at %s", vs_url)
        await ws.close(code=1011, reason="VirtualSpice unavailable")
    except websockets.exceptions.InvalidURI:
        logger.error("Invalid VirtualSpice URI: %s", vs_url)
        await ws.close(code=1011, reason="Invalid upstream URI")


@router.websocket("/ws/vm-events")
async def proxy_vm_events(ws: WebSocket):
    """Forward VM events WebSocket to VirtualSpice /ws/events."""
    await ws.accept()

    try:
        import websockets

        async with websockets.connect("ws://127.0.0.1:8081/ws/events") as vs_ws:

            async def client_to_server():
                try:
                    while True:
                        data = await ws.receive_text()
                        await vs_ws.send(data)
                except WebSocketDisconnect:
                    await vs_ws.close()

            async def server_to_client():
                try:
                    async for msg in vs_ws:
                        if isinstance(msg, str):
                            await ws.send_text(msg)
                        else:
                            await ws.send_bytes(msg)
                except websockets.exceptions.ConnectionClosed:
                    pass

            await asyncio.gather(client_to_server(), server_to_client())
    except ImportError:
        logger.error("websockets package not installed; WebSocket proxy unavailable")
        await ws.close(code=1011, reason="websockets package not installed")
    except ConnectionRefusedError:
        logger.warning("VirtualSpice not reachable for events WebSocket")
        await ws.close(code=1011, reason="VirtualSpice unavailable")

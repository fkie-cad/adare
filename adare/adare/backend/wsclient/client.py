import asyncio
import logging
from contextlib import contextmanager
import websockets

log = logging.getLogger(__name__)

@contextmanager
def suppress_websockets_logs(level):
    ws_logger = logging.getLogger("websockets")
    original_level = ws_logger.level
    ws_logger.setLevel(level)
    try:
        yield
    finally:
        ws_logger.setLevel(original_level)


class WebSocketClient:
    def __init__(self, uri, identifier):
        self.uri = uri
        self.identifier = identifier
        self.websocket = None

    async def connect(self):
        """Establish a connection and immediately send the identifier."""
        self.websocket = await websockets.connect(self.uri)
        await self.websocket.send(self.identifier)
        log.debug(f"Connected and sent identifier: {self.identifier}")

    async def send_message(self, message):
        """Send a message to the server."""
        if self.websocket is None:
            raise Exception("Not connected. Call connect() first.")
        await self.websocket.send(message)
        log.debug(f"Sent: {message}")

    async def fetch_message(self):
        """Receive a message from the server."""
        if self.websocket is None:
            raise Exception("Not connected. Call connect() first.")
        message = await self.websocket.recv()
        log.debug(f"Received: {message}")
        return message

    async def is_server_ready(self, timeout=5):
        """
        Check if the server is ready by sending a ping and waiting for a pong.
        Returns True if a pong is received within the timeout, otherwise False.
        """
        if self.websocket is None:
            raise Exception("Not connected. Call connect() first.")
        try:
            pong_waiter = await self.websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout)
            log.info("Server is ready (pong received).")
            return True
        except asyncio.TimeoutError:
            log.error("Server is not ready (ping timeout).")
            return False

    async def wait_until_server_ready(self, ping_timeout=5, retry_interval=2, max_retries=10):
        """
        Repeatedly attempt to connect and check if the server is ready.
        If the connection is lost or not yet established, it will reconnect.
        Returns True if the server is ready within max_retries attempts; otherwise, False.
        """
        attempt = 0
        while attempt < max_retries:
            try:
                if self.websocket is None or self.websocket.closed:
                    await self.connect()
                if await self.is_server_ready(timeout=ping_timeout):
                    return True
            except Exception as e:
                log.error(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            attempt += 1
            await asyncio.sleep(retry_interval)
        log.error("Server did not become ready after maximum retries.")
        return False

    async def close(self):
        """Close the WebSocket connection."""
        if self.websocket:
            await self.websocket.close()
            log.info("Connection closed.")
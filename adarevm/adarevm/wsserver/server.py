import asyncio
import websockets
import threading
import logging

log = logging.getLogger(__name__)
ws_server = None

class WebSocketServer:
    def __init__(self, host="localhost", port=18765):
        self.host = host
        self.port = port
        self.clients = {}  # maps client identifier to websocket
        self.send_queues = {}
        self.loop = None
        self.server_thread = None
        self.msg_handler = None

    def set_msg_handler(self, msg_handler):
        """Sets a message handler for incoming messages."""
        self.msg_handler = msg_handler

    async def sender(self, identifier, websocket):
        """Continuously sends messages from the client's send queue to the websocket."""
        if identifier not in self.send_queues:
            self.send_queues[identifier] = asyncio.Queue()
        while True:
            msg = await self.send_queues[identifier].get()
            try:
                await websocket.send(msg.encode())
                log.info(f"Sent to {identifier}: {msg}")
            except websockets.exceptions.ConnectionClosed:
                log.warning(f"Connection closed while sending to {identifier}.")
                break
            except Exception as e:
                log.error(f"Error sending to {identifier}: {e}")
                break

    async def handler(self, websocket):
        """Handles new WebSocket connections."""
        identifier = None
        send_task = None
        try:
            # Expect the first message to be the client identifier.
            identifier = await websocket.recv()
            self.clients[identifier] = websocket
            log.info(f"Client connected: {identifier}")

            # Start the sender task to drain the send queue.
            send_task = asyncio.create_task(self.sender(identifier, websocket))

            # Non-async callback function:
            def send_callback(msg):
                if identifier not in self.send_queues:
                    self.send_queues[identifier] = asyncio.Queue()
                # Schedule the coroutine in the running loop.
                asyncio.run_coroutine_threadsafe(
                    self.send_queues[identifier].put(msg), self.loop
                )

            # Process incoming messages.
            async for message in websocket:
                await self.process_message(identifier, message, send_callback)

        except websockets.exceptions.ConnectionClosed as e:
            # e.code == 1000 is a normal close.
            if identifier is None:
                log.info("Connection closed before client identifier was received.")
            elif e.rcvd.code == 1000:
                log.info(f"Client {identifier} closed connection normally.")
            else:
                log.error(f"Connection closed for client {identifier} with code: {e.code}")
        except Exception as e:
            log.error(f"Error handling client {identifier}: {e}")
        finally:
            if send_task:
                send_task.cancel()
            if identifier in self.clients:
                del self.clients[identifier]
                log.info(f"Client {identifier} removed from active connections.")

    async def process_message(self, identifier, message, send_callback):
        log.info(f"Received from {identifier}: {message}")
        if self.msg_handler:
            loop = asyncio.get_running_loop()
            # Offload the message handler to a separate thread.
            await loop.run_in_executor(
                None, self.msg_handler.handle_message, identifier, message, send_callback
            )
        else:
            log.warning("No message handler defined. Message ignored.")

    async def send_message(self, identifier, message):
        """Sends a message to a specific client."""
        websocket = self.clients.get(identifier)
        if websocket:
            try:
                await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                log.warning(f"Failed to send to {identifier}: connection closed.")
            except Exception as e:
                log.error(f"Failed to send to {identifier}: {e}")

    async def _start_server(self):
        """Starts the server and returns the server object."""
        self.loop = asyncio.get_running_loop()
        server = await websockets.serve(self.handler, self.host, self.port)
        log.info(f"WebSocket server started on ws://{self.host}:{self.port}")
        return server

    def start(self):
        """Starts the WebSocket server in the current thread’s event loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start_server())
        self.loop.run_forever()

def get_ws_server(*args, **kwargs):
    global ws_server
    if not ws_server:
        ws_server = WebSocketServer(*args, **kwargs)
    return ws_server

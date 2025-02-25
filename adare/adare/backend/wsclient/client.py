import asyncio
import threading
import queue
import time
from contextlib import contextmanager

import websockets
import logging

log = logging.getLogger(__name__)


@contextmanager
def suppress_websockets_logs(level):
    logger = logging.getLogger("websockets")
    previous_level = logger.level
    logger.setLevel(level)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


class WebSocketClient:
    def __init__(self, uri, identifier):
        self.uri = uri
        self.host, self.port = uri.split("://")[1].split(":")
        self.port = int(self.port)
        self.identifier = identifier
        self.external_input_queue = queue.Queue()
        self.received_messages = queue.Queue()
        self.loop = asyncio.new_event_loop()
        self.client_thread = threading.Thread(target=self.run_client, daemon=True)
        self.stop_event = threading.Event()

    def is_ready(self):
        """Check if URI is reachable"""
        try:
            with suppress_websockets_logs(logging.WARNING):
                asyncio.get_event_loop().run_until_complete(websockets.connect(self.uri))
            return True
        except (websockets.exceptions.InvalidURI, websockets.exceptions.InvalidHandshake, ConnectionRefusedError, asyncio.TimeoutError):
            return False

    def wait_until_ready(self, timeout=360):
        """Wait until the WebSocket server is running."""
        log.info("Waiting for WebSocket server to start...")
        for _ in range(timeout):
            if self.is_ready():
                log.info("WebSocket server is ready.")
                return
            time.sleep(1)
        log.error("WebSocket server did not start in time.")


    def start(self):
        """Starts the WebSocket client in a background thread."""
        if not self.client_thread.is_alive():
            self.client_thread.start()
            log.info("WebSocket client started.")

    def send_message(self, message):
        """Sends a message to the WebSocket server."""
        self.external_input_queue.put(message)
        log.debug(f"Queued message for sending: {message}")

    def fetch_messages(self):
        """Retrieves all stored messages and clears the queue."""
        messages = []
        while not self.received_messages.empty():
            messages.append(self.received_messages.get())
        #log.debug(f"Fetched messages: {messages}")
        return messages

    def run_client(self):
        """Runs the WebSocket client event loop."""
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.client())
        except Exception as e:
            log.error(f"WebSocket client encountered an error: {e}")
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            log.info("Event loop shut down.")


    async def client(self):
        """Main WebSocket client function."""
        self.tasks = []
        while not self.stop_event.is_set():
            try:
                async with websockets.connect(self.uri) as websocket:
                    # Send client identifier
                    await websocket.send(self.identifier)
                    log.info(f"Connected as {self.identifier}")

                    # Create and track tasks
                    listen_task = asyncio.create_task(self.listen(websocket))
                    process_task = asyncio.create_task(self.process_external_messages(websocket))
                    self.tasks = [listen_task, process_task]

                    # Wait for tasks to complete or be stopped
                    await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)

            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                log.warning(f"Connection lost, retrying in 5 seconds: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                log.error(f"Unexpected error: {e}")
                break
            finally:
                # Ensure tasks and WebSocket close properly
                await self.cleanup()

    async def cleanup(self):
        log.info("Cleaning up tasks and connections.")
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def stop(self):
        log.info("Stopping WebSocket client.")
        # Signal the client to stop
        self.stop_event.set()

        # Wait for the client thread to finish
        if self.client_thread.is_alive():
            self.client_thread.join(timeout=10)
            if self.client_thread.is_alive():
                log.warning("Client thread did not exit in time.")
        else:
            log.warning("Client thread was not started, skipping join.")

        # Cancel any pending tasks in the event loop
        pending = asyncio.all_tasks(loop=self.loop)
        for task in pending:
            task.cancel()

        # Wait for all tasks to complete their cancellation
        try:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception as e:
            log.error(f"Error while cancelling pending tasks: {e}")

        # Shutdown async generators and close the loop
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.close()
        log.info("WebSocket client stopped.")

    async def listen(self, websocket):
        """Asynchronously listens for messages from the server and stores them."""
        try:
            while not self.stop_event.is_set():
                message = await websocket.recv()
                self.received_messages.put(message)
                log.debug(f"Received message: {message}")
        except websockets.exceptions.ConnectionClosed:
            log.warning("Connection closed by server.")
        except Exception as e:
            log.error(f"Error while listening: {e}")

    async def process_external_messages(self, websocket):
        """Handles messages sent from the main program."""
        while not self.stop_event.is_set():
            try:
                message = self.external_input_queue.get_nowait()
                await websocket.send(message)
                log.debug(f"Sent message: {message}")
            except queue.Empty:
                await asyncio.sleep(0.1)
            except Exception as e:
                log.error(f"Error while sending message: {e}")
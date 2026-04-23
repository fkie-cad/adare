"""
WebSocket client for communicating with adarevm.

This client handles communication from the host (adare) to the VM (adarevm)
using WebSocket protocol for real-time GUI automation and test execution.
"""

import asyncio
import base64
import contextlib
import io
import json
import logging
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import websockets

from adarelib.websocket.protocol import (
    EventMessage,
    ToolRegistry,
    ToolResultMessage,
    create_tool_call,
    parse_message,
)

log = logging.getLogger(__name__)


class WebSocketTimeoutError(Exception):
    """Raised when a WebSocket operation times out."""
    pass


class AdareVMClient:
    """
    WebSocket client for communicating with adarevm server.

    This client provides an interface for sending commands to the VM
    and receiving real-time events and results.
    """

    def __init__(self, host: str = 'localhost', port: int = 18765):
        self.server_url = f'ws://{host}:{port}'
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.connected = False

        # Pending tool calls (waiting for results)
        self.pending_calls: dict[str, asyncio.Future] = {}

        # Event handlers
        self.event_handlers: dict[str, list[Callable]] = {}

        # Background task for handling messages
        self.message_handler_task: asyncio.Task | None = None

        # Connection lock (event-loop-aware, recreated in current loop)
        self._connection_lock = None

    async def connect(self, timeout: float = 10.0) -> bool:
        """
        Connect to the adarevm WebSocket server.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        await self._ensure_connection_lock()
        async with self._connection_lock:
            if self.connected:
                return True

            try:
                log.info(f"Connecting to adarevm server at {self.server_url}")

                self.websocket = await asyncio.wait_for(
                    websockets.connect(
                        self.server_url,
                        max_size=None,
                        ping_interval=None,    # Disable automatic WebSocket pings
                        ping_timeout=None      # Disable ping timeouts
                    ),
                    timeout=timeout
                )

                self.connected = True

                # Start message handler task
                self.message_handler_task = asyncio.create_task(self._handle_messages())

                log.info("Successfully connected to adarevm server")
                return True

            except TimeoutError:
                log.error(f"Connection timeout after {timeout} seconds")
                return False
            except (websockets.exceptions.WebSocketException, ConnectionError, OSError) as e:
                log.error(f"Failed to connect to adarevm server: {e}")
                return False

    async def _ensure_connection_lock(self):
        """
        Ensure connection lock exists in current event loop.

        This is critical for dev mode where commands run in separate asyncio.run() calls.
        When asyncio.run() exits, the event loop and all its primitives are cleaned up.
        We need to recreate the lock in the current event loop.
        """
        if self._connection_lock is None:
            self._connection_lock = asyncio.Lock()
            return

        try:
            # Always recreate the lock to ensure it's from the current event loop
            # This is safer than trying to detect if it's from a different loop
            self._connection_lock = asyncio.Lock()
        except RuntimeError:
            self._connection_lock = asyncio.Lock()

    async def disconnect(self):
        """Disconnect from the adarevm server."""
        await self._ensure_connection_lock()
        async with self._connection_lock:
            if not self.connected:
                return

            try:
                # Cancel message handler task (handle cross-loop scenario)
                if self.message_handler_task:
                    try:
                        current_loop = asyncio.get_running_loop()
                        task_loop = self.message_handler_task.get_loop()
                        if current_loop == task_loop:
                            # Same loop - safe to cancel
                            self.message_handler_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await self.message_handler_task
                        else:
                            # Different loop - task is already dead, just clear reference
                            log.debug("Message handler task is from different event loop (already destroyed)")
                    except RuntimeError:
                        # No running loop or task has no loop, just clear
                        log.debug("Could not determine task loop, clearing reference")
                    finally:
                        self.message_handler_task = None

                # Close WebSocket connection
                if self.websocket:
                    await self.websocket.close()

                self.connected = False
                self.websocket = None

                log.info("Disconnected from adarevm server")

            except (OSError, ConnectionError, RuntimeError, websockets.exceptions.WebSocketException) as e:
                log.error(f"Unexpected error during disconnect: {e}", exc_info=True)

    async def reconnect(self, retries: int = 3, base_delay: float = 2.0) -> bool:
        """
        Attempt to reconnect to the WebSocket server with exponential backoff.

        This method is used for dev mode session restoration to reconnect to
        an already-running VM's WebSocket server.

        Args:
            retries: Maximum number of reconnection attempts
            base_delay: Base delay in seconds between attempts (exponential backoff)

        Returns:
            True if reconnected successfully, False otherwise
        """
        log.info(f"Attempting to reconnect to WebSocket server (max {retries} attempts)")

        for attempt in range(retries):
            try:
                # Calculate delay with exponential backoff (2^attempt * base_delay)
                if attempt > 0:
                    delay = (2 ** attempt) * base_delay
                    log.debug(f"Waiting {delay:.1f}s before reconnection attempt {attempt + 1}")
                    await asyncio.sleep(delay)

                log.info(f"Reconnection attempt {attempt + 1}/{retries}")

                # Try to connect
                success = await self.connect(timeout=5.0)

                if success:
                    log.info(f"Successfully reconnected on attempt {attempt + 1}")
                    return True
                log.warning(f"Reconnection attempt {attempt + 1} failed")

            except (OSError, ConnectionError, TimeoutError, websockets.exceptions.WebSocketException) as e:
                log.error(f"Reconnection attempt {attempt + 1} failed with error: {e}")

        log.error(f"Failed to reconnect after {retries} attempts")
        return False

    async def _handle_messages(self):
        """Handle incoming messages from the server."""
        try:
            async for message in self.websocket:
                await self._process_message(message)
        except websockets.exceptions.ConnectionClosed:
            log.info("WebSocket connection closed")
            self.connected = False
        except (websockets.exceptions.WebSocketException, ConnectionError, OSError) as e:
            log.error(f"WebSocket error handling messages: {e}")
            self.connected = False

    async def _process_message(self, message_str: str):
        """Process a single incoming message."""
        try:
            message = parse_message(message_str)

            if isinstance(message, ToolResultMessage):
                await self._handle_tool_result(message)
            elif isinstance(message, EventMessage):
                await self._handle_event(message)
            else:
                log.debug(f"Received unknown message type: {message.type}")

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            log.error(f"Message parsing error: {e}")

    async def _handle_tool_result(self, message: ToolResultMessage):
        """Handle a tool result message."""
        call_id = message.id

        if call_id in self.pending_calls:
            future = self.pending_calls.pop(call_id)
            if not future.cancelled():
                future.set_result(message)
        else:
            log.warning(f"Received result for unknown call ID: {call_id}")

    async def _handle_event(self, message: EventMessage):
        """Handle an event message."""
        event_type = message.event_type

        # Call registered event handlers
        handlers = self.event_handlers.get(event_type, [])
        handlers.extend(self.event_handlers.get('*', []))  # Wildcard handlers

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_type, message.data)
                else:
                    handler(event_type, message.data)
            except Exception as e:  # noqa: BLE001 -- must not let user-registered event handlers crash the message loop
                log.error(f"Error in event handler: {e}", exc_info=True)

    def add_event_handler(self, event_type: str, handler: Callable):
        """
        Add an event handler for a specific event type.

        Args:
            event_type: Event type to handle (or '*' for all events)
            handler: Function to call when event occurs
        """
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def remove_event_handler(self, event_type: str, handler: Callable):
        """Remove an event handler."""
        if event_type in self.event_handlers:
            with contextlib.suppress(ValueError):
                self.event_handlers[event_type].remove(handler)

    async def _ensure_message_handler_running(self):
        """
        Ensure the message handler task is running in the current event loop.

        This is critical for dev mode where commands run in separate asyncio.run() calls.
        When asyncio.run() exits, the event loop and all its tasks are cleaned up.
        If we reconnected in a previous command, the message_handler_task is dead.
        We need to restart it in the current event loop before making WebSocket calls.
        """
        if not self.connected or not self.websocket:
            return

        # Check if message handler task exists and is still running
        if self.message_handler_task and not self.message_handler_task.done():
            # Task exists and is running - check if it's in the current event loop
            try:
                current_loop = asyncio.get_running_loop()
                task_loop = self.message_handler_task.get_loop()
                if current_loop == task_loop:
                    # Task is running in current loop, all good
                    return
                # Task is from a different event loop (previous asyncio.run())
                log.debug("Message handler task is from a different event loop, restarting")
            except RuntimeError:
                # No running loop, which is odd but handle it
                log.debug("No running event loop detected")

        # Message handler is not running in current loop - restart it
        log.info("Restarting message handler task in current event loop")
        self.message_handler_task = asyncio.create_task(self._handle_messages())

    async def call_tool(self, tool_name: str, params: dict[str, Any] = None, timeout: float = 30.0) -> dict[str, Any]:
        """
        Call a tool on the adarevm server.

        Args:
            tool_name: Name of the tool to call
            params: Parameters for the tool
            timeout: Timeout in seconds

        Returns:
            Tool result data

        Raises:
            WebSocketTimeoutError: If the call times out
            RuntimeError: If not connected or call fails
        """
        if not self.connected:
            raise RuntimeError("Not connected to adarevm server")

        # Ensure message handler is running in current event loop
        await self._ensure_message_handler_running()

        # Create tool call message
        call_msg = create_tool_call(tool_name, params or {})

        # Enhanced logging for command tracking
        import time
        start_time = time.time()
        log.info(f"[{call_msg.id[:8]}] Sending tool call: {tool_name}")
        if tool_name == "execute_shell" and params and "shell_command" in params:
            log.info(f"[{call_msg.id[:8]}] Shell command: {params['shell_command']}")
        log.debug(f"[{call_msg.id[:8]}] Tool params: {params}")
        log.debug(f"[{call_msg.id[:8]}] Timeout: {timeout}s")

        # Create future for the result
        result_future = asyncio.Future()
        self.pending_calls[call_msg.id] = result_future

        try:
            # Send the message
            await self.websocket.send(call_msg.to_json())
            log.debug(f"[{call_msg.id[:8]}] Message sent, waiting for response...")

            # Wait for result
            result_msg = await asyncio.wait_for(result_future, timeout=timeout)

            execution_time = time.time() - start_time
            log.info(f"[{call_msg.id[:8]}] Tool call completed in {execution_time:.2f}s")

            if result_msg.success:
                return result_msg.result
            log.error(f"[{call_msg.id[:8]}] Tool call failed: {result_msg.error}")
            raise RuntimeError(f"Tool call failed: {result_msg.error}")

        except TimeoutError:
            execution_time = time.time() - start_time
            log.error(f"[{call_msg.id[:8]}] Tool call '{tool_name}' timed out after {timeout}s (actual: {execution_time:.2f}s)")
            # Clean up pending call
            self.pending_calls.pop(call_msg.id, None)
            raise WebSocketTimeoutError(f"Tool call '{tool_name}' timed out after {timeout} seconds") from None
        except (OSError, ConnectionError, RuntimeError, websockets.exceptions.WebSocketException) as e:
            execution_time = time.time() - start_time
            log.error(f"[{call_msg.id[:8]}] Tool call error after {execution_time:.2f}s: {e}")
            # Clean up pending call
            self.pending_calls.pop(call_msg.id, None)
            raise

    # GUI Action Methods

    async def screenshot(self, x: int = None, y: int = None, width: int = None, height: int = None) -> dict[str, Any]:
        """Take a screenshot."""
        params = {}
        if x is not None and y is not None and width is not None and height is not None:
            params = {"x": x, "y": y, "width": width, "height": height}
        return await self.call_tool(ToolRegistry.SCREENSHOT, params)

    async def click(self, x: int, y: int) -> dict[str, Any]:
        """Simulate a mouse click."""
        return await self.call_tool(ToolRegistry.CLICK, {"x": x, "y": y})

    async def right_click(self, x: int, y: int) -> dict[str, Any]:
        """Simulate a right mouse click."""
        return await self.call_tool(ToolRegistry.RIGHT_CLICK, {"x": x, "y": y})

    async def double_click(self, x: int, y: int) -> dict[str, Any]:
        """Simulate a double mouse click."""
        return await self.call_tool(ToolRegistry.DOUBLE_CLICK, {"x": x, "y": y})

    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
        """Simulate a mouse drag."""
        return await self.call_tool(ToolRegistry.DRAG, {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def keyboard(self, type: str, key: str) -> dict[str, Any]:
        """Simulate keyboard actions."""
        return await self.call_tool(ToolRegistry.KEYBOARD, {"type": type, "key": key})

    async def scroll(self, direction: str, amount: int) -> dict[str, Any]:
        """Simulate scroll action."""
        return await self.call_tool(ToolRegistry.SCROLL, {"direction": direction, "amount": amount})

    async def goto(self, x: int, y: int) -> dict[str, Any]:
        """Move mouse to coordinates."""
        return await self.call_tool(ToolRegistry.GOTO, {"x": x, "y": y})

    async def idle(self, duration: float) -> dict[str, Any]:
        """Simulate idle time."""
        return await self.call_tool(ToolRegistry.IDLE, {"duration": duration})

    async def screenshot_window(self, window: str) -> dict[str, Any]:
        """Take screenshot of specific window."""
        return await self.call_tool(ToolRegistry.SCREENSHOT_WINDOW, {"window": window})

    # Test Management Methods

    async def upload_testfunctions(self, testfunctions_path: Path, specific_files: set[Path] = None) -> dict[str, Any]:
        """
        Upload testfunctions to the VM.

        Args:
            testfunctions_path: Path to directory containing testfunctions
            specific_files: Optional set of specific file paths to upload. If None, uploads all files.

        Returns:
            Upload result
        """
        # Create zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if specific_files:
                # Upload only specific files
                for file_path in specific_files:
                    if file_path.is_file():
                        # Calculate relative path from testfunctions directory
                        try:
                            arcname = file_path.relative_to(testfunctions_path)
                            zip_file.write(file_path, arcname)
                        except ValueError:
                            # File is not relative to testfunctions_path, skip it
                            log.warning(f"Skipping file outside testfunctions directory: {file_path}")
            else:
                # Upload all files (original behavior)
                for file_path in testfunctions_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(testfunctions_path)
                        zip_file.write(file_path, arcname)

        # Encode as base64
        zip_data = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')

        return await self.call_tool(ToolRegistry.UPLOAD_TESTFUNCTIONS, {
            "testfunctions_data": zip_data
        }, timeout=300.0)  # Increased timeout for dependency installation (5 minutes)

    async def install_testfunction_dependencies(self, dependencies: list[str]) -> dict[str, Any]:
        """
        Install testfunction dependencies in the VM.

        Args:
            dependencies: List of dependency strings (e.g., ["requests>=2.0.0", "numpy"])

        Returns:
            Installation result
        """
        return await self.call_tool(ToolRegistry.INSTALL_DEPENDENCIES, {
            "dependencies": dependencies
        }, timeout=300.0)  # 5 minutes for dependency installation

    async def set_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Set variables for test execution."""
        return await self.call_tool(ToolRegistry.SET_VARIABLES, {
            "variables": json.dumps(variables)
        })

    async def run_test(self, test_name: str, resolved_test_data: dict[str, Any], timeout: float = 130.0) -> dict[str, Any]:
        """Run a test with pre-resolved test data (variables already substituted).

        Args:
            test_name: Name of the test to run
            resolved_test_data: Test data with variables already substituted
            timeout: WebSocket timeout in seconds (default 130s = 120s test + 10s buffer)

        Returns:
            Test result dictionary
        """
        params = {
            "test_name": test_name,
            "resolved_test_data": resolved_test_data
        }
        return await self.call_tool(ToolRegistry.RUN_TEST, params, timeout=timeout)


    async def execute_shell(self, shell_command: str, cwd: str = None, env: dict = None, timeout: float = None, shell: bool = False, inherit_env: bool = True, admin: bool = False, websocket_timeout: float = None) -> dict[str, Any]:
        """Execute a raw shell command with advanced options."""
        params = {"shell_command": shell_command}
        if cwd is not None:
            params["cwd"] = cwd
        if env is not None:
            params["env"] = env
        if timeout is not None:
            params["timeout"] = timeout
        if shell is not None:
            params["shell"] = shell
        if inherit_env is not None:
            params["inherit_env"] = inherit_env
        if admin is not None:
            params["admin"] = admin

        # Use command timeout + buffer for WebSocket timeout, or default to 30s
        call_timeout = websocket_timeout or (timeout + 10 if timeout else 30.0)
        return await self.call_tool(ToolRegistry.EXECUTE_SHELL, params, timeout=call_timeout)

    async def get_status(self) -> dict[str, Any]:
        """Get current server status."""
        return await self.call_tool(ToolRegistry.GET_STATUS)

    async def collect_system_info(self, timeout: float = 120.0) -> dict[str, Any]:
        """
        Collect comprehensive system information from the guest VM.

        Returns structured data including OS info, installed packages, etc.
        Uses a longer timeout as this operation can take time on systems with many packages.

        Args:
            timeout: Timeout in seconds (default 120s for systems with many packages)

        Returns:
            Dict containing system information or error details
        """
        return await self.call_tool(ToolRegistry.COLLECT_SYSTEM_INFO, timeout=timeout)

    async def get_filesystem_snapshot(self, root_path: str = '/', timeout: float = 660.0) -> dict[str, Any]:
        """
        Get filesystem snapshot from the VM.

        Captures file metadata using platform-specific approaches:
        - Windows: MFT reader for NTFS timestamps
        - Linux: find command for file metadata

        Args:
            root_path: Root directory to scan (default: '/')
            timeout: WebSocket timeout in seconds (default: 660s = 11 min)

        Returns:
            Dict with snapshot data:
            {
                "status": "success",
                "snapshot": {"/path/to/file": {"size": 1024, "mtime": 1234567890.0, ...}},
                "file_count": 12345,
                "collection_time": 45.23
            }
        """
        return await self.call_tool(ToolRegistry.GET_FILESYSTEM_SNAPSHOT, {
            "root_path": root_path,
            "timeout": timeout - 60  # Subtract buffer for tool timeout
        }, timeout=timeout)

    async def get_timestamp(self, use_local: bool = False, timeout: float = 10.0) -> dict[str, Any]:
        """
        Get timezone-aware timestamp from the VM.

        Retrieves the current timestamp from the VM instead of using the host's clock.
        This ensures timestamps are synchronized with the VM's system time for accurate
        forensic artifact analysis.

        Args:
            use_local: If True, detect and return VM's local timezone.
                      If False (default), return UTC timestamp only.
            timeout: Timeout in seconds (default: 10.0)

        Returns:
            Dict with timestamp data:
            {
                "timestamp": 1234567890.123456,  # Unix timestamp in UTC (float with microseconds)
                "timezone": "UTC" or "+04:00",    # Timezone string
                "iso_format": "2026-01-17T14:30:45.123456+00:00",  # ISO 8601 format
                "local_time": "2026-01-17T18:30:45.123456+04:00"   # Only present if use_local=True
            }

        Examples:
            Basic UTC timestamp:
            >>> result = await client.get_timestamp()
            >>> timestamp = result["timestamp"]  # 1234567890.123456
            >>> timezone = result["timezone"]    # "UTC"

            Local timezone timestamp:
            >>> result = await client.get_timestamp(use_local=True)
            >>> timestamp = result["timestamp"]      # 1234567890.123456 (still UTC-based)
            >>> timezone = result["timezone"]        # "+04:00"
            >>> local_time = result["local_time"]    # "2026-01-17T18:30:45.123456+04:00"

            Store in variable with metadata:
            >>> from adarelib.common.variables import Variable, VariableType
            >>> result = await client.get_timestamp(use_local=True)
            >>> timestamp_var = Variable(
            ...     value=result["timestamp"],
            ...     type=VariableType.TIMESTAMP,
            ...     metadata={"timezone": result["timezone"]}
            ... )

        Raises:
            WebSocketTimeoutError: If the call times out
            RuntimeError: If not connected or call fails
        """
        return await self.call_tool(ToolRegistry.GET_TIMESTAMP, {
            "use_local": use_local
        }, timeout=timeout)

    async def pull_file_chunked(self, guest_path: str, host_path: Path,
                               chunk_size: int = 1048576,
                               progress_callback = None) -> dict[str, Any]:
        """
        Pull a file from guest to host using chunked transfer.

        Args:
            guest_path: Path to file on guest
            host_path: Destination path on host
            chunk_size: Bytes per chunk (default 1MB)
            progress_callback: Optional callback(chunk_idx, total_chunks, bytes_transferred, total_bytes)

        Returns:
            Dict with status, file_size, chunks_transferred, metadata

        Raises:
            RuntimeError: If transfer fails
        """
        import base64

        log.info(f"Starting chunked pull: {guest_path} -> {host_path}")

        # Create temp file for writing chunks
        temp_path = host_path.with_suffix(host_path.suffix + '.tmp')
        temp_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Get first chunk to determine total chunks
            first_result = await self.call_tool(
                ToolRegistry.PULL_FILE_CHUNK,
                {
                    "guest_path": guest_path,
                    "chunk_index": 0,
                    "chunk_size": chunk_size
                },
                timeout=60.0
            )

            if first_result.get("status") == "error":
                raise RuntimeError(f"Failed to pull {guest_path}: {first_result.get('error')}")

            total_chunks = first_result["total_chunks"]
            file_size = first_result["file_size"]
            metadata = first_result.get("file_metadata", {})

            log.info(f"File size: {file_size} bytes, chunks: {total_chunks}")

            # Write first chunk
            with open(temp_path, 'wb') as f:
                chunk_data = base64.b64decode(first_result["chunk_data"])
                f.write(chunk_data)

            if progress_callback:
                progress_callback(0, total_chunks, len(chunk_data), file_size)

            # Pull remaining chunks
            bytes_transferred = len(chunk_data)
            for chunk_idx in range(1, total_chunks):
                chunk_result = await self.call_tool(
                    ToolRegistry.PULL_FILE_CHUNK,
                    {
                        "guest_path": guest_path,
                        "chunk_index": chunk_idx,
                        "chunk_size": chunk_size
                    },
                    timeout=60.0
                )

                if chunk_result.get("status") == "error":
                    raise RuntimeError(
                        f"Failed to pull chunk {chunk_idx}/{total_chunks}: "
                        f"{chunk_result.get('error')}"
                    )

                # Append chunk to temp file
                with open(temp_path, 'ab') as f:
                    chunk_data = base64.b64decode(chunk_result["chunk_data"])
                    f.write(chunk_data)
                    bytes_transferred += len(chunk_data)

                if progress_callback:
                    progress_callback(chunk_idx, total_chunks, bytes_transferred, file_size)

            # Verify file size
            actual_size = temp_path.stat().st_size
            if actual_size != file_size:
                raise RuntimeError(
                    f"File size mismatch: expected {file_size}, got {actual_size}"
                )

            # Move temp file to final location
            if host_path.exists():
                host_path.unlink()
            temp_path.rename(host_path)

            log.info(f"Successfully pulled {guest_path} ({file_size} bytes, {total_chunks} chunks)")

            return {
                "status": "success",
                "file_size": file_size,
                "chunks_transferred": total_chunks,
                "metadata": metadata,
                "destination": str(host_path)
            }

        except (OSError, ConnectionError, RuntimeError, TimeoutError, WebSocketTimeoutError) as e:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            log.error(f"Chunked pull failed for {guest_path}: {e}")
            raise

    async def pull_multiple_files_chunked(self, guest_paths: list[str], host_dest_dir: Path,
                                         chunk_size: int = 1048576,
                                         progress_callback = None) -> dict[str, Any]:
        """
        Pull multiple files from guest to host using chunked transfer.

        Args:
            guest_paths: List of paths to files on guest
            host_dest_dir: Destination directory on host
            chunk_size: Bytes per chunk (default 1MB)
            progress_callback: Optional callback(current_file_idx, total_files,
                              file_path, chunk_idx, total_chunks, bytes_transferred, total_bytes)

        Returns:
            Dict with:
                - success_count: Number of successfully transferred files
                - failed_count: Number of failed transfers
                - total_bytes: Total bytes transferred
                - failures: List of {path, error} dicts for failed files
                - file_results: List of individual file results

        Raises:
            RuntimeError: If all transfers fail
        """
        log.info(f"Starting batch chunked pull: {len(guest_paths)} files -> {host_dest_dir}")

        total_files = len(guest_paths)
        success_count = 0
        failed_count = 0
        total_bytes_transferred = 0
        failures = []
        file_results = []

        for file_idx, guest_path in enumerate(guest_paths, start=1):
            try:
                log.info(f"Pulling file {file_idx}/{total_files}: {guest_path}")

                # Preserve directory structure
                # Extract relative path from guest_path
                if ':' in guest_path:  # Windows path
                    guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
                    relative_path = guest_path_cleaned.replace('\\', '/')
                else:  # Unix path
                    relative_path = guest_path.lstrip('/')

                # Construct host destination path
                host_path = host_dest_dir / relative_path

                # Create per-file progress callback that wraps the overall progress callback
                def file_progress_callback(chunk_idx, total_chunks, bytes_xfer, file_size):
                    if progress_callback:
                        progress_callback(
                            file_idx, total_files, guest_path,
                            chunk_idx, total_chunks, bytes_xfer, file_size
                        )

                # Pull the file using existing single-file method
                result = await self.pull_file_chunked(
                    guest_path=guest_path,
                    host_path=host_path,
                    chunk_size=chunk_size,
                    progress_callback=file_progress_callback
                )

                # Track success
                success_count += 1
                total_bytes_transferred += result['file_size']
                file_results.append({
                    'path': guest_path,
                    'success': True,
                    'destination': str(host_path),
                    'file_size': result['file_size'],
                    'chunks': result['chunks_transferred']
                })

                log.info(f"Successfully pulled {guest_path} ({result['file_size']} bytes)")

            except (OSError, ConnectionError, RuntimeError, TimeoutError, WebSocketTimeoutError) as e:
                # Log and track failure, but continue with remaining files
                failed_count += 1
                error_msg = str(e)
                log.error(f"Failed to pull {guest_path}: {error_msg}")

                failures.append({
                    'path': guest_path,
                    'error': error_msg
                })

                file_results.append({
                    'path': guest_path,
                    'success': False,
                    'error': error_msg
                })

        # Prepare summary
        summary = {
            'success_count': success_count,
            'failed_count': failed_count,
            'total_files': total_files,
            'total_bytes': total_bytes_transferred,
            'failures': failures,
            'file_results': file_results
        }

        log.info(
            f"Batch pull complete: {success_count}/{total_files} succeeded, "
            f"{failed_count} failed, {total_bytes_transferred} bytes transferred"
        )

        # Raise exception if ALL files failed
        if failed_count == total_files:
            raise RuntimeError(
                f"All {total_files} file transfers failed. "
                f"First error: {failures[0]['error'] if failures else 'Unknown'}"
            )

        return summary

    # Convenience Methods

    async def ping(self) -> bool:
        """Check connectivity by testing if websocket is still connected."""
        return self.connected and self.websocket is not None

    async def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for connection to be established."""
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)
        return self.connected

    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self.connected

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

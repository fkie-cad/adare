"""
WebSocket server for adarevm.

This server handles communication between the host (adare) and VM (adarevm)
using a custom WebSocket protocol for real-time GUI automation and test execution.
"""

import asyncio
import websockets
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import platform

import logging
log = logging.getLogger(__name__)

# Import our WebSocket protocol
from adarelib.websocket.protocol import (
    parse_message, create_tool_result, create_event, create_status,
    MessageType, EventType, ToolRegistry,
    ToolResultMessage, EventMessage
)

# Import tool mixins
from adarevm.core.tools.gui_tools import GUIToolsMixin
from adarevm.core.tools.test_tools import TestToolsMixin
from adarevm.core.tools.system_tools import SystemToolsMixin
from adarevm.core.tools.file_tools import FileToolsMixin


class AdareVMServer(GUIToolsMixin, TestToolsMixin, SystemToolsMixin, FileToolsMixin):
    """WebSocket server for adarevm GUI automation and test execution."""

    def _split_command_line(self, command: str) -> List[str]:
        """Split a command string into arguments using platform-native parsing."""
        if platform.system().lower() == "windows":
            return self._split_windows_command_line(command)

        import shlex
        try:
            return shlex.split(command)
        except ValueError:
            # Fallback for unbalanced quotes
            return command.split(" ")

    def _split_windows_command_line(self, command: str) -> List[str]:
        """Split a Windows command string using pure Python shlex."""
        import shlex
        try:
            # Use shlex with custom configuration for Windows-like parsing:
            # 1. posix=True: Enables quote stripping (removing " from "foo bar")
            # 2. escape='': Disables backslash escaping so C:\Path shouldn't become C:Path
            # 3. whitespace_split=True: Splits by whitespace
            lexer = shlex.shlex(command, posix=True)
            lexer.whitespace_split = True
            lexer.escape = ''

            # Additional safety: handle comment chars if any default (typically #)
            lexer.commenters = ''

            return list(lexer)
        except Exception as e:
            log.error(f"Error parsing Windows command line with shlex: {e}")
            # Fallback
            return command.split(" ")

    def __init__(self, host="0.0.0.0", port=18765, tools_paths: List[str] = None, data_paths: List[str] = None, installation_mode: str = "wheel"):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()

        # Shared data paths (project and experiment data directories)
        self.data_paths = data_paths or []
        if self.data_paths:
            log.info(f"AdareVMServer initialized with data_paths: {self.data_paths}")
        self.tools_paths = tools_paths or []
        if self.tools_paths:
            log.info(f"AdareVMServer initialized with tools_paths: {self.tools_paths}")

        # Installation mode configuration
        self.installation_mode = installation_mode
        log.info(f"Installation mode: {installation_mode}")

        # Test management state
        self.testfunctions_dir: Optional[Path] = None
        self.current_variables: Dict[str, Any] = {}
        self._testfunction_cache: Optional[dict] = None  # Cache discovered testfunctions

        # Task management for non-blocking tool execution
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.client_tasks: Dict[websockets.WebSocketServerProtocol, Set[str]] = {}

        # Tool registry
        self.tools = {
            "screenshot": self._screenshot,
            "click": self._click,
            "right_click": self._right_click,
            "double_click": self._double_click,
            "drag": self._drag,
            "keyboard": self._keyboard,
            "scroll": self._scroll,
            "goto": self._goto,
            "idle": self._idle,
            "screenshot_window": self._screenshot_window,
            "upload_testfunctions": self._upload_testfunctions,
            "install_dependencies": self._install_dependencies,
            "set_variables": self._set_variables,
            "run_test": self._run_test,
            "execute_shell": self._execute_shell,
            "get_status": self._get_status,
            "collect_system_info": self._collect_system_info,
            "set_screenshot_method": self._set_screenshot_method,
            "pull_file_chunk": self._pull_file_chunk,
            "get_filesystem_snapshot": self._get_filesystem_snapshot,
            "get_timestamp": self._get_timestamp,
            "chain_commands": self._chain_commands,
        }

    async def start_server(self):
        """Start the WebSocket server."""
        log.info(f"Starting AdareVM WebSocket server on {self.host}:{self.port}")

        # Check if we should skip PyAutoGUI (host-based GUI mode)
        import os
        gui_mode = os.environ.get('ADARE_GUI_MODE', 'agent')
        skip_pyautogui = (gui_mode == 'host')

        if skip_pyautogui:
            log.info(
                "Host-based GUI automation detected (ADARE_GUI_MODE=host). "
                "Skipping PyAutoGUI initialization - GUI automation will be performed by host."
            )
        else:
            # Log screen size and initialize mouse position
            try:
                import pyautogui
                screen_width, screen_height = pyautogui.size()
                log.info(f"Screen size: {screen_width}x{screen_height}")

                # Initialize mouse to center to avoid fail-safe issues
                center_x = screen_width // 2
                center_y = screen_height // 2

                # Temporarily disable fail-safe for initialization
                original_failsafe = pyautogui.FAILSAFE
                pyautogui.FAILSAFE = False
                pyautogui.moveTo(center_x, center_y)
                pyautogui.FAILSAFE = original_failsafe
                log.info(f"Initialized mouse position to center: ({center_x}, {center_y})")
            except Exception as e:
                # Catch ALL exceptions (ImportError, X11 errors, etc.)
                log.warning(
                    f"pyautogui initialization failed ({type(e).__name__}: {e}). "
                    "GUI automation via agent mode will not be available. "
                    "This is normal when using host-based GUI automation."
                )

        server = await websockets.serve(self.handle_client, self.host, self.port)
        log.info(f"Server started successfully")
        return server

    async def handle_client(self, websocket):
        """Handle a new client connection."""
        self.clients.add(websocket)
        self.client_tasks[websocket] = set()
        client_address = websocket.remote_address
        log.info(f"Client connected: {client_address}")

        try:
            # Send welcome message
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Connected to AdareVM server",
                "server_info": {
                    "host": self.host,
                    "port": self.port,
                    "available_tools": list(self.tools.keys())
                }
            })

            async for message in websocket:
                await self.handle_message(websocket, message)

        except websockets.exceptions.ConnectionClosed:
            log.info(f"Client disconnected: {client_address}")
        except Exception as e:
            log.error(f"Unexpected error handling client {client_address}: {e}", exc_info=True)
        finally:
            await self._cleanup_client_tasks(websocket)
            self.clients.discard(websocket)
            self.client_tasks.pop(websocket, None)

    async def handle_message(self, websocket, message_str: str):
        """Handle incoming message from client."""
        try:
            message = json.loads(message_str)
            msg_type = message.get('type')

            if msg_type == MessageType.TOOL_CALL:
                await self.handle_tool_call(websocket, message)
            else:
                log.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON received: {e}")
            await self.send_error(websocket, f"Invalid JSON: {e}")
        except KeyError as e:
            log.error(f"Missing required field in message: {e}")
            await self.send_error(websocket, f"Missing field: {e}")
        except Exception as e:
            log.error(f"Unexpected error handling message: {e}", exc_info=True)
            await self.send_error(websocket, str(e))

    async def handle_tool_call(self, websocket, message: Dict[str, Any]):
        """
        Handle a tool call from the client.

        Tool execution runs in background tasks to avoid blocking the message loop,
        allowing the server to continue processing ping/pong and other messages
        during long-running operations like dependency installation.
        """
        call_id = message.get('id')
        tool_name = message.get('tool')
        params = message.get('params', {})

        log.info(f"Tool call: {tool_name} with params: {params}")

        try:
            if tool_name not in self.tools:
                raise ValueError(f"Unknown tool: {tool_name}")

            # Execute the tool in background task to avoid blocking message loop
            tool_func = self.tools[tool_name]
            task_id = f"{call_id}_{tool_name}"

            # Create background task for tool execution
            task = asyncio.create_task(tool_func(websocket, **params))
            self.running_tasks[task_id] = task

            # Track task for this client
            if websocket not in self.client_tasks:
                self.client_tasks[websocket] = set()
            self.client_tasks[websocket].add(task_id)

            # Create completion handler that will send result when task finishes
            asyncio.create_task(self._handle_task_completion(task_id, websocket, call_id))

            log.debug(f"[{call_id[:8]}] Started background task for {tool_name}")

        except ValueError as e:
            log.error(f"Invalid tool or parameters: {tool_name}: {e}")
            error_msg = ToolResultMessage(
                id=call_id,
                success=False,
                error=f"Invalid tool call: {e}"
            )
            await websocket.send(error_msg.to_json())
        except Exception as e:
            log.error(f"Tool execution failed: {tool_name}: {e}", exc_info=True)
            error_msg = ToolResultMessage(
                id=call_id,
                success=False,
                error=f"Tool execution error: {e}"
            )
            await websocket.send(error_msg.to_json())

    async def send_event(self, websocket, event_type: str, data: Dict[str, Any]):
        """Send an event message to the client."""
        event_msg = EventMessage(event_type=event_type, data=data)
        await websocket.send(event_msg.to_json())

    async def send_error(self, websocket, error: str):
        """Send an error event to the client."""
        await self.send_event(websocket, EventType.ERROR, {"error": error})


    async def _cleanup_client_tasks(self, websocket):
        """Cancel all running tasks for a disconnected client."""
        if websocket not in self.client_tasks:
            return

        task_ids = list(self.client_tasks[websocket])
        if task_ids:
            log.info(f"Cancelling {len(task_ids)} running tasks for disconnected client")

        for task_id in task_ids:
            if task_id in self.running_tasks:
                task = self.running_tasks[task_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        log.warning(f"Error cancelling task {task_id}: {e}")
                del self.running_tasks[task_id]

    async def _handle_task_completion(self, task_id: str, websocket, call_id: str):
        """Handle completion of a background tool execution task."""
        try:
            task = self.running_tasks.get(task_id)
            if not task:
                log.warning(f"Task {task_id} not found in running tasks")
                return

            try:
                result = await task
                # Send successful result back to client
                result_msg = ToolResultMessage(
                    id=call_id,
                    success=True,
                    result=result
                )
                if websocket in self.clients:  # Check if client still connected
                    await websocket.send(result_msg.to_json())
                    log.debug(f"[{call_id[:8]}] Background task completed successfully")

            except asyncio.CancelledError:
                log.debug(f"[{call_id[:8]}] Background task was cancelled")
                # Don't send error for cancelled tasks, client likely disconnected

            except Exception as e:
                log.error(f"[{call_id[:8]}] Background task failed: {e}", exc_info=True)
                # Send error result back to client
                error_msg = ToolResultMessage(
                    id=call_id,
                    success=False,
                    error=f"Tool execution error: {e}"
                )
                if websocket in self.clients:  # Check if client still connected
                    await websocket.send(error_msg.to_json())

        finally:
            # Clean up task tracking
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
            if websocket in self.client_tasks and task_id in self.client_tasks[websocket]:
                self.client_tasks[websocket].discard(task_id)

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        if self.clients:
            event_msg = EventMessage(event_type=event_type, data=data)
            message = event_msg.to_json()
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )

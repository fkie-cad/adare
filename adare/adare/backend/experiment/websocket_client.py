"""
WebSocket client for communicating with adarevm.

This client handles communication from the host (adare) to the VM (adarevm)
using WebSocket protocol for real-time GUI automation and test execution.
"""

import asyncio
import websockets
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
import base64
import zipfile
import io

from adarelib.websocket.protocol import (
    parse_message, create_tool_call, create_tool_result, create_event,
    MessageType, EventType, ToolRegistry, 
    ToolCallMessage, ToolResultMessage, EventMessage
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
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        
        # Pending tool calls (waiting for results)
        self.pending_calls: Dict[str, asyncio.Future] = {}
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Background task for handling messages
        self.message_handler_task: Optional[asyncio.Task] = None
        
        # Connection lock
        self._connection_lock = asyncio.Lock()
    
    async def connect(self, timeout: float = 10.0) -> bool:
        """
        Connect to the adarevm WebSocket server.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully
        """
        async with self._connection_lock:
            if self.connected:
                return True
            
            try:
                log.info(f"Connecting to adarevm server at {self.server_url}")
                
                self.websocket = await asyncio.wait_for(
                    websockets.connect(self.server_url, max_size=None),
                    timeout=timeout
                )
                
                self.connected = True
                
                # Start message handler task
                self.message_handler_task = asyncio.create_task(self._handle_messages())
                
                log.info("Successfully connected to adarevm server")
                return True
                
            except asyncio.TimeoutError:
                log.error(f"Connection timeout after {timeout} seconds")
                return False
            except Exception as e:
                log.error(f"Failed to connect to adarevm server: {e}")
                return False
    
    async def disconnect(self):
        """Disconnect from the adarevm server."""
        async with self._connection_lock:
            if not self.connected:
                return
            
            try:
                # Cancel message handler task
                if self.message_handler_task:
                    self.message_handler_task.cancel()
                    try:
                        await self.message_handler_task
                    except asyncio.CancelledError:
                        pass
                
                # Close WebSocket connection
                if self.websocket:
                    await self.websocket.close()
                
                self.connected = False
                self.websocket = None
                
                log.info("Disconnected from adarevm server")
                
            except Exception as e:
                log.error(f"Error during disconnect: {e}")
    
    async def _handle_messages(self):
        """Handle incoming messages from the server."""
        try:
            async for message in self.websocket:
                await self._process_message(message)
        except websockets.exceptions.ConnectionClosed:
            log.info("WebSocket connection closed")
            self.connected = False
        except Exception as e:
            log.error(f"Error handling messages: {e}")
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
                
        except Exception as e:
            log.error(f"Error processing message: {e}")
    
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
            except Exception as e:
                log.error(f"Error in event handler: {e}")
    
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
            try:
                self.event_handlers[event_type].remove(handler)
            except ValueError:
                pass
    
    async def call_tool(self, tool_name: str, params: Dict[str, Any] = None, timeout: float = 30.0) -> Dict[str, Any]:
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
        
        # Create tool call message
        call_msg = create_tool_call(tool_name, params or {})
        
        # Create future for the result
        result_future = asyncio.Future()
        self.pending_calls[call_msg.id] = result_future
        
        try:
            # Send the message
            await self.websocket.send(call_msg.to_json())
            
            # Wait for result
            result_msg = await asyncio.wait_for(result_future, timeout=timeout)
            
            if result_msg.success:
                return result_msg.result
            else:
                raise RuntimeError(f"Tool call failed: {result_msg.error}")
                
        except asyncio.TimeoutError:
            # Clean up pending call
            self.pending_calls.pop(call_msg.id, None)
            raise WebSocketTimeoutError(f"Tool call '{tool_name}' timed out after {timeout} seconds")
        except Exception as e:
            # Clean up pending call
            self.pending_calls.pop(call_msg.id, None)
            raise e
    
    # GUI Action Methods
    
    async def screenshot(self, x: int = None, y: int = None, width: int = None, height: int = None) -> Dict[str, Any]:
        """Take a screenshot."""
        params = {}
        if x is not None and y is not None and width is not None and height is not None:
            params = {"x": x, "y": y, "width": width, "height": height}
        return await self.call_tool(ToolRegistry.SCREENSHOT, params)
    
    async def click(self, x: int, y: int) -> Dict[str, Any]:
        """Simulate a mouse click."""
        return await self.call_tool(ToolRegistry.CLICK, {"x": x, "y": y})
    
    async def right_click(self, x: int, y: int) -> Dict[str, Any]:
        """Simulate a right mouse click."""
        return await self.call_tool(ToolRegistry.RIGHT_CLICK, {"x": x, "y": y})
    
    async def double_click(self, x: int, y: int) -> Dict[str, Any]:
        """Simulate a double mouse click.""" 
        return await self.call_tool(ToolRegistry.DOUBLE_CLICK, {"x": x, "y": y})
    
    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
        """Simulate a mouse drag."""
        return await self.call_tool(ToolRegistry.DRAG, {"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    
    async def keyboard(self, type: str, key: str) -> Dict[str, Any]:
        """Simulate keyboard actions."""
        return await self.call_tool(ToolRegistry.KEYBOARD, {"type": type, "key": key})
    
    async def scroll(self, direction: str, amount: int) -> Dict[str, Any]:
        """Simulate scroll action."""
        return await self.call_tool(ToolRegistry.SCROLL, {"direction": direction, "amount": amount})
    
    async def goto(self, x: int, y: int) -> Dict[str, Any]:
        """Move mouse to coordinates."""
        return await self.call_tool(ToolRegistry.GOTO, {"x": x, "y": y})
    
    async def idle(self, duration: float) -> Dict[str, Any]:
        """Simulate idle time."""
        return await self.call_tool(ToolRegistry.IDLE, {"duration": duration})
    
    async def screenshot_window(self, window: str) -> Dict[str, Any]:
        """Take screenshot of specific window."""
        return await self.call_tool(ToolRegistry.SCREENSHOT_WINDOW, {"window": window})
    
    # Test Management Methods
    
    async def upload_testfunctions(self, testfunctions_path: Path) -> Dict[str, Any]:
        """
        Upload testfunctions to the VM.
        
        Args:
            testfunctions_path: Path to directory containing testfunctions
            
        Returns:
            Upload result
        """
        # Create zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in testfunctions_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(testfunctions_path)
                    zip_file.write(file_path, arcname)
        
        # Encode as base64
        zip_data = base64.b64encode(zip_buffer.getvalue()).decode('utf-8')
        
        return await self.call_tool(ToolRegistry.UPLOAD_TESTFUNCTIONS, {
            "testfunctions_data": zip_data
        })
    
    async def upload_testset(self, testset_yaml: str) -> Dict[str, Any]:
        """Upload testset YAML configuration."""
        return await self.call_tool(ToolRegistry.UPLOAD_TESTSET, {
            "testset_yaml": testset_yaml
        })
    
    async def set_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Set variables for test execution."""
        return await self.call_tool(ToolRegistry.SET_VARIABLES, {
            "variables": json.dumps(variables)
        })
    
    async def run_test(self, test_name: str) -> Dict[str, Any]:
        """Run a specific test."""
        return await self.call_tool(ToolRegistry.RUN_TEST, {"test_name": test_name})
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all available tests."""
        return await self.call_tool(ToolRegistry.RUN_ALL_TESTS)
    
    async def list_tests(self) -> Dict[str, Any]:
        """List available tests."""
        return await self.call_tool(ToolRegistry.LIST_TESTS)
    
    async def execute_shell(self, shell_command: str, cwd: str = None, env: dict = None, timeout: float = None, shell: bool = False) -> Dict[str, Any]:
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
        return await self.call_tool(ToolRegistry.EXECUTE_SHELL, params)
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current server status."""
        return await self.call_tool(ToolRegistry.GET_STATUS)
    
    # Convenience Methods
    
    async def ping(self) -> bool:
        """Ping the server to check connectivity."""
        try:
            if not self.connected:
                return False
            
            ping_msg = {"type": MessageType.PING, "timestamp": time.time()}
            await self.websocket.send(json.dumps(ping_msg))
            return True
        except Exception:
            return False
    
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

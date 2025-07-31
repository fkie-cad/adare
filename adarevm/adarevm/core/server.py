"""
WebSocket server for adarevm.

This server handles communication between the host (adare) and VM (adarevm)
using a custom WebSocket protocol for real-time GUI automation and test execution.
"""

import asyncio
import websockets
import json
import logging
import tempfile
import shutil
import binascii
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import time

# Import automation modules
from adarevm.automation.gui import (
    take_screenshot, take_window_screenshots, click, right_click, double_click,
    drag, keyboard_action, scroll, move_mouse, idle
)
from adarevm.automation.shell import execute_on_shell
from adarevm.testing.testset import TestsetExecutionError

import logging
log = logging.getLogger(__name__)

# Import our WebSocket protocol
from adarelib.websocket.protocol import (
    parse_message, create_tool_result, create_event, create_status,
    MessageType, EventType, ToolRegistry,
    ToolResultMessage, EventMessage
)
import base64

class AdareVMServer:
    """WebSocket server for adarevm GUI automation and test execution."""
    
    def __init__(self, host="0.0.0.0", port=18765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        
        # Test management state
        self.testfunctions_dir: Optional[Path] = None
        self.testset_instance: Optional[Any] = None
        self.current_variables: Dict[str, Any] = {}
        
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
            "upload_testset": self._upload_testset,
            "set_variables": self._set_variables,
            "run_test": self._run_test,
            "run_all_tests": self._run_all_tests,
            "list_tests": self._list_tests,
            "execute_shell": self._execute_shell,
            "get_status": self._get_status,
        }
    
    async def start_server(self):
        """Start the WebSocket server."""
        log.info(f"Starting AdareVM WebSocket server on {self.host}:{self.port}")
        
        # Log screen size and initialize mouse position
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
        
        server = await websockets.serve(self.handle_client, self.host, self.port)
        log.info(f"Server started successfully")
        return server
    
    async def handle_client(self, websocket):
        """Handle a new client connection."""
        self.clients.add(websocket)
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
            log.error(f"Error handling client {client_address}: {e}")
        finally:
            self.clients.discard(websocket)
    
    async def handle_message(self, websocket, message_str: str):
        """Handle incoming message from client."""
        try:
            message = json.loads(message_str)
            msg_type = message.get('type')
            
            if msg_type == MessageType.TOOL_CALL:
                await self.handle_tool_call(websocket, message)
            elif msg_type == MessageType.PING:
                await self.send_pong(websocket)
            else:
                log.warning(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON received: {e}")
            await self.send_error(websocket, f"Invalid JSON: {e}")
        except KeyError as e:
            log.error(f"Missing required field in message: {e}")
            await self.send_error(websocket, f"Missing field: {e}")
        except Exception as e:
            log.error(f"Unexpected error handling message: {e}")
            await self.send_error(websocket, str(e))
    
    async def handle_tool_call(self, websocket, message: Dict[str, Any]):
        """Handle a tool call from the client."""
        call_id = message.get('id')
        tool_name = message.get('tool')
        params = message.get('params', {})
        
        log.info(f"Tool call: {tool_name} with params: {params}")
        
        try:
            if tool_name not in self.tools:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            # Execute the tool
            tool_func = self.tools[tool_name]
            result = await tool_func(websocket, **params)
            
            # Send result back
            result_msg = ToolResultMessage(
                id=call_id,
                success=True,
                result=result
            )
            await websocket.send(result_msg.to_json())
            
        except ValueError as e:
            log.error(f"Invalid tool or parameters: {tool_name}: {e}")
            error_msg = ToolResultMessage(
                id=call_id,
                success=False,
                error=f"Invalid tool call: {e}"
            )
            await websocket.send(error_msg.to_json())
        except Exception as e:
            log.error(f"Tool execution failed: {tool_name}: {e}")
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
    
    async def send_pong(self, websocket):
        """Send a pong response."""
        pong_msg = {"type": MessageType.PONG, "timestamp": time.time()}
        await websocket.send(json.dumps(pong_msg))
    
    async def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        """Broadcast an event to all connected clients."""
        if self.clients:
            event_msg = EventMessage(event_type=event_type, data=data)
            message = event_msg.to_json()
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )
    
    # GUI Action Tools
    
    async def _screenshot(self, websocket, x: int = None, y: int = None, width: int = None, height: int = None):
        """Take a screenshot."""
        await self.send_event(websocket, EventType.LOG, {"message": "Taking screenshot"})
        return take_screenshot(x, y, width, height)
    
    async def _click(self, websocket, x: int, y: int):
        """Simulate a mouse click."""
        await self.send_event(websocket, EventType.GUI_CLICK, {
            "action": "click", "x": x, "y": y
        })
        return click(x, y)
    
    async def _right_click(self, websocket, x: int, y: int):
        """Simulate a right mouse click."""
        await self.send_event(websocket, EventType.GUI_CLICK, {
            "action": "right_click", "x": x, "y": y
        })
        return right_click(x, y)
    
    async def _double_click(self, websocket, x: int, y: int):
        """Simulate a double mouse click."""
        await self.send_event(websocket, EventType.GUI_CLICK, {
            "action": "double_click", "x": x, "y": y
        })
        return double_click(x, y)
    
    async def _drag(self, websocket, x1: int, y1: int, x2: int, y2: int):
        """Simulate a mouse drag."""
        await self.send_event(websocket, EventType.GUI_DRAG, {
            "from": {"x": x1, "y": y1}, "to": {"x": x2, "y": y2}
        })
        return drag(x1, y1, x2, y2)
    
    async def _keyboard(self, websocket, type: str, key: str):
        """Simulate keyboard actions."""
        await self.send_event(websocket, EventType.GUI_KEYPRESS, {
            "type": type, "key": key
        })
        return keyboard_action(type, key)
    
    async def _scroll(self, websocket, direction: str, amount: int):
        """Simulate scroll action."""
        log.info(f"Scrolling {direction} by {amount}")
        result = scroll(direction, amount)
        await self.send_event(websocket, EventType.LOG, {"message": f"Scrolled {direction} by {amount}"})
        return result
    
    async def _goto(self, websocket, x: int, y: int):
        """Move mouse to coordinates."""
        log.info(f"Moving mouse to ({x}, {y})")
        result = move_mouse(x, y)
        await self.send_event(websocket, EventType.LOG, {"message": f"Mouse moved to ({x}, {y})"})
        return result
    
    async def _idle(self, websocket, duration: float):
        """Simulate idle time."""
        await self.send_event(websocket, EventType.GUI_IDLE, {"duration": duration})
        await asyncio.sleep(duration)
        return {"status": "success", "message": f"Idle for {duration} seconds"}
    
    async def _screenshot_window(self, websocket, window: str):
        """Take screenshot of specific window."""
        log.info(f"Taking screenshot of window: {window}")
        await self.send_event(websocket, EventType.LOG, {"message": f"Taking screenshot of window: {window}"})
        try:
            result = take_window_screenshots(window)
            await self.send_event(websocket, EventType.LOG, {"message": f"Window screenshot completed: {len(result) if isinstance(result, list) else 1} images"})
            return result
        except ImportError as e:
            log.error(f"Platform module not available: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Platform not supported: {e}"})
            return {"status": "error", "message": f"Platform not supported: {e}"}
        except OSError as e:
            log.error(f"Screenshot operation failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Screenshot failed: {e}"})
            return {"status": "error", "message": f"Screenshot failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected screenshot error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Window screenshot failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    # Test Management Tools
    
    async def _upload_testfunctions(self, websocket, testfunctions_data: str):
        """Upload testfunction files."""
        await self.send_event(websocket, EventType.LOG, {"message": "Uploading testfunctions"})
        
        try:
            # Decode base64 data
            zip_data = base64.b64decode(testfunctions_data)
            
            # Create temporary directory
            self.testfunctions_dir = Path(tempfile.mkdtemp(prefix="adare_testfunctions_"))
            
            # Write and extract zip
            zip_path = self.testfunctions_dir / "testfunctions.zip"
            with open(zip_path, 'wb') as f:
                f.write(zip_data)
            
            shutil.unpack_archive(zip_path, self.testfunctions_dir)
            zip_path.unlink()
            
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Testfunctions uploaded to {self.testfunctions_dir}"
            })
            
            return {
                "status": "success",
                "message": f"Testfunctions uploaded to {self.testfunctions_dir}",
                "path": str(self.testfunctions_dir)
            }
            
        except binascii.Error as e:
            log.error(f"Invalid base64 data: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Invalid base64 data: {e}"})
            return {"status": "error", "message": f"Invalid base64 data: {e}"}
        except (OSError, FileNotFoundError) as e:
            log.error(f"File operation failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"File operation failed: {e}"})
            return {"status": "error", "message": f"File operation failed: {e}"}
        except shutil.ReadError as e:
            log.error(f"Archive extraction failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Archive extraction failed: {e}"})
            return {"status": "error", "message": f"Archive extraction failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected upload error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Upload failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    async def _upload_testset(self, websocket, testset_yaml: str):
        """Upload testset YAML configuration."""
        await self.send_event(websocket, EventType.LOG, {"message": "Loading testset"})
        
        try:
            if not self.testfunctions_dir or not self.testfunctions_dir.exists():
                return {"status": "error", "message": "Testfunctions must be uploaded first"}
            
            # Write testset YAML
            testset_path = self.testfunctions_dir / "testset.yml"
            with open(testset_path, 'w') as f:
                f.write(testset_yaml)
            
            # Import and create testset
            from adarevm.testing.testset import Testset
            
            async def log_func(message: str):
                await self.broadcast_event(EventType.LOG, {"message": f"Testset: {message}"})
            
            self.testset_instance = Testset(self.testfunctions_dir, testset_path, log_func)
            
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Testset loaded with {len(self.testset_instance.tests)} tests"
            })
            
            return {
                "status": "success", 
                "message": f"Testset loaded with {len(self.testset_instance.tests)} tests",
                "tests": list(self.testset_instance.tests.keys())
            }
            
        except (OSError, FileNotFoundError) as e:
            log.error(f"Testset file operation failed: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"File operation failed: {e}"})
            return {"status": "error", "message": f"File operation failed: {e}"}
        except ImportError as e:
            log.error(f"Testing module not available: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Testing module not available: {e}"})
            return {"status": "error", "message": f"Testing module not available: {e}"}
        except Exception as e:
            log.error(f"Unexpected testset upload error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Testset upload failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    async def _set_variables(self, websocket, variables: str):
        """Set variables for test execution."""
        log.info(f"Setting variables: {variables[:100]}...")
        try:
            new_variables = json.loads(variables)
            self.current_variables.update(new_variables)
            
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Set {len(new_variables)} variables"
            })
            
            return {
                "status": "success",
                "message": f"Set {len(new_variables)} variables",
                "variables": self.current_variables
            }
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON in variables: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Invalid JSON format: {e}"})
            return {"status": "error", "message": f"Invalid JSON format: {e}"}
        except Exception as e:
            log.error(f"Unexpected variable setting error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Variable setting failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    async def _run_test(self, websocket, test_name: str):
        """Run a specific test."""
        log.info(f"Running test: {test_name}")
        try:
            if not self.testset_instance:
                return {"status": "error", "message": "No testset loaded"}
            
            if test_name not in self.testset_instance.tests:
                return {
                    "status": "error",
                    "message": f"Test '{test_name}' not found",
                    "available_tests": list(self.testset_instance.tests.keys())
                }
            
            await self.send_event(websocket, EventType.TEST_START, {"test_name": test_name})
            
            # Execute test
            self.testset_instance.test(test_name, self.current_variables)
            
            await self.send_event(websocket, EventType.TEST_COMPLETE, {"test_name": test_name})
            log.info(f"Test completed successfully: {test_name}")
            
            return {"status": "success", "message": f"Test '{test_name}' executed successfully"}
            
        except TestsetExecutionError as e:
            log.error(f"Test execution error: {test_name}: {e}")
            await self.send_event(websocket, EventType.TEST_FAILED, {
                "test_name": test_name, "error": str(e)
            })
            return {"status": "error", "message": f"Test execution failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected test error: {test_name}: {e}")
            await self.send_event(websocket, EventType.TEST_FAILED, {
                "test_name": test_name, "error": str(e)
            })
            return {"status": "error", "message": str(e)}
    
    async def _run_all_tests(self, websocket):
        """Run all available tests."""
        log.info("Running all tests")
        try:
            if not self.testset_instance:
                return {"status": "error", "message": "No testset loaded"}
            
            test_names = list(self.testset_instance.tests.keys())
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Running {len(test_names)} tests"
            })
            
            # Execute all tests
            self.testset_instance.testall(self.current_variables)
            
            log.info(f"All tests completed: {len(test_names)} tests")
            await self.send_event(websocket, EventType.LOG, {
                "message": f"All {len(test_names)} tests completed successfully"
            })
            
            return {
                "status": "success",
                "message": f"All {len(test_names)} tests executed",
                "tests": test_names
            }
            
        except TestsetExecutionError as e:
            log.error(f"Test suite execution error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Test suite execution failed: {e}"})
            return {"status": "error", "message": f"Test suite execution failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected test suite error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Test execution failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    async def _list_tests(self, websocket):
        """List available tests."""
        log.info("Listing available tests")
        try:
            if not self.testset_instance:
                return {"status": "error", "message": "No testset loaded"}
            
            tests = list(self.testset_instance.tests.keys())
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Found {len(tests)} available tests"
            })
            
            return {
                "status": "success",
                "tests": tests,
                "count": len(self.testset_instance.tests)
            }
        except AttributeError as e:
            log.error(f"Testset not properly initialized: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Testset not initialized: {e}"})
            return {"status": "error", "message": f"Testset not initialized: {e}"}
        except Exception as e:
            log.error(f"Unexpected list tests error: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Failed to list tests: {e}"})
            return {"status": "error", "message": str(e)}
    
    async def _execute_shell(self, websocket, shell_command: str, cwd: str = None, env: dict = None, timeout: float = None, shell: bool = False):
        """Execute a raw shell command with advanced options."""
        log.info(f"Executing shell command: {shell_command}")
        try:
            await self.send_event(websocket, EventType.COMMAND_START, {"shell_command": shell_command})
            
            # Prepare options for execute_on_shell
            from pathlib import Path
            options = {}
            if cwd:
                options['cwd'] = Path(cwd)
            if env:
                options['env'] = env
            if timeout:
                options['timeout'] = timeout
            if shell is not None:
                options['shell'] = shell
            
            # Execute shell command directly using execute_on_shell
            result = execute_on_shell(shell_command.split(" "), **options)
            
            if result['returncode'] == 0:
                await self.send_event(websocket, EventType.COMMAND_COMPLETE, {"shell_command": shell_command})
                log.info(f"Shell command completed successfully: {shell_command}")
                return {
                    "status": "success", 
                    "message": f"Shell command executed successfully",
                    "returncode": result['returncode'],
                    "stdout": result['stdout']
                }
            else:
                await self.send_event(websocket, EventType.ERROR, {"message": f"Shell command failed: {shell_command}"})
                log.error(f"Shell command failed with return code {result['returncode']}: {shell_command}")
                return {
                    "status": "error", 
                    "message": f"Shell command failed with return code {result['returncode']}",
                    "returncode": result['returncode'],
                    "stdout": result['stdout']
                }
            
        except Exception as e:
            log.error(f"Unexpected shell command error: {shell_command}: {e}")
            await self.send_event(websocket, EventType.ERROR, {"message": f"Shell command '{shell_command}' failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    async def _get_status(self, websocket):
        """Get current server status."""
        return {
            "testfunctions_uploaded": self.testfunctions_dir is not None and self.testfunctions_dir.exists(),
            "testfunctions_path": str(self.testfunctions_dir) if self.testfunctions_dir else None,
            "testset_loaded": self.testset_instance is not None,
            "available_tests": list(self.testset_instance.tests.keys()) if self.testset_instance else [],
            "variables_count": len(self.current_variables),
            "variables": self.current_variables,
            "connected_clients": len(self.clients)
        }


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
from typing import Dict, List, Any, Optional, Set, Tuple, Union
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
        self.current_variables: Dict[str, Any] = {}

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
            log.error(f"Unexpected screenshot error: {e}", exc_info=True)
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
            log.error(f"Unexpected upload error: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {"message": f"Upload failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    def _find_project_directory(self) -> str:
        """Find the adarevm project directory containing pyproject.toml."""
        import os
        from pathlib import Path

        # Common deployment paths to check
        possible_paths = [
            "/adare/app/adarevm",  # VM runtime deployment path (adarevm in runtime directory)
            "/adare/app",  # Legacy deployment path (whole adare directory)
            "/adare",      # Alternative deployment path
            Path(__file__).parent.parent.parent,  # Development path (../../../)
            Path.cwd(),    # Current working directory
        ]

        for path in possible_paths:
            path = Path(path)
            pyproject_path = path / "pyproject.toml"
            if pyproject_path.exists():
                log.info(f"Found pyproject.toml at: {path}")
                return str(path)

        # Fallback to current directory
        log.warning("Could not find pyproject.toml, falling back to current directory")
        return str(Path.cwd())

    async def _install_dependencies(self, websocket, dependencies: List[str], prefer_binary: bool = False):
        """Install Python dependencies using Poetry.

        Args:
            websocket: WebSocket connection
            dependencies: List of dependencies to install
            prefer_binary: If True, configure Poetry to only use binary packages (avoid compilation)
        """
        await self.send_event(websocket, EventType.LOG, {"message": f"Starting dependency installation: {len(dependencies)} packages"})

        try:
            if not dependencies:
                log.info("No dependencies to install")
                return {"status": "success", "message": "No dependencies to install"}

            log.info(f"Installing dependencies with Poetry: {dependencies}")

            # Step 1: Find project directory
            await self.send_event(websocket, EventType.LOG, {"message": "Step 1/4: Locating pyproject.toml..."})
            project_dir = self._find_project_directory()
            await self.send_event(websocket, EventType.LOG, {"message": f"Found project directory: {project_dir}"})

            step_count = "4" if not prefer_binary else "5"
            current_step = 2

            # Step 2: Configure Poetry for binary-only installation (if requested)
            if prefer_binary:
                await self.send_event(websocket, EventType.LOG, {"message": f"Step {current_step}/{step_count}: Configuring Poetry for binary-only installation..."})
                config_cmd = ["poetry", "config", "--local", "installer.only-binary", ":all:"]
                log.info(f"Running config command: {' '.join(config_cmd)} in directory: {project_dir}")

                config_process = await asyncio.create_subprocess_exec(
                    *config_cmd,
                    cwd=project_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                config_stdout, config_stderr = await config_process.communicate()

                if config_process.returncode != 0:
                    log.warning(f"Poetry config failed (continuing anyway): {config_stderr.decode('utf-8') if config_stderr else 'unknown error'}")
                else:
                    log.info("Poetry configured for binary-only installation")
                current_step += 1

            # Step 2/3: Prepare Poetry add command
            await self.send_event(websocket, EventType.LOG, {"message": f"Step {current_step}/{step_count}: Preparing Poetry command..."})
            cmd = ["poetry", "add"] + dependencies
            log.info(f"Running command: {' '.join(cmd)} in directory: {project_dir}")
            await self.send_event(websocket, EventType.LOG, {"message": f"Command: {' '.join(cmd)}"})
            current_step += 1

            # Step 3/4: Execute installation
            await self.send_event(websocket, EventType.LOG, {"message": f"Step {current_step}/{step_count}: Installing dependencies (this may take several minutes)..."})

            # Use asyncio subprocess to avoid blocking the event loop
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for process with periodic heartbeat to keep WebSocket alive
            stdout, stderr = await self._wait_for_process_with_heartbeat(
                websocket, process, timeout=600.0
            )

            # Decode bytes to string
            stdout = stdout.decode('utf-8') if stdout else ""
            stderr = stderr.decode('utf-8') if stderr else ""
            
            if process.returncode != 0:
                await self.send_event(websocket, EventType.LOG, {"message": f"Step {step_count}/{step_count}: Installation failed"})
                error_msg = f"Poetry add failed with exit code {process.returncode}"
                if stderr.strip():
                    error_msg += f": {stderr}"
                else:
                    error_msg += " (no error output)"
                if stdout.strip():
                    error_msg += f"\nStdout: {stdout}"

                log.error(error_msg)
                log.error(f"CLAUDE: Poetry command details - Exit code: {process.returncode}, Stderr: '{stderr}', Stdout: '{stdout}'")
                await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
                return {"status": "error", "message": error_msg}
            else:
                await self.send_event(websocket, EventType.LOG, {"message": f"Step {step_count}/{step_count}: Installation completed successfully"})
                success_msg = f"Successfully installed all {len(dependencies)} dependencies with Poetry"
                log.info(success_msg)
                log.debug(f"Poetry output: {stdout}")
                await self.send_event(websocket, EventType.LOG, {"message": success_msg})

                return {
                    "status": "success",
                    "message": success_msg,
                    "installed_count": len(dependencies),
                    "poetry_output": stdout
                }
            
        except asyncio.TimeoutError as e:
            error_msg = f"Poetry dependency installation timed out: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}
        except (OSError, FileNotFoundError) as e:
            error_msg = f"Poetry dependency installation failed: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {"message": error_msg})
            return {"status": "error", "message": error_msg}

    async def _wait_for_process_with_heartbeat(self, websocket, process, timeout=600.0, heartbeat_interval=30.0):
        """Wait for subprocess with periodic WebSocket heartbeat to prevent disconnection.

        Args:
            websocket: WebSocket connection for heartbeat messages
            process: asyncio subprocess to monitor
            timeout: Maximum time to wait for process completion
            heartbeat_interval: Seconds between heartbeat messages

        Returns:
            Tuple of (stdout, stderr) from process

        Raises:
            asyncio.TimeoutError: If process exceeds timeout
            OSError: If process execution fails
        """
        start_time = time.time()
        heartbeat_task = None
        websocket_alive = True

        async def send_heartbeat():
            """Send periodic heartbeat messages to keep WebSocket alive."""
            nonlocal websocket_alive
            heartbeat_count = 0

            while True:
                try:
                    await asyncio.sleep(heartbeat_interval)
                    if not websocket_alive:
                        break

                    heartbeat_count += 1
                    elapsed = time.time() - start_time
                    await self.send_event(websocket, EventType.LOG, {
                        "message": f"Installation in progress... ({elapsed:.0f}s elapsed)"
                    })
                    log.debug(f"Sent heartbeat {heartbeat_count} after {elapsed:.1f}s")

                except websockets.exceptions.ConnectionClosed:
                    log.warning("WebSocket disconnected during heartbeat, continuing process in background")
                    websocket_alive = False
                    break
                except Exception as e:
                    log.warning(f"Heartbeat failed: {e}, continuing process", exc_info=True)
                    websocket_alive = False
                    break

        try:
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(send_heartbeat())

            # Wait for process with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return stdout, stderr

        except websockets.exceptions.ConnectionClosed:
            log.warning("WebSocket disconnected during process wait, continuing in background")
            websocket_alive = False
            # Continue waiting for process even if WebSocket is gone
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            return stdout, stderr

        finally:
            # Clean up heartbeat task
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

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
            log.error(f"Unexpected variable setting error: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {"message": f"Variable setting failed: {e}"})
            return {"status": "error", "message": str(e)}
    
    
    
    
    
    def _execute_resolved_test_data(self, resolved_test_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a test using pre-resolved test data."""
        log.info(f"CLAUDE: Starting test execution with resolved_test_data: {resolved_test_data}")
        
        try:
            # Validate resolved_test_data is not None
            if resolved_test_data is None:
                error_msg = "No test data provided - resolved_test_data is None"
                log.error(error_msg)
                # This is a system error, not a test failure
                from adarelib.event.event import TestResult
                from adarelib.constants import StatusEnum
                return TestResult.error([error_msg])
            
            # Check if testfunctions directory is available
            if not self.testfunctions_dir or not self.testfunctions_dir.exists():
                error_msg = "No testfunctions directory available. Please upload testfunctions first."
                log.error(error_msg)
                # This is a system error, not a test failure
                from adarelib.event.event import TestResult
                from adarelib.constants import StatusEnum
                return TestResult.error([error_msg])
                
            # Import test function class based on function name
            from adarelib.testset.testfunction import import_basictest_subclasses, get_testclass_from_testfunction
            from adarelib.event.event import TestResult
            from adarelib.constants import StatusEnum
            
            try:
                supported_tests = import_basictest_subclasses(directory=self.testfunctions_dir)
            except Exception as e:
                log.error(f"Error importing test functions: {e}", exc_info=True)
                return TestResult.execution_error(e, "Failed to import testfunctions")
            
            function_name = resolved_test_data.get('function')
            if not function_name:
                return TestResult.error(["No test function specified"])
            
            # Get test class using the proper helper function
            test_class = get_testclass_from_testfunction(function_name, supported_tests)
            if not test_class:
                return TestResult.error([f"Test function '{function_name}' not found"])
            
            # Create test instance with required arguments
            test_name = resolved_test_data.get('name', 'unknown_test')
            test_description = resolved_test_data.get('description', '')
            
            # No complex timestamp processing - use resolved test data as-is
            processed_test_data = resolved_test_data
            
            try:
                # Create proper parameter instance using the test class's parameter class
                parameter_instance = None
                if 'parameter' in processed_test_data:
                    # Get parameter class from the test class's type annotations
                    import typing
                    type_hints = typing.get_type_hints(test_class)
                    
                    if 'parameter' not in type_hints:
                        return TestResult.error([f"No parameter type annotation found for {test_class.__name__}"])
                    
                    parameter_class = type_hints['parameter']
                    parameter_instance = parameter_class(**processed_test_data['parameter'])
                
                variable_metadata = processed_test_data.get('_VARIABLE_METADATA', {})
                log.info(f"CLAUDE: Creating test instance with variable_metadata: {variable_metadata}")
                
                test_instance = test_class(
                    name=test_name,
                    parameter=parameter_instance,
                    description=test_description,
                    variable_metadata=variable_metadata
                )
            except Exception as e:
                log.error(f"Error creating test instance: {e}", exc_info=True)
                return TestResult.execution_error(e, f"Failed to create test instance for {function_name}")
            
            # Execute the test - this returns a TestResult object
            try:
                test_result = test_instance.test()
                if test_result is None:
                    return TestResult.error(["Test returned None result"])
                return test_result
            except Exception as e:
                # Test execution threw an exception - this is an ERROR, not a FAILED test
                log.error(f"Test execution threw exception: {e}")
                return TestResult.execution_error(e, f"Test {test_name} threw exception during execution")
                
        except Exception as e:
            # System-level exception during test setup/teardown
            log.error(f"System error executing resolved test data: {e}")
            from adarelib.event.event import TestResult
            return TestResult.execution_error(e, "System error during test execution")
    
    async def _run_test(self, websocket, test_name: str, resolved_test_data: dict):
        """Run a test with pre-resolved test data (variables already substituted)."""
        log.info(f"Running test: {test_name}")
        log.debug(f"Test '{test_name}' resolved_test_data: {resolved_test_data}")
        try:
            await self.send_event(websocket, EventType.TEST_START, {"test_name": test_name})
            
            # Execute test with resolved data by creating temporary test instance
            test_result = self._execute_resolved_test_data(resolved_test_data)
            
            # Use TestResultLogger to handle logging and formatting
            from adarevm.testing.result_logger import TestResultLogger
            TestResultLogger.log_test_result(test_name, test_result)
            result_data = TestResultLogger.format_result_for_response(test_name, test_result)
            
            await self.send_event(websocket, EventType.TEST_COMPLETE, {"test_name": test_name})
            log.info(f"Test execution completed: {test_name}")
            
            return {"status": "success", "message": f"Test '{test_name}' executed", "result": result_data}
            
        except TestsetExecutionError as e:
            log.error(f"Test execution error: {test_name}: {e}")
            await self.send_event(websocket, EventType.TEST_FAILED, {
                "test_name": test_name, "error": str(e)
            })
            return {"status": "error", "message": f"Test execution failed: {e}"}
        except Exception as e:
            log.error(f"Unexpected test error: {test_name}: {e}", exc_info=True)
            await self.send_event(websocket, EventType.TEST_FAILED, {
                "test_name": test_name, "error": str(e)
            })
            return {"status": "error", "message": str(e)}
    
    
    async def _execute_shell(self, websocket, shell_command: str, cwd: str = None, env: dict = None, timeout: float = None, shell: bool = False, inherit_env: bool = True, admin: bool = False, background: bool = False, run_as_user: str = None):
        """Execute a raw shell command with advanced options."""
        import time
        import uuid

        # Generate unique command ID for tracking
        command_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        log.info(f"[{command_id}] Executing shell command: {shell_command}")
        log.debug(f"[{command_id}] Command options - cwd: {cwd}, timeout: {timeout}, shell: {shell}, inherit_env: {inherit_env}, admin: {admin}, background: {background}, run_as_user: {run_as_user}")
        
        try:
            await self.send_event(websocket, EventType.COMMAND_START, {
                "shell_command": shell_command, 
                "command_id": command_id,
                "start_time": start_time
            })
            
            # Prepare options for execute_on_shell
            from pathlib import Path
            options = {}
            if cwd:
                options['cwd'] = Path(cwd)
            if env:
                options['env'] = env
            if timeout:
                options['timeout'] = timeout
            if inherit_env is not None:
                options['inherit_env'] = inherit_env
            if admin is not None:
                options['admin'] = admin
            if background is not None:
                options['background'] = background
            if run_as_user is not None:
                options['run_as_user'] = run_as_user
            if shell is not None:
                options['shell'] = shell
            else:
                # Auto-detect if shell mode is needed based on special characters
                shell_chars = ['>', '<', '>>', '|', '||', '&&', ';', '`', '$', '*', '?', '~']
                if any(char in shell_command for char in shell_chars):
                    options['shell'] = True
                    log.info(f"Auto-enabled shell mode for command with special characters: {shell_command}")
            
            # Execute shell command directly using execute_on_shell
            # When shell=True, pass command as string; otherwise split into list
            # Log command execution start
            log.debug(f"[{command_id}] Starting shell execution with options: {options}")
            
            if options.get('shell', False):
                result = execute_on_shell(shell_command, **options)
            else:
                result = execute_on_shell(shell_command.split(" "), **options)

            execution_time = time.time() - start_time

            # Handle background mode response
            if result.get('background'):
                await self.send_event(websocket, EventType.COMMAND_COMPLETE, {
                    "shell_command": shell_command,
                    "command_id": command_id,
                    "background": True,
                    "pid": result.get('pid')
                })
                log.info(f"[{command_id}] Background command started with PID {result.get('pid')}: {shell_command}")
                return {
                    "status": "success",
                    "message": f"Background command started",
                    "background": True,
                    "pid": result.get('pid'),
                    "command_id": command_id
                }

            # Handle normal mode response
            if result['returncode'] == 0:
                await self.send_event(websocket, EventType.COMMAND_COMPLETE, {
                    "shell_command": shell_command,
                    "command_id": command_id,
                    "execution_time": execution_time
                })
                log.info(f"[{command_id}] Shell command completed successfully in {execution_time:.2f}s: {shell_command}")
                return {
                    "status": "success",
                    "message": f"Shell command executed successfully",
                    "returncode": result['returncode'],
                    "stdout": result['stdout'],
                    "command_id": command_id,
                    "execution_time": execution_time
                }
            else:
                await self.send_event(websocket, EventType.ERROR, {
                    "message": f"Shell command failed: {shell_command}",
                    "command_id": command_id,
                    "execution_time": execution_time
                })
                log.error(f"[{command_id}] Shell command failed with return code {result['returncode']} in {execution_time:.2f}s: {shell_command}")
                return {
                    "status": "error",
                    "message": f"Shell command failed with return code {result['returncode']}",
                    "returncode": result['returncode'],
                    "stdout": result['stdout'],
                    "command_id": command_id,
                    "execution_time": execution_time
                }
            
        except Exception as e:
            execution_time = time.time() - start_time
            log.error(f"[{command_id}] Unexpected shell command error after {execution_time:.2f}s: {shell_command}: {e}")
            await self.send_event(websocket, EventType.ERROR, {
                "message": f"Shell command '{shell_command}' failed: {e}",
                "command_id": command_id,
                "execution_time": execution_time
            })
            return {
                "status": "error", 
                "message": str(e),
                "command_id": command_id,
                "execution_time": execution_time
            }
    
    async def _get_status(self, websocket):
        """Get current server status."""
        return {
            "testfunctions_uploaded": self.testfunctions_dir is not None and self.testfunctions_dir.exists(),
            "testfunctions_path": str(self.testfunctions_dir) if self.testfunctions_dir else None,
            "variables_count": len(self.current_variables),
            "variables": self.current_variables,
            "connected_clients": len(self.clients)
        }

    async def _collect_system_info(self, websocket):
        """Collect comprehensive system information from the guest VM."""
        import platform
        import time
        from datetime import datetime, timezone

        collection_start = time.time()
        log.info("Starting system information collection...")

        try:
            system_info = {
                'os_info': {},
                'installed_packages': [],
                'package_manager': 'unknown'
            }

            # Detect platform
            guest_platform = platform.system().lower()
            system_info['guest_platform'] = guest_platform

            if guest_platform == 'windows':
                # Use Windows platform functions
                from adarevm.platforms.windows import get_os_info, get_installed_programs, get_windows_features, get_installed_updates

                system_info['os_info'] = get_os_info()
                system_info['installed_programs'] = get_installed_programs()
                system_info['windows_features'] = get_windows_features()
                system_info['installed_updates'] = get_installed_updates()

            else:
                # Use Linux platform functions
                from adarevm.platforms.linux import get_os_info, detect_package_manager, get_installed_packages

                system_info['os_info'] = get_os_info()

                # Detect package manager and get packages
                package_manager = detect_package_manager()
                if package_manager:
                    system_info['package_manager'] = package_manager
                    system_info['installed_packages'] = get_installed_packages(package_manager)
                    log.info(f"Found {len(system_info['installed_packages'])} packages using {package_manager}")

            collection_time = time.time() - collection_start
            log.info(f"System information collection completed in {collection_time:.2f} seconds")

            # Send success event
            await self.send_event(websocket, EventType.LOG, {
                "message": f"System information collected successfully in {collection_time:.2f}s",
                "packages_found": len(system_info.get('installed_packages', [])),
                "os_detected": system_info['os_info'].get('name', 'Unknown')
            })

            return {
                "status": "success",
                "system_info": system_info,
                "collection_time": collection_time
            }

        except Exception as e:
            collection_time = time.time() - collection_start
            log.error(f"System information collection failed after {collection_time:.2f}s: {e}", exc_info=True)

            await self.send_event(websocket, EventType.ERROR, {
                "message": f"System information collection failed: {str(e)}",
                "collection_time": collection_time
            })

            return {
                "status": "error",
                "message": str(e),
                "collection_time": collection_time
            }

    async def _set_screenshot_method(self, websocket, use_maim: bool):
        """Set the screenshot method to use (maim or pyautogui)."""
        log.info(f"Setting screenshot method to: {'maim' if use_maim else 'pyautogui'}")
        try:
            from adarevm.automation.gui import set_screenshot_method
            set_screenshot_method(use_maim)

            await self.send_event(websocket, EventType.LOG, {
                "message": f"Screenshot method set to: {'maim' if use_maim else 'pyautogui'}"
            })

            return {
                "status": "success",
                "message": f"Screenshot method set to: {'maim' if use_maim else 'pyautogui'}",
                "use_maim": use_maim
            }
        except Exception as e:
            log.error(f"Failed to set screenshot method: {e}", exc_info=True)
            await self.send_event(websocket, EventType.ERROR, {
                "message": f"Failed to set screenshot method: {e}"
            })
            return {"status": "error", "message": str(e)}


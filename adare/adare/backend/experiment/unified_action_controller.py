"""
Unified Action Controller

This module consolidates the MCP and WebSocket action controllers into a single,
unified controller that provides the best features from both approaches while
maintaining clean separation between client orchestration and VM tool execution.
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Tuple, Optional, Union, Any, Protocol
from pathlib import Path
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from adare.backend.experiment.websocket_client import AdareVMClient
from adare.types.playbook import (
    Config, Settings, Target, ActionType,
    ClickAction, RightClickAction, DoubleClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction,
    ActionTestAction, CommandAction, BlockAction, ScreenshotAction,
    ExistsCondition, NotExistsCondition
)

# Type alias for better readability
Action = ActionType

log = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of an action execution."""
    success: bool
    message: str = ""
    coordinates: Optional[Tuple[int, int]] = None
    data: Optional[Dict] = None
    execution_time: float = 0.0


@dataclass
class ActionContext:
    """Context for action execution with state management."""
    variables: Dict[str, Any] = field(default_factory=dict)
    screenshot_cache: Optional[bytes] = None
    window: Optional[str] = None
    settings: Optional[Settings] = None
    
    def set_variable(self, name: str, value: Any) -> None:
        """Set a context variable."""
        self.variables[name] = value
        
    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self.variables.get(name, default)


class VMCommunicator(Protocol):
    """Protocol for VM communication backends."""
    
    async def connect(self) -> bool:
        """Connect to the VM."""
        ...
    
    async def disconnect(self) -> None:
        """Disconnect from the VM."""
        ...
    
    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the VM."""
        ...
    
    def is_connected(self) -> bool:
        """Check if connected to the VM."""
        ...


class WebSocketCommunicator:
    """WebSocket-based VM communicator."""
    
    def __init__(self, vm_server_url: str = "ws://localhost:13108"):
        self.vm_server_url = vm_server_url
        self.client: Optional[AdareVMClient] = None
        
        # Event tracking
        self.events: List[Dict] = []
        self.event_handlers: Dict[str, List] = {}
    
    async def connect(self) -> bool:
        """Connect to the adarevm WebSocket server."""
        try:
            self.client = AdareVMClient(self.vm_server_url)
            
            # Add event handlers for logging and tracking
            self.client.add_event_handler('*', self._on_event)
            
            connected = await self.client.connect()
            if connected:
                log.info(f"Connected to adarevm server at {self.vm_server_url}")
                
                # Get server status
                status = await self.client.get_status()
                log.info(f"Server status: {status}")
                
            return connected
            
        except Exception as e:
            log.error(f"Failed to connect to adarevm server: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the adarevm server."""
        if self.client:
            await self.client.disconnect()
            self.client = None
    
    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via WebSocket."""
        if not self.client or not self.client.is_connected():
            raise RuntimeError("Not connected to VM server")
        
        return await self.client.call_tool(tool_name, params)
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self.client is not None and self.client.is_connected()
    
    async def _on_event(self, event_type: str, data: Dict[str, Any]):
        """Handle events from the adarevm server."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        }
        self.events.append(event)
        
        # Log important events
        if event_type in ['gui_click', 'gui_find', 'test_start', 'test_complete', 'error']:
            log.info(f"Event: {event_type} - {data}")
        
        # Call registered handlers
        handlers = self.event_handlers.get(event_type, [])
        handlers.extend(self.event_handlers.get('*', []))
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_type, data)
                else:
                    handler(event_type, data)
            except Exception as e:
                log.error(f"Error in event handler: {e}")
    
    def add_event_handler(self, event_type: str, handler):
        """Add an event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def get_events(self, event_type: Optional[str] = None) -> List[Dict]:
        """Get recorded events, optionally filtered by type."""
        if event_type:
            return [e for e in self.events if e['type'] == event_type]
        return self.events.copy()


class UnifiedActionController:
    """
    Unified action controller that orchestrates experiment execution on the client side
    while delegating pure tool execution to the VM.
    
    This controller eliminates duplication between MCP and WebSocket approaches by:
    1. Providing a single, clean API for playbook execution
    2. Handling all orchestration logic on the client side
    3. Using the VM purely as a tool executor
    4. Supporting multiple communication backends (WebSocket, MCP)
    """
    
    def __init__(self, 
                 communicator: Optional[VMCommunicator] = None,
                 vm_server_url: str = "ws://localhost:13108"):
        """
        Initialize the unified controller.
        
        Args:
            communicator: VM communication backend (defaults to WebSocket)
            vm_server_url: URL of the VM server (for default WebSocket communicator)
        """
        self.communicator = communicator or WebSocketCommunicator(vm_server_url)
        self.context = ActionContext()
        
        # Performance tracking
        self.action_times: Dict[str, float] = {}
        self.total_actions = 0
        self.successful_actions = 0
    
    async def connect(self) -> bool:
        """Connect to the VM."""
        return await self.communicator.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from the VM."""
        await self.communicator.disconnect()
    
    def add_event_handler(self, event_type: str, handler):
        """Add an event handler (if supported by communicator)."""
        if hasattr(self.communicator, 'add_event_handler'):
            self.communicator.add_event_handler(event_type, handler)
    
    async def execute_config(self, config: Config) -> List[ActionResult]:
        """
        Execute a complete playbook configuration.
        
        This is the main orchestration method that runs on the client side.
        
        Args:
            config: Parsed playbook configuration
            
        Returns:
            List of action results
        """
        if not self.communicator.is_connected():
            raise RuntimeError("Not connected to VM server")
        
        # Store settings in context
        self.context.settings = config.settings
        
        # Apply global settings
        if config.settings:
            if config.settings.idle:
                self.context.set_variable('default_idle', config.settings.idle)
        
        results = []
        
        log.info(f"Executing playbook with {len(config.actions)} actions")
        
        for i, action in enumerate(config.actions):
            try:
                log.debug(f"Executing action {i+1}/{len(config.actions)}: {type(action).__name__}")
                
                start_time = time.time()
                result = await self.execute_action(action)
                execution_time = time.time() - start_time
                
                # Update result with timing
                result.execution_time = execution_time
                self.action_times[f"action_{i+1}"] = execution_time
                
                results.append(result)
                self.total_actions += 1
                
                if result.success:
                    self.successful_actions += 1
                else:
                    log.warning(f"Action {i+1} failed: {result.message}")
                    # Continue with next action unless specified otherwise
                
                # Apply global idle after each action
                if config.settings and config.settings.idle:
                    idle_result = await self._execute_tool("idle", {"duration": config.settings.idle})
                    if not idle_result.get('status') == 'success':
                        log.warning(f"Global idle failed: {idle_result}")
                
            except Exception as e:
                log.error(f"Error executing action {i+1}: {e}")
                results.append(ActionResult(
                    success=False,
                    message=f"Exception: {str(e)}",
                    execution_time=time.time() - start_time if 'start_time' in locals() else 0.0
                ))
        
        log.info(f"Playbook completed: {self.successful_actions}/{self.total_actions} actions successful")
        return results
    
    async def execute_action(self, action: Action) -> ActionResult:
        """
        Execute a single action.
        
        This method dispatches actions to appropriate handlers and maintains
        all orchestration logic on the client side.
        
        Args:
            action: Action to execute
            
        Returns:
            Action execution result
        """
        try:
            action_type = type(action).__name__
            log.debug(f"Executing {action_type}: {getattr(action, 'description', '')}")
            
            # Handle conditional execution
            if hasattr(action, 'when') and action.when:
                should_execute = await self._evaluate_conditions(action.when)
                if not should_execute:
                    log.info(f"Skipping action due to conditions")
                    return ActionResult(success=True, message="Skipped due to conditions")
            
            # Dispatch to appropriate handler
            if isinstance(action, ClickAction):
                return await self._execute_click(action)
            elif isinstance(action, RightClickAction):
                return await self._execute_right_click(action)
            elif isinstance(action, DoubleClickAction):
                return await self._execute_double_click(action)
            elif isinstance(action, DragAction):
                return await self._execute_drag(action)
            elif isinstance(action, KeyboardAction):
                return await self._execute_keyboard(action)
            elif isinstance(action, IdleAction):
                return await self._execute_idle(action)
            elif isinstance(action, ScrollAction):
                return await self._execute_scroll(action)
            elif isinstance(action, GotoAction):
                return await self._execute_goto(action)
            elif isinstance(action, CommandAction):
                return await self._execute_command(action)
            elif isinstance(action, ScreenshotAction):
                return await self._execute_screenshot(action)
            elif isinstance(action, BlockAction):
                return await self._execute_block(action)
            elif isinstance(action, ActionTestAction):
                return await self._execute_test(action)
            else:
                return ActionResult(
                    success=False,
                    message=f"Unknown action type: {action_type}"
                )
                
        except Exception as e:
            log.error(f"Error executing action: {e}")
            return ActionResult(
                success=False,
                message=f"Exception: {str(e)}"
            )
    
    async def _execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool on the VM."""
        return await self.communicator.call_tool(tool_name, params)
    
    async def _resolve_target(self, target: Target) -> Optional[Tuple[int, int]]:
        """
        Resolve a target to screen coordinates using CV/OCR.
        
        This orchestrates the target resolution process but delegates the actual
        image/text finding to the VM tools.
        
        Args:
            target: Target to resolve
            
        Returns:
            Coordinates if found, None otherwise
        """
        # Direct coordinates - return as-is
        if target.position:
            return tuple(target.position)
        
        # Legacy attribute support
        if hasattr(target, 'x') and hasattr(target, 'y'):
            return (target.x, target.y)
        
        # Image-based targeting using CV
        if target.image:
            try:
                result = await self._execute_tool("find_icon", {
                    "icon": target.image,
                    "threshold": 0.8
                })
                if result and "locations" in result and result["locations"]:
                    location = result["locations"][0]
                    log.info(f"Found image '{target.image}' at {location}")
                    return tuple(location)
                else:
                    log.warning(f"Image not found: {target.image}")
                    return None
            except Exception as e:
                log.error(f"Error finding image {target.image}: {e}")
                return None
        
        # Text-based targeting using OCR
        if target.text:
            try:
                result = await self._execute_tool("find_text", {
                    "text": target.text,
                    "case_sensitive": False
                })
                if result and "locations" in result and result["locations"]:
                    location_data = result["locations"][0]
                    # Extract center coordinates from bounding box
                    x = location_data["location"]["x"]
                    y = location_data["location"]["y"]
                    log.info(f"Found text '{target.text}' at ({x}, {y})")
                    return (x, y)
                else:
                    log.warning(f"Text not found: {target.text}")
                    return None
            except Exception as e:
                log.error(f"Error finding text {target.text}: {e}")
                return None
        
        log.warning(f"Target has no valid resolution method: {target}")
        return None
    
    async def _evaluate_conditions(self, conditions: List[Union[ExistsCondition, NotExistsCondition]]) -> bool:
        """
        Evaluate whether all conditions are met.
        
        Args:
            conditions: List of conditions to evaluate
            
        Returns:
            True if all conditions are met, False otherwise
        """
        for condition in conditions:
            if isinstance(condition, ExistsCondition):
                exists = await self._check_element_exists(condition.target)
                if not exists:
                    return False
            elif isinstance(condition, NotExistsCondition):
                exists = await self._check_element_exists(condition.target)
                if exists:
                    return False
                    
        return True
    
    async def _check_element_exists(self, target: Target) -> bool:
        """Check if an element (image or text) exists on screen."""
        try:
            coords = await self._resolve_target(target)
            return coords is not None
        except Exception:
            return False
    
    # Action execution methods - All delegate to VM tools
    
    async def _execute_click(self, action: ClickAction) -> ActionResult:
        """Execute a click action."""
        coords = await self._resolve_target(action.target)
        if not coords:
            return ActionResult(
                success=False,
                message=f"Could not resolve target: {action.target}"
            )
        
        x, y = coords
        try:
            result = await self._execute_tool("click", {"x": x, "y": y})
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', f"Clicked at ({x}, {y})"),
                coordinates=(x, y)
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=str(e),
                coordinates=(x, y)
            )
    
    async def _execute_right_click(self, action: RightClickAction) -> ActionResult:
        """Execute a right click action."""
        coords = await self._resolve_target(action.target)
        if not coords:
            return ActionResult(
                success=False,
                message=f"Could not resolve target: {action.target}"
            )
        
        x, y = coords
        result = await self._execute_tool("right_click", {"x": x, "y": y})
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', f"Right-clicked at ({x}, {y})"),
            coordinates=(x, y)
        )
    
    async def _execute_double_click(self, action: DoubleClickAction) -> ActionResult:
        """Execute a double click action."""
        coords = await self._resolve_target(action.target)
        if not coords:
            return ActionResult(
                success=False,
                message=f"Could not resolve target: {action.target}"
            )
        
        x, y = coords
        result = await self._execute_tool("double_click", {"x": x, "y": y})
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', f"Double-clicked at ({x}, {y})"),
            coordinates=(x, y)
        )
    
    async def _execute_drag(self, action: DragAction) -> ActionResult:
        """Execute a drag action."""
        source_coords = await self._resolve_target(action.source)
        dest_coords = await self._resolve_target(action.destination)
        
        if not source_coords or not dest_coords:
            return ActionResult(
                success=False,
                message="Could not resolve source or destination target"
            )
        
        x1, y1 = source_coords
        x2, y2 = dest_coords
        result = await self._execute_tool("drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"),
            coordinates=(x2, y2)
        )
    
    async def _execute_keyboard(self, action: KeyboardAction) -> ActionResult:
        """Execute a keyboard action."""
        if action.keys:
            # Type text
            result = await self._execute_tool("keyboard", {"type": "type", "key": action.keys})
            message = f"Typed: {action.keys}"
        elif action.combination:
            # Key combination
            combo = "+".join(action.combination)
            result = await self._execute_tool("keyboard", {"type": "hotkey", "key": combo})
            message = f"Pressed combination: {combo}"
        else:
            return ActionResult(
                success=False,
                message="No keys or combination specified"
            )
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', message)
        )
    
    async def _execute_idle(self, action: IdleAction) -> ActionResult:
        """Execute an idle action."""
        duration = action.duration or self.context.get_variable('default_idle', 1.0)
        result = await self._execute_tool("idle", {"duration": duration})
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', f"Waited {duration} seconds")
        )
    
    async def _execute_scroll(self, action: ScrollAction) -> ActionResult:
        """Execute a scroll action."""
        direction = "up" if action.direction == "up" else "down"
        amount = action.amount or 3
        
        result = await self._execute_tool("scroll", {"direction": direction, "amount": amount})
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', f"Scrolled {direction} by {amount}")
        )
    
    async def _execute_goto(self, action: GotoAction) -> ActionResult:
        """Execute a goto action."""
        coords = await self._resolve_target(action.target)
        if not coords:
            return ActionResult(
                success=False,
                message=f"Could not resolve target: {action.target}"
            )
        
        x, y = coords
        result = await self._execute_tool("goto", {"x": x, "y": y})
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', f"Moved to ({x}, {y})"),
            coordinates=(x, y)
        )
    
    async def _execute_command(self, action: CommandAction) -> ActionResult:
        """Execute a command action."""
        try:
            result = await self._execute_tool("execute_command", {"command": action.command})
            
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Command execution failed: {str(e)}"
            )
    
    async def _execute_screenshot(self, action: ScreenshotAction) -> ActionResult:
        """Execute a screenshot action."""
        try:
            params = {}
            if hasattr(action, 'x'):
                params.update({"x": action.x, "y": action.y, 
                              "width": action.width, "height": action.height})
            
            result = await self._execute_tool("screenshot", params)
            
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', 'Screenshot captured'),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Screenshot failed: {str(e)}"
            )
    
    async def _execute_block(self, action: BlockAction) -> ActionResult:
        """Execute a conditional block action."""
        # Check conditions
        if action.when:
            conditions_met = await self._evaluate_conditions(action.when)
            if not conditions_met:
                return ActionResult(
                    success=True,
                    message="Block conditions not met, skipping"
                )
        
        # Execute block actions
        results = []
        for block_action in action.actions:
            result = await self.execute_action(block_action)
            results.append(result)
            
            if not result.success:
                return ActionResult(
                    success=False,
                    message=f"Block action failed: {result.message}",
                    data={"action_results": results}
                )
        
        return ActionResult(
            success=True,
            message=f"Block executed successfully ({len(results)} actions)",
            data={"action_results": results}
        )
    
    async def _execute_test(self, action: ActionTestAction) -> ActionResult:
        """Execute a test action by delegating to VM test execution."""
        try:
            result = await self._execute_tool("run_test", {"test_name": action.function})
            
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', f"Test {action.function} executed"),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Test execution failed: {str(e)}"
            )
    
    # Test management methods - Orchestrated on client side
    
    async def upload_testfunctions(self, testfunctions_path: Path) -> ActionResult:
        """Upload testfunctions to the VM."""
        try:
            result = await self._execute_tool("upload_testfunctions", {"path": str(testfunctions_path)})
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Upload failed: {str(e)}"
            )
    
    async def upload_testset(self, testset_yaml: str) -> ActionResult:
        """Upload testset configuration to the VM."""
        try:
            result = await self._execute_tool("upload_testset", {"testset": testset_yaml})
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Upload failed: {str(e)}"
            )
    
    async def run_test(self, test_name: str) -> ActionResult:
        """Run a specific test on the VM."""
        try:
            result = await self._execute_tool("run_test", {"test_name": test_name})
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Test execution failed: {str(e)}"
            )
    
    async def run_all_tests(self) -> ActionResult:
        """Run all tests on the VM."""
        try:
            result = await self._execute_tool("run_all_tests", {})
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
                data=result
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Test execution failed: {str(e)}"
            )
    
    # Utility methods
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return {
            "action_times": self.action_times.copy(),
            "total_actions": self.total_actions,
            "successful_actions": self.successful_actions,
            "success_rate": (self.successful_actions / self.total_actions) if self.total_actions > 0 else 0.0
        }
    
    def get_events(self, event_type: Optional[str] = None) -> List[Dict]:
        """Get recorded events (if supported by communicator)."""
        if hasattr(self.communicator, 'get_events'):
            return self.communicator.get_events(event_type)
        return []
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Convenience functions for direct usage

async def execute_playbook_file(playbook_path: Path, 
                               vm_server_url: str = "ws://localhost:13108") -> List[ActionResult]:
    """
    Execute a YAML playbook file.
    
    Args:
        playbook_path: Path to the YAML playbook file
        vm_server_url: VM server URL
        
    Returns:
        List of action results
    """
    from adare.types.playbook import parse_config
    
    config = parse_config(playbook_path)
    
    async with UnifiedActionController(vm_server_url=vm_server_url) as controller:
        return await controller.execute_config(config)


async def execute_actions(actions: List[Action],
                         settings: Optional[Settings] = None,
                         vm_server_url: str = "ws://localhost:13108") -> List[ActionResult]:
    """
    Execute a list of actions directly.
    
    Args:
        actions: List of actions to execute
        settings: Optional settings for execution
        vm_server_url: VM server URL
        
    Returns:
        List of action results
    """
    from adare.types.playbook import Config
    
    config = Config(actions=actions, settings=settings)
    
    async with UnifiedActionController(vm_server_url=vm_server_url) as controller:
        return await controller.execute_config(config)


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Create a simple action sequence
        from adare.types.playbook import ClickAction, IdleAction, KeyboardAction, Target
        
        actions = [
            ClickAction(target=Target(image="button.png"), description="Click the button"),
            IdleAction(duration=1.0, description="Wait 1 second"),
            KeyboardAction(keys="Hello World", description="Type hello world"),
            KeyboardAction(combination=["ctrl", "s"], description="Save")
        ]
        
        results = await execute_actions(actions)
        
        for i, result in enumerate(results):
            status = 'SUCCESS' if result.success else 'FAILED'
            print(f"Action {i+1}: {status} - {result.message} ({result.execution_time:.2f}s)")
    
    asyncio.run(example())
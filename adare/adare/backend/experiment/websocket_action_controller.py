"""
WebSocket GUI Action Controller

This module provides a controller that executes action sequences defined in YAML playbooks
by communicating with the adarevm WebSocket server for GUI automation and test execution.
"""

import asyncio
import logging
import json
from typing import Dict, List, Tuple, Optional, Union, Any
from pathlib import Path
from dataclasses import dataclass, field
import time

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


class WebSocketActionController:
    """
    Controller for executing GUI actions via WebSocket communication with adarevm.
    
    This controller replaces the MCP-based controller with WebSocket communication
    for better real-time feedback and event streaming.
    """
    
    def __init__(self, vm_server_url: str = "ws://localhost:13108"):
        """
        Initialize the controller.
        
        Args:
            vm_server_url: WebSocket URL of the adarevm server
        """
        self.vm_server_url = vm_server_url
        self.client: Optional[AdareVMClient] = None
        self.context = ActionContext()
        
        # Event tracking
        self.events: List[Dict] = []
        self.event_handlers: Dict[str, List] = {}
        
        # Performance tracking
        self.action_times: Dict[str, float] = {}
    
    async def connect(self) -> bool:
        """
        Connect to the adarevm server.
        
        Returns:
            True if connected successfully
        """
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
    
    async def disconnect(self):
        """Disconnect from the adarevm server."""
        if self.client:
            await self.client.disconnect()
            self.client = None
    
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
    
    async def execute_config(self, config: Config) -> List[ActionResult]:
        """
        Execute a complete playbook configuration.
        
        Args:
            config: Parsed playbook configuration
            
        Returns:
            List of action results
        """
        if not self.client or not self.client.is_connected():
            raise RuntimeError("Not connected to adarevm server")
        
        # Store settings in context
        self.context.settings = config.settings
        
        # Apply global idle setting
        if config.settings and config.settings.idle:
            self.context.set_variable('default_idle', config.settings.idle)
        
        results = []
        
        log.info(f"Executing playbook with {len(config.actions)} actions")
        
        for i, action in enumerate(config.actions):
            try:
                log.debug(f"Executing action {i+1}/{len(config.actions)}: {type(action).__name__}")
                
                start_time = time.time()
                result = await self.execute_action(action)
                execution_time = time.time() - start_time
                
                self.action_times[f"action_{i+1}"] = execution_time
                
                results.append(result)
                
                if not result.success:
                    log.warning(f"Action {i+1} failed: {result.message}")
                    # Continue with next action unless specified otherwise
                
                # Apply global idle after each action
                if config.settings and config.settings.idle:
                    await self.client.idle(config.settings.idle)
                
            except Exception as e:
                log.error(f"Error executing action {i+1}: {e}")
                results.append(ActionResult(
                    success=False,
                    message=f"Exception: {str(e)}"
                ))
        
        return results
    
    async def execute_action(self, action: Action) -> ActionResult:
        """
        Execute a single action.
        
        Args:
            action: Action to execute
            
        Returns:
            Action execution result
        """
        try:
            action_type = type(action).__name__
            log.debug(f"Executing {action_type}: {action.description}")
            
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
    
    async def _resolve_target(self, target: Target) -> Optional[Tuple[int, int]]:
        """
        Resolve a target to screen coordinates using CV/OCR.
        
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
                result = await self.client.call_tool("find_icon", {
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
                result = await self.client.call_tool("find_text", {
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
            result = await self.client.click(x, y)
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
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
        result = await self.client.right_click(x, y)
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', ''),
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
        result = await self.client.double_click(x, y)
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', ''),
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
        result = await self.client.drag(x1, y1, x2, y2)
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', ''),
            coordinates=(x2, y2)
        )
    
    async def _execute_keyboard(self, action: KeyboardAction) -> ActionResult:
        """Execute a keyboard action."""
        if action.keys:
            # Type text
            result = await self.client.keyboard("type", action.keys)
        elif action.combination:
            # Key combination
            combo = "+".join(action.combination)
            result = await self.client.keyboard("hotkey", combo)
        else:
            return ActionResult(
                success=False,
                message="No keys or combination specified"
            )
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', '')
        )
    
    async def _execute_idle(self, action: IdleAction) -> ActionResult:
        """Execute an idle action."""
        duration = action.duration or self.context.get_variable('default_idle', 1.0)
        result = await self.client.idle(duration)
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', '')
        )
    
    async def _execute_scroll(self, action: ScrollAction) -> ActionResult:
        """Execute a scroll action."""
        direction = "up" if action.direction == "up" else "down"
        amount = action.amount or 3
        
        result = await self.client.scroll(direction, amount)
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', '')
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
        result = await self.client.goto(x, y)
        
        return ActionResult(
            success=result.get('status') == 'success',
            message=result.get('message', ''),
            coordinates=(x, y)
        )
    
    async def _execute_command(self, action: CommandAction) -> ActionResult:
        """Execute a command action."""
        try:
            result = await self.client.execute_command(action.command)
            
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
    
    async def _execute_screenshot(self, action) -> ActionResult:
        """Execute a screenshot action."""
        try:
            result = await self.client.screenshot(action.x, action.y, action.width, action.height)
            
            return ActionResult(
                success=result.get('status') == 'success',
                message=result.get('message', ''),
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
            conditions_met = await self._check_conditions(action.when)
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
                    message=f"Block action failed: {result.message}"
                )
        
        return ActionResult(
            success=True,
            message=f"Block executed successfully ({len(results)} actions)"
        )
    
    async def _check_conditions(self, conditions: List[Union[ExistsCondition, NotExistsCondition]]) -> bool:
        """Check if conditions are met."""
        for condition in conditions:
            if isinstance(condition, ExistsCondition):
                # Check if target exists
                coords = await self._resolve_target(condition.target)
                if not coords:
                    return False
            elif isinstance(condition, NotExistsCondition):
                # Check if target does not exist
                coords = await self._resolve_target(condition.target)
                if coords:
                    return False
        
        return True
    
    # Test management methods
    
    async def upload_testfunctions(self, testfunctions_path: Path) -> ActionResult:
        """Upload testfunctions to the VM."""
        try:
            result = await self.client.upload_testfunctions(testfunctions_path)
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
            result = await self.client.upload_testset(testset_yaml)
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
        """Run a test on the VM."""
        try:
            result = await self.client.run_test(test_name)
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
            result = await self.client.run_all_tests()
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
    
    def get_events(self, event_type: Optional[str] = None) -> List[Dict]:
        """Get recorded events, optionally filtered by type."""
        if event_type:
            return [e for e in self.events if e['type'] == event_type]
        return self.events.copy()
    
    def get_performance_stats(self) -> Dict[str, float]:
        """Get performance statistics."""
        return self.action_times.copy()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Backwards compatibility alias
MCPActionController = WebSocketActionController
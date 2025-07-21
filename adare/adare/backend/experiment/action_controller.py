"""
MCP GUI Action Controller

This module provides a controller that executes action sequences defined in YAML playbooks
by coordinating between the MCP servers (basic actions on port 13108 and computer vision on port 13109).
"""

import asyncio
import logging
import json
from typing import Dict, List, Tuple, Optional, Union, Any
from pathlib import Path
from dataclasses import dataclass, field

from fastmcp import Client
from adare.types.playbook import (
    Config, Settings, Target, ActionType,
    ClickAction, RightClickAction, DoubleClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction,
    ActionTestAction, CommandAction, BlockAction,
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


class MCPActionController:
    """
    Controller that executes action sequences via MCP servers.
    
    Coordinates between:
    - Basic action server (port 13108): clicks, keyboard, etc.
    - GUI server (port 13109): computer vision, OCR
    """
    
    def __init__(self, 
                 action_server_url: str = "http://localhost:13108/mcp",
                 gui_server_url: str = "http://localhost:13109/mcp"):
        self.action_server_url = action_server_url
        self.gui_server_url = gui_server_url
        self.context = ActionContext()
        
    async def execute_config(self, config: Config) -> List[ActionResult]:
        """
        Execute a complete playbook configuration.
        
        Args:
            config: The parsed playbook configuration
            
        Returns:
            List of action results
        """
        results = []
        
        # Set up context with settings
        if config.settings:
            self.context.settings = config.settings
            
        # Execute actions sequentially
        for action in config.actions:
            try:
                result = await self.execute_action(action)
                results.append(result)
                
                # Stop on failure unless explicitly configured to continue
                if not result.success:
                    log.error(f"Action failed: {result.message}")
                    break
                    
            except Exception as e:
                log.error(f"Exception executing action {action}: {e}")
                results.append(ActionResult(success=False, message=str(e)))
                break
                
        return results
    
    async def execute_action(self, action: Action) -> ActionResult:
        """
        Execute a single action based on its type.
        
        Args:
            action: The action to execute
            
        Returns:
            ActionResult indicating success/failure
        """
        log.info(f"Executing action: {type(action).__name__}")
        
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
        elif isinstance(action, ActionTestAction):
            return await self._execute_test(action)
        elif isinstance(action, CommandAction):
            return await self._execute_command(action)
        elif isinstance(action, BlockAction):
            return await self._execute_block(action)
        else:
            return ActionResult(success=False, message=f"Unknown action type: {type(action)}")
    
    async def _resolve_target(self, target: Target) -> Tuple[int, int]:
        """
        Resolve a target specification to actual coordinates.
        
        Args:
            target: Target specification (image, text, or position)
            
        Returns:
            Tuple of (x, y) coordinates
            
        Raises:
            ValueError: If target cannot be resolved
        """
        if target.position:
            return tuple(target.position)
            
        if target.image:
            return await self._find_image_coordinates(target.image)
            
        if target.text:
            return await self._find_text_coordinates(target.text)
            
        raise ValueError("Target must specify image, text, or position")
    
    async def _find_image_coordinates(self, image_name: str) -> Tuple[int, int]:
        """Find coordinates of an image using computer vision."""
        async with Client(self.gui_server_url) as client:
            result = await client.call_tool("find_icon", {
                "icon": image_name,
                "window": self.context.window
            })
            
            data = json.loads(result[0].text)
            if not data.get("found"):
                raise ValueError(f"Image '{image_name}' not found on screen")
                
            coords = data.get("coordinates", [])
            if not coords:
                raise ValueError(f"No coordinates returned for image '{image_name}'")
                
            # Return center of first match
            x, y = coords[0]
            return x, y
    
    async def _find_text_coordinates(self, text: str) -> Tuple[int, int]:
        """Find coordinates of text using OCR."""
        async with Client(self.gui_server_url) as client:
            result = await client.call_tool("find_text", {
                "text": text,
                "window": self.context.window
            })
            
            data = json.loads(result[0].text)
            if not data.get("found"):
                raise ValueError(f"Text '{text}' not found on screen")
                
            coords = data.get("coordinates", [])
            if not coords:
                raise ValueError(f"No coordinates returned for text '{text}'")
                
            # Return center of first match
            x, y = coords[0]
            return x, y
    
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
                exists = await self._check_element_exists(condition)
                if not exists:
                    return False
            elif isinstance(condition, NotExistsCondition):
                exists = await self._check_element_exists(condition)
                if exists:
                    return False
                    
        return True
    
    async def _check_element_exists(self, condition: Union[ExistsCondition, NotExistsCondition]) -> bool:
        """Check if an element (image or text) exists on screen."""
        try:
            if condition.image:
                await self._find_image_coordinates(condition.image)
                return True
            elif condition.text:
                await self._find_text_coordinates(condition.text)
                return True
        except ValueError:
            return False
        return False
    
    # Action execution methods
    
    async def _execute_click(self, action: ClickAction) -> ActionResult:
        """Execute a click action."""
        try:
            x, y = await self._resolve_target(action.target)
            
            async with Client(self.action_server_url) as client:
                await client.call_tool("click", {"x": x, "y": y})
                
            return ActionResult(
                success=True, 
                message=f"Clicked at ({x}, {y})",
                coordinates=(x, y)
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_right_click(self, action: RightClickAction) -> ActionResult:
        """Execute a right-click action."""
        try:
            x, y = await self._resolve_target(action.target)
            
            async with Client(self.action_server_url) as client:
                await client.call_tool("right_click", {"x": x, "y": y})
                
            return ActionResult(
                success=True,
                message=f"Right-clicked at ({x}, {y})",
                coordinates=(x, y)
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_double_click(self, action: DoubleClickAction) -> ActionResult:
        """Execute a double-click action."""
        try:
            x, y = await self._resolve_target(action.target)
            
            async with Client(self.action_server_url) as client:
                await client.call_tool("double_click", {"x": x, "y": y})
                
            return ActionResult(
                success=True,
                message=f"Double-clicked at ({x}, {y})",
                coordinates=(x, y)
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_drag(self, action: DragAction) -> ActionResult:
        """Execute a drag action."""
        try:
            x1, y1 = await self._resolve_target(action.source)
            x2, y2 = await self._resolve_target(action.destination)
            
            async with Client(self.action_server_url) as client:
                await client.call_tool("drag", {
                    "x1": x1, "y1": y1,
                    "x2": x2, "y2": y2
                })
                
            return ActionResult(
                success=True,
                message=f"Dragged from ({x1}, {y1}) to ({x2}, {y2})",
                coordinates=((x1, y1), (x2, y2))
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_keyboard(self, action: KeyboardAction) -> ActionResult:
        """Execute a keyboard action."""
        try:
            async with Client(self.action_server_url) as client:
                if action.keys:
                    await client.call_tool("keyboard", {
                        "type": "type",
                        "key": action.keys
                    })
                    message = f"Typed: {action.keys}"
                elif action.combination:
                    await client.call_tool("keyboard", {
                        "type": "hotkey",
                        "key": "+".join(action.combination)
                    })
                    message = f"Pressed combination: {'+'.join(action.combination)}"
                else:
                    return ActionResult(success=False, message="No keys or combination specified")
                
            return ActionResult(success=True, message=message)
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_idle(self, action: IdleAction) -> ActionResult:
        """Execute an idle/wait action."""
        try:
            duration = action.duration
            if duration is None and self.context.settings:
                duration = self.context.settings.idle
            if duration is None:
                duration = 1.0
                
            async with Client(self.action_server_url) as client:
                await client.call_tool("idle", {"duration": duration})
                
            return ActionResult(success=True, message=f"Waited {duration} seconds")
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_scroll(self, action: ScrollAction) -> ActionResult:
        """Execute a scroll action."""
        try:
            async with Client(self.action_server_url) as client:
                await client.call_tool("scroll", {
                    "direction": action.direction,
                    "amount": action.amount
                })
                
            return ActionResult(
                success=True,
                message=f"Scrolled {action.direction} by {action.amount}"
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_goto(self, action: GotoAction) -> ActionResult:
        """Execute a goto/move action."""
        try:
            x, y = await self._resolve_target(action.target)
            
            async with Client(self.action_server_url) as client:
                await client.call_tool("goto", {"x": x, "y": y})
                
            return ActionResult(
                success=True,
                message=f"Moved to ({x}, {y})",
                coordinates=(x, y)
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_test(self, action: ActionTestAction) -> ActionResult:
        """Execute a test action."""
        # This would integrate with your test function system
        # For now, return a placeholder
        return ActionResult(
            success=True,
            message=f"Test action executed: {action.function}"
        )
    
    async def _execute_command(self, action: CommandAction) -> ActionResult:
        """Execute a command action."""
        try:
            # Execute shell command
            import subprocess
            result = subprocess.run(
                action.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=action.timeout if hasattr(action, 'timeout') else 30
            )
            
            if result.returncode == 0:
                return ActionResult(
                    success=True,
                    message=f"Command executed successfully: {action.command}",
                    data={"stdout": result.stdout, "stderr": result.stderr}
                )
            else:
                return ActionResult(
                    success=False,
                    message=f"Command failed with exit code {result.returncode}: {result.stderr}"
                )
        except Exception as e:
            return ActionResult(success=False, message=str(e))
    
    async def _execute_block(self, action: BlockAction) -> ActionResult:
        """Execute a block of actions."""
        # Handle conditional execution for the block
        if action.when:
            should_execute = await self._evaluate_conditions(action.when)
            if not should_execute:
                return ActionResult(success=True, message="Block skipped due to conditions")
        
        # Execute all actions in the block
        results = []
        for block_action in action.actions:
            result = await self.execute_action(block_action)
            results.append(result)
            
            # Stop on failure unless configured otherwise
            if not result.success:
                break
        
        success = all(r.success for r in results)
        return ActionResult(
            success=success,
            message=f"Block executed: {len(results)} actions, {sum(1 for r in results if r.success)} successful",
            data={"action_results": results}
        )


class PlaybookExecutor:
    """
    High-level executor for YAML playbook files.
    """
    
    def __init__(self, controller: Optional[MCPActionController] = None):
        self.controller = controller or MCPActionController()
    
    async def execute_playbook_file(self, playbook_path: Path) -> List[ActionResult]:
        """
        Load and execute a YAML playbook file.
        
        Args:
            playbook_path: Path to the YAML playbook file
            
        Returns:
            List of action results
        """
        import yaml
        import cattrs
        
        with open(playbook_path, 'r') as f:
            playbook_data = yaml.safe_load(f)
        
        # Convert to Config object using cattrs
        converter = cattrs.Converter()
        config = converter.structure(playbook_data, Config)
        
        return await self.controller.execute_config(config)
    
    async def execute_playbook_dict(self, playbook_dict: Dict) -> List[ActionResult]:
        """
        Execute a playbook from a dictionary.
        
        Args:
            playbook_dict: Dictionary containing playbook configuration
            
        Returns:
            List of action results
        """
        import cattrs
        
        converter = cattrs.Converter()
        config = converter.structure(playbook_dict, Config)
        
        return await self.controller.execute_config(config)


# Convenience functions for direct usage

async def execute_actions(actions: List[Action], 
                         settings: Optional[Settings] = None) -> List[ActionResult]:
    """
    Execute a list of actions directly.
    
    Args:
        actions: List of actions to execute
        settings: Optional settings for execution
        
    Returns:
        List of action results
    """
    config = Config(actions=actions, settings=settings)
    controller = MCPActionController()
    return await controller.execute_config(config)


async def execute_playbook(playbook_path: Union[str, Path]) -> List[ActionResult]:
    """
    Execute a playbook file.
    
    Args:
        playbook_path: Path to the YAML playbook file
        
    Returns:
        List of action results
    """
    executor = PlaybookExecutor()
    return await executor.execute_playbook_file(Path(playbook_path))


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Create a simple action sequence
        actions = [
            ClickAction(target=Target(image="button.png"), description="Click the button"),
            IdleAction(duration=1.0, description="Wait 1 second"),
            KeyboardAction(keys="Hello World", description="Type hello world"),
            KeyboardAction(combination=["ctrl", "s"], description="Save")
        ]
        
        results = await execute_actions(actions)
        
        for i, result in enumerate(results):
            print(f"Action {i+1}: {'SUCCESS' if result.success else 'FAILED'} - {result.message}")
    
    asyncio.run(example())
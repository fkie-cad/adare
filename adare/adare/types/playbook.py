from __future__ import annotations
import attrs
from typing import List, Optional, Union
import yaml
import cattrs
from pathlib import Path

# Import the new Variable system
from adarelib.common.variables import VariableRegistry
from adarelib.testset.type import Test

# Target selection strategies
@attrs.define
class SweepStrategy:
    """Select the nth match when scanning left-to-right, top-to-bottom."""
    index: int = 1  # 1-based index (1 = first, 2 = second, etc.)

@attrs.define
class BestConfidenceStrategy:
    """Select match with highest confidence score."""
    pass

@attrs.define
class ClosestToStrategy:
    """Select match closest to specified coordinates."""
    x: int
    y: int

@attrs.define
class TopLeftStrategy:
    """Select topmost-leftmost match."""
    pass

@attrs.define
class TopRightStrategy:
    """Select topmost-rightmost match."""
    pass

@attrs.define
class BottomLeftStrategy:
    """Select bottommost-leftmost match."""
    pass

@attrs.define
class BottomRightStrategy:
    """Select bottommost-rightmost match."""
    pass

@attrs.define
class LargestStrategy:
    """Select match with largest bounding box area."""
    pass

@attrs.define
class SmallestStrategy:
    """Select match with smallest bounding box area."""
    pass

TargetStrategyType = Union[
    SweepStrategy,
    BestConfidenceStrategy, 
    ClosestToStrategy,
    TopLeftStrategy,
    TopRightStrategy,
    BottomLeftStrategy,
    BottomRightStrategy,
    LargestStrategy,
    SmallestStrategy
]

@attrs.define
class Settings:
    idle: float = 0.1
    timeout: Optional[float] = None
    screenshot: Optional[dict] = None
    continue_on_test_failure: bool = False

@attrs.define
class Target:
    image: Optional[str] = None
    text: Optional[str] = None
    position: Optional[List[int]] = None
    strategy: Optional[TargetStrategyType] = None

@attrs.define
class ExistsCondition:
    text: Optional[str] = None
    image: Optional[str] = None

@attrs.define
class NotExistsCondition:
    text: Optional[str] = None
    image: Optional[str] = None

@attrs.define
class KeyboardAction:
    key: Optional[str] = None  # Single key press -> pyautogui.press()
    text: Optional[str] = None  # Text typing -> pyautogui.typewrite()
    combination: Optional[List[str]] = None  # Key combinations -> pyautogui.hotkey()
    when: Optional[List[Union['ExistsCondition', 'NotExistsCondition']]] = None
    description: str = ''

@attrs.define
class ClickAction:
    target: Target
    type: str = 'left'  # 'left', 'right', 'double'
    description: str = ''

@attrs.define
class DragAction:
    src: Target
    dst: Target
    description: str = ''

@attrs.define
class IdleAction:
    duration: float
    description: str = ''

@attrs.define
class ScrollAction:
    direction: str
    amount: int
    description: str = ''

@attrs.define
class GotoAction:
    target: Target
    description: str = ''

# info: Do NOT rename it to TestAction, since it lets pytest think it is a test
@attrs.define
class ActionTestAction:
    name: str
    description: str = ''

@attrs.define
class CommandAction:
    command: str  # Required field - the shell command to execute
    name: Optional[str] = None
    description: str = ''
    tool: Optional[str] = None
    cwd: Optional[str] = None
    env: Optional[dict] = None
    timeout: Optional[float] = None
    shell: bool = False

@attrs.define
class ScreenshotAction:
    description: str = ''
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

@attrs.define
class SaveTimestampAction:
    variable: str
    description: str = ''

@attrs.define
class PullAction:
    src: str  # Path to file/directory in VM to pull
    dst: Optional[str] = None  # Optional destination name in artifacts folder
    description: str = ''
    # Note: Always pulls recursively - no need for recursive parameter

@attrs.define
class BlockAction:
    actions: List[ActionType]  # Remove quotes
    description: str = ''
    when: Optional[List[Union['ExistsCondition', 'NotExistsCondition']]] = None

# Now define ActionType after all classes
ActionType = Union[
    ClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction, ActionTestAction, 
    CommandAction, ScreenshotAction, BlockAction, SaveTimestampAction, PullAction
]

@attrs.define
class Playbook:
    actions: List[ActionType]
    settings: Settings = attrs.Factory(Settings)
    variables: Optional[VariableRegistry] = None
    tests: List[Test] = attrs.Factory(list)

def parse_playbook(yaml_path: Union[str, Path], vm_os: str = None, vm_user: str = None) -> Playbook:  # Accept Path or str
    yaml_path = Path(yaml_path)  # Ensure it's a Path object
    
    # Use custom YAML loader to handle our custom tags
    from adarelib.testset.yaml.customloader import get_custom_loader
    
    with yaml_path.open('r') as f:
        data = yaml.load(f, Loader=get_custom_loader())
    
    # Get automatic variables
    from adarelib.common.automatic_variables import AutomaticVariables
    automatic_vars = AutomaticVariables.get_automatic_variables(vm_os=vm_os, vm_user=vm_user)
    
    # Convert variables to VariableRegistry if present and merge with automatic variables
    if 'variables' in data and data['variables']:
        from adarelib.common.variables import VariableRegistry
        user_vars = VariableRegistry.from_dict(data['variables'])
        data['variables'] = AutomaticVariables.merge_with_user_variables(automatic_vars, user_vars)
    else:
        # No user variables, just use automatic ones
        data['variables'] = automatic_vars
    
    # Tests will be converted by cattrs when structuring the Playbook object
    # No need to convert them here
    
    converter = cattrs.Converter()
    
    # Configure converter to forbid extra keys - fail on unknown fields
    converter.forbid_extra_keys = True
    
    # Register structure hooks for Union types if needed
    converter.register_structure_hook(
        ActionType,
        lambda obj, _: _structure_action(obj, converter)
    )
    converter.register_structure_hook(
        Union[ExistsCondition, NotExistsCondition],
        lambda obj, _: _structure_condition(obj, converter)
    )
    converter.register_structure_hook(
        Optional[TargetStrategyType],
        lambda obj, _: _structure_strategy(obj, converter) if obj is not None else None
    )
    
    # Register structure hook for VariableRegistry
    converter.register_structure_hook(
        VariableRegistry,
        lambda obj, _: obj if isinstance(obj, VariableRegistry) else VariableRegistry.from_dict(obj)
    )
    converter.register_structure_hook(
        Optional[VariableRegistry],
        lambda obj, _: obj if obj is None or isinstance(obj, VariableRegistry) else VariableRegistry.from_dict(obj)
    )
    
    # Register strict structure hooks for all main classes to validate fields
    _register_strict_hooks(converter)
    
    return converter.structure(data, Playbook)

def _structure_action(obj, converter):
    if 'click' in obj:
        return converter.structure(obj['click'], ClickAction)
    if 'drag' in obj:
        return converter.structure(obj['drag'], DragAction)
    if 'keyboard' in obj:
        return converter.structure(obj['keyboard'], KeyboardAction)
    if 'idle' in obj:
        return converter.structure(obj['idle'], IdleAction)
    if 'scroll' in obj:
        return converter.structure(obj['scroll'], ScrollAction)
    if 'goto' in obj:
        return converter.structure(obj['goto'], GotoAction)
    if 'block' in obj:
        return converter.structure(obj['block'], BlockAction)
    if 'test' in obj:
        if isinstance(obj['test'], str):
            # Handle inline test format: - test: testname
            return ActionTestAction(name=obj['test'])
        else:
            # Handle full test format with description
            return converter.structure(obj['test'], ActionTestAction)
    if 'command' in obj:
        return converter.structure(obj['command'], CommandAction)
    if 'screenshot' in obj:
        return converter.structure(obj['screenshot'], ScreenshotAction)
    if 'save_timestamp' in obj:
        return converter.structure(obj['save_timestamp'], SaveTimestampAction)
    if 'pull' in obj:
        return converter.structure(obj['pull'], PullAction)
    raise ValueError(f"Unknown action: {obj}")

def _structure_condition(obj, converter):
    if 'exists' in obj:
        return converter.structure(obj['exists'], ExistsCondition)
    if 'not_exists' in obj:
        return converter.structure(obj['not_exists'], NotExistsCondition)
    raise ValueError(f"Unknown condition: {obj}")

def _structure_strategy(obj, converter):
    if 'SweepStrategy' in obj:
        return converter.structure(obj['SweepStrategy'], SweepStrategy)
    if 'BestConfidenceStrategy' in obj:
        return converter.structure(obj['BestConfidenceStrategy'], BestConfidenceStrategy)
    if 'ClosestToStrategy' in obj:
        return converter.structure(obj['ClosestToStrategy'], ClosestToStrategy)
    if 'TopLeftStrategy' in obj:
        return converter.structure(obj['TopLeftStrategy'], TopLeftStrategy)
    if 'TopRightStrategy' in obj:
        return converter.structure(obj['TopRightStrategy'], TopRightStrategy)
    if 'BottomLeftStrategy' in obj:
        return converter.structure(obj['BottomLeftStrategy'], BottomLeftStrategy)
    if 'BottomRightStrategy' in obj:
        return converter.structure(obj['BottomRightStrategy'], BottomRightStrategy)
    if 'LargestStrategy' in obj:
        return converter.structure(obj['LargestStrategy'], LargestStrategy)
    if 'SmallestStrategy' in obj:
        return converter.structure(obj['SmallestStrategy'], SmallestStrategy)
    raise ValueError(f"Unknown strategy: {obj}")

def _register_strict_hooks(converter):
    """Register strict structure hooks that validate all fields."""
    
    def _validate_attrs_class(cls):
        """Create a strict structure hook for an attrs class."""
        def strict_structure_hook(obj, _):
            # Get expected field names from the attrs class
            if not attrs.has(cls):
                # Use cattrs default structure for non-attrs classes
                return cattrs.structure(obj, cls)
                
            expected_fields = {field.name for field in attrs.fields(cls)}
            
            # Check for unexpected fields
            if isinstance(obj, dict):
                extra_fields = set(obj.keys()) - expected_fields
                if extra_fields:
                    raise ValueError(
                        f"Unexpected field(s) in {cls.__name__}: {', '.join(sorted(extra_fields))}. "
                        f"Expected fields: {', '.join(sorted(expected_fields))}"
                    )
            
            # Use cattrs default structure with a fresh converter to avoid recursion
            fresh_converter = cattrs.Converter()
            # Copy union hooks to fresh converter to handle nested unions
            fresh_converter.register_structure_hook(
                ActionType,
                lambda obj, _: _structure_action(obj, fresh_converter)
            )
            fresh_converter.register_structure_hook(
                Union[ExistsCondition, NotExistsCondition],
                lambda obj, _: _structure_condition(obj, fresh_converter)
            )
            fresh_converter.register_structure_hook(
                Optional[TargetStrategyType],
                lambda obj, _: _structure_strategy(obj, fresh_converter) if obj is not None else None
            )
            fresh_converter.register_structure_hook(
                VariableRegistry,
                lambda obj, _: obj if isinstance(obj, VariableRegistry) else VariableRegistry.from_dict(obj)
            )
            fresh_converter.register_structure_hook(
                Optional[VariableRegistry],
                lambda obj, _: obj if obj is None or isinstance(obj, VariableRegistry) else VariableRegistry.from_dict(obj)
            )
            return fresh_converter.structure(obj, cls)
        return strict_structure_hook
    
    # Register hooks for all main attrs classes
    for cls in [Target, Settings, ClickAction, 
                DragAction, KeyboardAction, IdleAction, ScrollAction, GotoAction,
                ActionTestAction, CommandAction, ScreenshotAction, BlockAction,
                SaveTimestampAction, PullAction, ExistsCondition, NotExistsCondition,
                SweepStrategy, BestConfidenceStrategy, ClosestToStrategy,
                TopLeftStrategy, TopRightStrategy, BottomLeftStrategy,
                BottomRightStrategy, LargestStrategy, SmallestStrategy, Playbook]:
        if attrs.has(cls):
            converter.register_structure_hook(cls, _validate_attrs_class(cls))
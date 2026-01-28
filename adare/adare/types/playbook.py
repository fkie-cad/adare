from __future__ import annotations
import attrs
from typing import List, Optional, Union, Any
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
    """Select match closest to coordinates or target reference.

    Supports three modes:
    1. Fixed coordinates: x, y specified
    2. Text reference: text specified
    3. Image reference: image specified

    Optional max_distance enables region-based search optimization.
    """
    # Mode 1: Fixed coordinates (existing - backwards compatible)
    x: Optional[int] = None
    y: Optional[int] = None

    # Mode 2: Text reference (new)
    text: Optional[str] = None

    # Mode 3: Image reference (new)
    image: Optional[str] = None

    # Optional distance limit (new)
    max_distance: Optional[int] = None  # pixels

    def __attrs_post_init__(self):
        """Validate that exactly one mode is specified."""
        modes_set = sum([
            self.x is not None and self.y is not None,  # coordinates mode
            self.text is not None,  # text reference mode
            self.image is not None  # image reference mode
        ])

        if modes_set != 1:
            raise ValueError(
                "ClosestToStrategy must specify exactly one of: "
                "(x, y) coordinates, text reference, or image reference"
            )

        # Validate x,y together
        if (self.x is None) != (self.y is None):
            raise ValueError(
                "ClosestToStrategy: x and y must both be specified or both be None"
            )

        # Validate max_distance
        if self.max_distance is not None and self.max_distance <= 0:
            raise ValueError(
                f"ClosestToStrategy: max_distance must be positive, got {self.max_distance}"
            )

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
    auto_pull_on_test_failure: bool = True
    collect_system_info: bool = True
    forensic_logging: bool = True  # Generate forensic audit logs (YAML) after experiment completion
    enable_filesystem_diff: bool = True  # Enable automatic snapshots at experiment start/end
    gui_execution_mode: str = 'auto'  # GUI automation mode: 'auto', 'agent', 'host' (QEMU only)

@attrs.define
class Offset:
    x: int = 0
    y: int = 0
    base: str = 'center'  # center, top-left, top-right, bottom-left, bottom-right, center-left, center-right, top-center, bottom-center

    def __attrs_post_init__(self):
        valid_bases = {
            'center', 'top-left', 'top-right', 'bottom-left', 'bottom-right',
            'center-left', 'center-right', 'top-center', 'bottom-center'
        }
        if self.base not in valid_bases:
            raise ValueError(f"Offset.base must be one of {valid_bases}, got '{self.base}'")


@attrs.define
class Target:
    image: Optional[str] = None
    text: Optional[str] = None
    position: Optional[List[int]] = None
    strategy: Optional[TargetStrategyType] = None
    offset: Optional[Offset] = None


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
class CaptureSpec:
    """Specification for capturing command output to a variable."""
    variable: str  # Variable name to store the captured output
    source: str = 'stdout'  # Source to capture from: stdout, stderr, returncode, all
    parser: Optional[str] = None  # Optional Python expression to parse the output

    def __attrs_post_init__(self):
        """Validate capture specification."""
        valid_sources = {'stdout', 'stderr', 'returncode', 'all'}
        if self.source not in valid_sources:
            raise ValueError(
                f"CaptureSpec.source must be one of {valid_sources}, got '{self.source}'"
            )

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
    admin: bool = False  # Run with elevated privileges (Windows: RunAs, Linux: sudo)
    background: bool = False  # Run without waiting for completion
    capture: Optional[CaptureSpec] = None  # Capture command output to variable
    allow_failure: bool = False  # Continue execution even if command returns non-zero exit code

    def __attrs_post_init__(self):
        """Validate that command is a string, not a list."""
        if isinstance(self.command, list):
            raise ValueError(
                f"CommandAction.command must be a string, not a list. "
                f"Found: {self.command}. "
                f"Use 'command: \"your command here\"' instead of array notation."
            )

@attrs.define
class ScreenshotAction:
    description: str = ''
    name: Optional[str] = None  # Optional custom name for screenshot file
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

@attrs.define
class SaveTimestampAction:
    variable: str
    description: str = ''

@attrs.define
class SaveVariableAction:
    """Save a value (static or Jinja2 expression) to a variable."""
    name: str  # Variable name to save to
    value: Any  # Static value OR Jinja2 template string
    description: str = ''

@attrs.define
class PullAction:
    src: Union[str, List[str]]  # Single path or list of paths to pull
    dst: Optional[str] = None  # Optional destination name in artifacts folder
    description: str = ''
    mode: str = 'hypervisor'  # Transfer mode: 'hypervisor' or 'websocket'

    def __attrs_post_init__(self):
        """Validate mode field."""
        valid_modes = {'hypervisor', 'websocket'}
        if self.mode not in valid_modes:
            raise ValueError(
                f"PullAction.mode must be one of {valid_modes}, got '{self.mode}'"
            )

@attrs.define
class SnapshotFilesystemAction:
    """Capture filesystem snapshot and store in variable."""
    variable: str  # Variable name to store snapshot data
    root_path: Optional[str] = None  # Root path to scan (default: / or C:\)
    timeout: Optional[float] = 300.0  # Timeout in seconds (default: 5 minutes)
    description: str = ''

@attrs.define
class PullChangedFilesAction:
    """Pull files that changed between two filesystem snapshots.

    Automatically calculates diff between snapshots and pulls all changed/added files
    in batch using efficient chunked transfer.
    """
    snapshot_before: str  # Variable name containing initial snapshot
    snapshot_after: str   # Variable name containing final snapshot
    dst: str = 'changed_files'  # Destination folder in artifacts
    mode: str = 'websocket'  # Transfer mode: 'hypervisor' or 'websocket'
    include_modified: bool = True  # Pull modified files
    include_added: bool = True  # Pull added files
    description: str = ''

    def __attrs_post_init__(self):
        """Validate fields."""
        valid_modes = {'hypervisor', 'websocket'}
        if self.mode not in valid_modes:
            raise ValueError(
                f"PullChangedFilesAction.mode must be one of {valid_modes}, got '{self.mode}'"
            )

        if not self.include_modified and not self.include_added:
            raise ValueError(
                "PullChangedFilesAction must include at least one of: "
                "include_modified or include_added"
            )

@attrs.define
class PauseAction:
    message: Optional[str] = None  # Optional message to display during pause
    name: Optional[str] = None     # Optional name for the pause action
    description: str = ''

@attrs.define
class VariableCondition:
    """Condition for testing variable values locally (evaluated on host).

    Exactly one operator must be specified per condition.
    """
    variable: str  # Variable name to test

    # Operators (mutually exclusive - exactly one must be specified)
    equals: Optional[Any] = None  # Variable value equals this value (case-sensitive)
    contains: Optional[str] = None  # String variable contains this substring
    matches: Optional[str] = None  # Variable matches this regex pattern
    greater_than: Optional[Union[int, float]] = None  # Numeric comparison
    less_than: Optional[Union[int, float]] = None  # Numeric comparison
    is_empty: Optional[bool] = None  # Check if variable is empty/None (True) or not empty (False)

    def __attrs_post_init__(self):
        """Validation: exactly one operator must be set."""
        operators = [
            self.equals is not None,
            self.contains is not None,
            self.matches is not None,
            self.greater_than is not None,
            self.less_than is not None,
            self.is_empty is not None
        ]
        operators_set = sum(operators)

        if operators_set != 1:
            raise ValueError(
                "VariableCondition must have exactly one operator set. "
                f"Valid operators: equals, contains, matches, greater_than, less_than, is_empty"
            )

@attrs.define
class StopAction:
    """Stop playbook execution based on a condition.

    If condition is specified, stops only when condition evaluates to True.
    If no condition, always stops (unconditional stop).
    """
    condition: Optional[VariableCondition] = None
    description: str = ''

@attrs.define
class ContinueAction:
    """Skip remaining actions in current loop iteration/block based on a condition.

    If condition is specified, continues only when condition evaluates to True.
    If no condition, always continues (unconditional continue).
    Only valid within loop or block contexts.
    """
    condition: Optional[VariableCondition] = None
    description: str = ''

@attrs.define
class BlockAction:
    actions: List[ActionType]  # Remove quotes
    description: str = ''
    when: Optional[List[Union['ExistsCondition', 'NotExistsCondition']]] = None
    delay: Optional[float] = None

@attrs.define
class WaitCondition:
    """Recursive boolean condition for wait_until actions."""
    # Leaf conditions (mutually exclusive with operators)
    exists: Optional[Target] = None
    not_exists: Optional[Target] = None

    # Boolean operators (mutually exclusive with leaf conditions)
    all: Optional[List['WaitCondition']] = None  # AND logic
    any: Optional[List['WaitCondition']] = None  # OR logic
    negate: Optional['WaitCondition'] = None     # NOT logic

    def __attrs_post_init__(self):
        """Validation: exactly one field must be set."""
        fields_set = sum([
            self.exists is not None,
            self.not_exists is not None,
            self.all is not None,
            self.any is not None,
            self.negate is not None
        ])
        if fields_set != 1:
            raise ValueError("WaitCondition must have exactly one field set")

    def validate_depth(self, current_depth=0, max_depth=10):
        """Prevent infinite recursion by checking nesting depth."""
        if current_depth > max_depth:
            raise ValueError(f"WaitCondition nesting exceeds maximum depth of {max_depth}")

        # Recursively validate nested conditions
        if self.all:
            for condition in self.all:
                condition.validate_depth(current_depth + 1, max_depth)
        elif self.any:
            for condition in self.any:
                condition.validate_depth(current_depth + 1, max_depth)
        elif self.negate:
            self.negate.validate_depth(current_depth + 1, max_depth)

@attrs.define
class PixelChangeConstraint:
    above: Optional[float] = None  # Skip if change > value (Wait for stability)
    below: Optional[float] = None  # Skip if change < value (Wait for activity)
    strategy: str = 'once'         # 'once' (latch) or 'continuous' (enforce always). Default: 'once'

    def __attrs_post_init__(self):
        valid_strategies = {'once', 'continuous'}
        if self.strategy not in valid_strategies:
             raise ValueError(f"PixelChangeConstraint.strategy must be one of {valid_strategies}, got '{self.strategy}'")

@attrs.define
class SkipOptions:
    pixel_change: Optional[PixelChangeConstraint] = None

@attrs.define
class WaitUntilAction:
    condition: WaitCondition
    timeout: float = 60.0
    check_interval: float = 3.0  # Default 3s check interval (previously 0.0)
    initial_delay: float = 5.0   # Default 5s delay to let UI stabilize
    skip: Optional[SkipOptions] = None
    description: str = ''

    def __attrs_post_init__(self):
        """Validate condition tree depth."""
        self.condition.validate_depth()

@attrs.define
class LoopAction:
    """Loop over actions multiple times or iterate over a list.

    Provides automatic variables:
    - index: Current iteration (0-based)
    - total: Total number of iterations
    - item: Current item (for list iteration)
    """
    actions: List[ActionType]  # Will be resolved after ActionType is defined

    # Simple iteration (mutually exclusive with items)
    times: Optional[int] = None

    # List iteration (mutually exclusive with times)
    items: Optional[Union[str, List[Any]]] = None  # Can be "{{var}}" or direct list

    # Optional: customize item variable name (defaults to 'item')
    item_var: Optional[str] = None

    description: str = ''

    def __attrs_post_init__(self):
        """Validate that exactly one of times or items is specified."""
        if (self.times is None) == (self.items is None):
            raise ValueError("LoopAction must specify exactly one of: times or items")
        if self.times is not None and self.times < 1:
            raise ValueError(f"Loop times must be >= 1, got {self.times}")

# Now define ActionType after all classes
ActionType = Union[
    ClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction, ActionTestAction,
    CommandAction, ScreenshotAction, BlockAction, SaveTimestampAction, SaveVariableAction,
    PullAction, PauseAction, WaitUntilAction, LoopAction, StopAction, ContinueAction,
    SnapshotFilesystemAction, PullChangedFilesAction
]

@attrs.define
class Playbook:
    actions: List[ActionType]
    settings: Settings = attrs.Factory(Settings)
    variables: Optional[VariableRegistry] = None
    tests: List[Test] = attrs.Factory(list)

def parse_playbook(yaml_path: Union[str, Path]) -> Playbook:  # Accept Path or str
    import logging
    log = logging.getLogger(__name__)

    yaml_path = Path(yaml_path)  # Ensure it's a Path object

    # Use custom YAML loader to handle our custom tags
    from adarelib.testset.yaml.customloader import get_custom_loader

    with yaml_path.open('r') as f:
        data = yaml.load(f, Loader=get_custom_loader())

    # Convert variables to VariableRegistry if present (automatic variables added during resolution)
    if 'variables' in data and data['variables']:
        data['variables'] = VariableRegistry.from_dict(data['variables'])
    # Note: automatic variables will be merged during variable resolution, not during parsing
    
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

    # Register structure hook for Union[str, List[str]] in PullAction.src
    converter.register_structure_hook(
        Union[str, List[str]],
        lambda obj, _: obj if isinstance(obj, (str, list)) else str(obj)
    )

    # Register structure hook for WaitCondition
    converter.register_structure_hook(
        WaitCondition,
        lambda obj, _: _structure_wait_condition(obj, converter)
    )
    converter.register_structure_hook(
        Optional[WaitCondition],
        lambda obj, _: _structure_wait_condition(obj, converter) if obj is not None else None
    )

    # Register structure hook for LoopAction items field (Union[str, List[Any]])
    converter.register_structure_hook(
        Optional[Union[str, List[Any]]],
        lambda obj, _: obj  # Pass through as-is, will be resolved at runtime
    )

    # Register structure hook for numeric comparison fields (Union[int, float, None])
    def structure_optional_numeric(obj, _):
        if obj is None:
            return None
        if isinstance(obj, (int, float)):
            return obj
        # Try to convert string to number if needed
        if isinstance(obj, str):
            try:
                return int(obj)
            except ValueError:
                try:
                    return float(obj)
                except ValueError:
                    raise ValueError(f"Cannot convert '{obj}' to numeric value")
        return obj

    converter.register_structure_hook(
        Optional[Union[int, float]],
        structure_optional_numeric
    )
    
    # Register structure hook for SkipOptions
    converter.register_structure_hook(
        Optional[SkipOptions],
        lambda obj, _: _structure_skip_options(obj, converter) if obj is not None else None
    )

    # Register structure hook for Offset
    converter.register_structure_hook(
        Optional[Offset],
        lambda obj, _: converter.structure(obj, Offset) if obj is not None else None
    )

    # Register strict structure hooks for all main classes to validate fields
    _register_strict_hooks(converter)

    playbook = converter.structure(data, Playbook)

    # Validate playbook (variable definitions, etc.)
    from adare.types.playbook_validators import validate_playbook
    validate_playbook(playbook)

    return playbook

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
    if 'save_variable' in obj:
        return converter.structure(obj['save_variable'], SaveVariableAction)
    if 'pull' in obj:
        return converter.structure(obj['pull'], PullAction)
    if 'pause' in obj:
        return converter.structure(obj['pause'], PauseAction)
    if 'wait_until' in obj:
        return converter.structure(obj['wait_until'], WaitUntilAction)
    if 'loop' in obj:
        return converter.structure(obj['loop'], LoopAction)
    if 'stop' in obj:
        return converter.structure(obj['stop'], StopAction)
    if 'continue' in obj:
        return converter.structure(obj['continue'], ContinueAction)
    if 'snapshot_filesystem' in obj:
        return converter.structure(obj['snapshot_filesystem'], SnapshotFilesystemAction)
    if 'pull_changed_files' in obj:
        return converter.structure(obj['pull_changed_files'], PullChangedFilesAction)
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

def _structure_wait_condition(obj, converter):
    """Structure WaitCondition objects with recursive support."""
    if 'exists' in obj:
        target = converter.structure(obj['exists'], Target)
        return WaitCondition(exists=target)
    if 'not_exists' in obj:
        target = converter.structure(obj['not_exists'], Target)
        return WaitCondition(not_exists=target)
    if 'all' in obj:
        conditions = [_structure_wait_condition(condition, converter) for condition in obj['all']]
        return WaitCondition(all=conditions)
    if 'any' in obj:
        conditions = [_structure_wait_condition(condition, converter) for condition in obj['any']]
        return WaitCondition(any=conditions)
    if 'not' in obj:
        condition = _structure_wait_condition(obj['not'], converter)
        return WaitCondition(negate=condition)
    raise ValueError(f"Unknown wait condition: {obj}")

def _structure_skip_options(obj, converter):
    """Structure SkipOptions object."""
    if 'pixel_change' in obj:
        pixel_change = converter.structure(obj['pixel_change'], PixelChangeConstraint)
        return SkipOptions(pixel_change=pixel_change)
    raise ValueError(f"Unknown skip option: {obj}")

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
            fresh_converter.register_structure_hook(
                WaitCondition,
                lambda obj, _: _structure_wait_condition(obj, fresh_converter)
            )
            fresh_converter.register_structure_hook(
                Optional[WaitCondition],
                lambda obj, _: _structure_wait_condition(obj, fresh_converter) if obj is not None else None
            )
            fresh_converter.register_structure_hook(
                Optional[Union[str, List[Any]]],
                lambda obj, _: obj  # Pass through as-is for LoopAction items
            )
            # Register numeric structure hook for VariableCondition fields
            def structure_optional_numeric(obj, _):
                if obj is None:
                    return None
                if isinstance(obj, (int, float)):
                    return obj
                if isinstance(obj, str):
                    try:
                        return int(obj)
                    except ValueError:
                        try:
                            return float(obj)
                        except ValueError:
                            raise ValueError(f"Cannot convert '{obj}' to numeric value")
                return obj
            fresh_converter.register_structure_hook(
                Optional[Union[int, float]],
                structure_optional_numeric
            )
            # Register structure hook for Union[str, List[str]] in PullAction.src
            fresh_converter.register_structure_hook(
                Union[str, List[str]],
                lambda obj, _: obj if isinstance(obj, (str, list)) else str(obj)
            )
            # Register structure hook for SkipOptions
            fresh_converter.register_structure_hook(
                Optional[SkipOptions],
                lambda obj, _: _structure_skip_options(obj, fresh_converter) if obj is not None else None
            )
            return fresh_converter.structure(obj, cls)
        return strict_structure_hook
    
    # Register hooks for all main attrs classes
    for cls in [Target, Settings, ClickAction,
                DragAction, KeyboardAction, IdleAction, ScrollAction, GotoAction,
                ActionTestAction, CommandAction, CaptureSpec, ScreenshotAction, BlockAction,
                SaveTimestampAction, SaveVariableAction, PullAction, PauseAction,
                WaitUntilAction, LoopAction, StopAction, ContinueAction, VariableCondition,
                WaitCondition, ExistsCondition, NotExistsCondition,
                SweepStrategy, BestConfidenceStrategy, ClosestToStrategy,
                TopLeftStrategy, TopRightStrategy, BottomLeftStrategy,
                BottomRightStrategy, LargestStrategy, SmallestStrategy, Playbook,
                SnapshotFilesystemAction, PullChangedFilesAction, PixelChangeConstraint, SkipOptions, Offset]:
        if attrs.has(cls):
            converter.register_structure_hook(cls, _validate_attrs_class(cls))
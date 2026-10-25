from __future__ import annotations

from pathlib import Path
from typing import Any

import attrs
import cattrs
import yaml

# Re-exported: callers import these from adare.types.playbook.
from adare.types.targets import (
    BestConfidenceStrategy,
    BottomLeftStrategy,
    BottomRightStrategy,
    ClosestToStrategy,
    ExistsCondition,
    LargestStrategy,
    NotExistsCondition,
    Offset,
    SmallestStrategy,
    SweepStrategy,
    Target,
    TargetStrategyType,
    TextMatchConfig,
    TopLeftStrategy,
    TopRightStrategy,
)

# Import the new Variable system
from adarelib.common.variables import VariableRegistry
from adarelib.testset.type import Test


@attrs.define
class Settings:
    idle: float = 0.1
    timeout: float | None = None
    screenshot: dict | None = None
    continue_on_test_failure: bool = False
    auto_pull_on_test_failure: bool = True
    collect_system_info: bool = True
    forensic_logging: bool = True  # Generate forensic audit logs (YAML) after experiment completion
    enable_filesystem_diff: bool = False  # Enable automatic snapshots at experiment start/end
    gui_execution_mode: str = 'auto'  # GUI automation mode: 'auto', 'agent', 'host' (QEMU only)
    resolution: str | None = None  # Guest display resolution "WxH" (e.g. "1280x1024"); unset = host/env default
    vm_memory: int | None = None  # Working RAM in MB discovered/used for this run; boots future runs at this size
    export_disk_image: bool = (
        False  # Export the VM's overlay disk as a merged raw image (artifacts/disk/), e.g. for Autopsy ingestion
    )
    capture_pcap: bool = False  # Capture the VM's outside-world traffic to artifacts/pcap/ via QEMU filter-dump
    export_memory_dump: bool = (
        False  # Live-dump guest RAM via QMP dump-guest-memory (artifacts/memory/), e.g. for Volatility ingestion
    )
    clock_log: bool = True  # Sample the guest clock around every action into clock.jsonl (offset, jumps, timezone)


@attrs.define
class KeyboardAction:
    key: str | None = None  # Single key press -> pyautogui.press()
    text: str | None = None  # Text typing -> pyautogui.typewrite()
    combination: list[str] | None = None  # Key combinations -> pyautogui.hotkey()
    when: list[ExistsCondition | NotExistsCondition] | None = None
    description: str = ''
    machine: str | None = None


@attrs.define
class ClickAction:
    target: Target
    type: str = 'left'  # 'left', 'right', 'double'
    description: str = ''
    machine: str | None = None  # Machine key from playbook.machines this action targets (multi-machine playbooks only)


@attrs.define
class DragAction:
    src: Target
    dst: Target
    description: str = ''
    machine: str | None = None


@attrs.define
class IdleAction:
    duration: float
    description: str = ''
    machine: str | None = None


@attrs.define
class ScrollAction:
    direction: str
    amount: int
    description: str = ''
    machine: str | None = None


@attrs.define
class GotoAction:
    target: Target
    description: str = ''
    machine: str | None = None


# info: Do NOT rename it to TestAction, since it lets pytest think it is a test
@attrs.define
class ActionTestAction:
    name: str
    description: str = ''
    timeout: float | None = None  # Test timeout in seconds (None = use Test default)
    machine: str | None = None


@attrs.define
class CaptureSpec:
    """Specification for capturing command output to a variable."""

    variable: str  # Variable name to store the captured output
    source: str = 'stdout'  # Source to capture from: stdout, stderr, returncode, all
    parser: str | None = None  # Optional Python expression to parse the output

    def __attrs_post_init__(self):
        """Validate capture specification."""
        valid_sources = {'stdout', 'stderr', 'returncode', 'all'}
        if self.source not in valid_sources:
            raise ValueError(f"CaptureSpec.source must be one of {valid_sources}, got '{self.source}'")


@attrs.define
class CommandAction:
    command: str  # Required field - the shell command to execute
    name: str | None = None
    description: str = ''
    tool: str | None = None
    cwd: str | None = None
    env: dict | None = None
    timeout: float | None = None
    shell: bool = False
    admin: bool = False  # Run with elevated privileges (Windows: RunAs, Linux: sudo)
    background: bool = False  # Run without waiting for completion
    capture: CaptureSpec | None = None  # Capture command output to variable
    allow_failure: bool = False  # Continue execution even if command returns non-zero exit code
    machine: str | None = None

    def __attrs_post_init__(self):
        if isinstance(self.command, list):
            raise ValueError(
                f"CommandAction.command must be a string, not a list. "
                f"Found: {self.command}. "
                f"Use 'command: \"your command here\"' instead of array notation."
            )

        # Support for Python-style raw strings to make Windows paths easier in YAML
        # E.g. command: r"C:\Windows\System32" -> shell command: C:\Windows\System32
        if (
            self.command.startswith('r"')
            and self.command.endswith('"')
            and len(self.command) >= 3
            or self.command.startswith("r'")
            and self.command.endswith("'")
            and len(self.command) >= 3
        ):
            self.command = self.command[2:-1]


@attrs.define
class ScreenshotAction:
    description: str = ''
    name: str | None = None  # Optional custom name for screenshot file
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    machine: str | None = None


@attrs.define
class SaveTimestampAction:
    variable: str
    description: str = ''
    machine: str | None = None


@attrs.define
class SaveVariableAction:
    """Save a value (static or Jinja2 expression) to a variable."""

    name: str  # Variable name to save to
    value: Any  # Static value OR Jinja2 template string
    description: str = ''
    machine: str | None = None


@attrs.define
class PullAction:
    src: str | list[str]  # Single path or list of paths to pull
    dst: str | None = None  # Optional destination name in artifacts folder
    description: str = ''
    mode: str = 'hypervisor'  # Transfer mode: 'hypervisor' or 'websocket'
    machine: str | None = None

    def __attrs_post_init__(self):
        """Validate mode field."""
        valid_modes = {'hypervisor', 'websocket'}
        if self.mode not in valid_modes:
            raise ValueError(f"PullAction.mode must be one of {valid_modes}, got '{self.mode}'")


@attrs.define
class SnapshotFilesystemAction:
    """Capture filesystem snapshot and store in variable."""

    variable: str  # Variable name to store snapshot data
    root_path: str | None = None  # Root path to scan (default: / or C:\)
    timeout: float | None = 300.0  # Timeout in seconds (default: 5 minutes)
    description: str = ''
    machine: str | None = None


@attrs.define
class PullChangedFilesAction:
    """Pull files that changed between two filesystem snapshots.

    Automatically calculates diff between snapshots and pulls all changed/added files
    in batch using efficient chunked transfer.
    """

    snapshot_before: str  # Variable name containing initial snapshot
    snapshot_after: str  # Variable name containing final snapshot
    dst: str = 'changed_files'  # Destination folder in artifacts
    mode: str = 'websocket'  # Transfer mode: 'hypervisor' or 'websocket'
    include_modified: bool = True  # Pull modified files
    include_added: bool = True  # Pull added files
    description: str = ''
    machine: str | None = None

    def __attrs_post_init__(self):
        """Validate fields."""
        valid_modes = {'hypervisor', 'websocket'}
        if self.mode not in valid_modes:
            raise ValueError(f"PullChangedFilesAction.mode must be one of {valid_modes}, got '{self.mode}'")

        if not self.include_modified and not self.include_added:
            raise ValueError("PullChangedFilesAction must include at least one of: include_modified or include_added")


@attrs.define
class PauseAction:
    message: str | None = None  # Optional message to display during pause
    name: str | None = None  # Optional name for the pause action
    description: str = ''
    machine: str | None = None


@attrs.define
class VariableCondition:
    """Condition for testing variable values locally (evaluated on host).

    Exactly one operator must be specified per condition.
    """

    variable: str  # Variable name to test

    # Operators (mutually exclusive - exactly one must be specified)
    equals: Any | None = None  # Variable value equals this value (case-sensitive)
    contains: str | None = None  # String variable contains this substring
    matches: str | None = None  # Variable matches this regex pattern
    greater_than: int | float | None = None  # Numeric comparison
    less_than: int | float | None = None  # Numeric comparison
    is_empty: bool | None = None  # Check if variable is empty/None (True) or not empty (False)

    def __attrs_post_init__(self):
        """Validation: exactly one operator must be set."""
        operators = [
            self.equals is not None,
            self.contains is not None,
            self.matches is not None,
            self.greater_than is not None,
            self.less_than is not None,
            self.is_empty is not None,
        ]
        operators_set = sum(operators)

        if operators_set != 1:
            raise ValueError(
                "VariableCondition must have exactly one operator set. "
                "Valid operators: equals, contains, matches, greater_than, less_than, is_empty"
            )


@attrs.define
class StopAction:
    """Stop playbook execution based on a condition.

    If condition is specified, stops only when condition evaluates to True.
    If no condition, always stops (unconditional stop).
    """

    condition: VariableCondition | None = None
    description: str = ''
    machine: str | None = None


@attrs.define
class ContinueAction:
    """Skip remaining actions in current loop iteration/block based on a condition.

    If condition is specified, continues only when condition evaluates to True.
    If no condition, always continues (unconditional continue).
    Only valid within loop or block contexts.
    """

    condition: VariableCondition | None = None
    description: str = ''
    machine: str | None = None


@attrs.define
class BlockAction:
    actions: list[ActionType]  # Remove quotes
    description: str = ''
    when: list[ExistsCondition | NotExistsCondition] | None = None
    delay: float | None = None
    machine: str | None = None  # Default machine for children that don't set their own (cascades at parse time)


@attrs.define
class WaitCondition:
    """Recursive boolean condition for wait_until actions."""

    # Leaf conditions (mutually exclusive with operators)
    exists: Target | None = None
    not_exists: Target | None = None

    # Boolean operators (mutually exclusive with leaf conditions)
    all: list[WaitCondition] | None = None  # AND logic
    any: list[WaitCondition] | None = None  # OR logic
    negate: WaitCondition | None = None  # NOT logic

    def __attrs_post_init__(self):
        """Validation: exactly one field must be set."""
        fields_set = sum(
            [
                self.exists is not None,
                self.not_exists is not None,
                self.all is not None,
                self.any is not None,
                self.negate is not None,
            ]
        )
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
    above: float | None = None  # Skip if change > value (Wait for stability)
    below: float | None = None  # Skip if change < value (Wait for activity)
    strategy: str = 'once'  # 'once' (latch) or 'continuous' (enforce always). Default: 'once'
    idle: float | None = None  # Wait (s) after constraint satisfied before searching.

    def __attrs_post_init__(self):
        valid_strategies = {'once', 'continuous'}
        if self.strategy not in valid_strategies:
            raise ValueError(f"PixelChangeConstraint.strategy must be one of {valid_strategies}, got '{self.strategy}'")


@attrs.define
class SkipOptions:
    pixel_change: PixelChangeConstraint | None = None


@attrs.define
class WaitUntilAction:
    condition: WaitCondition
    timeout: float = 60.0
    check_interval: float = 3.0  # Default 3s check interval (previously 0.0)
    initial_delay: float = 5.0  # Default 5s delay to let UI stabilize
    skip: SkipOptions | None = None
    description: str = ''
    machine: str | None = None

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

    actions: list[ActionType]  # Will be resolved after ActionType is defined

    # Simple iteration (mutually exclusive with items)
    times: int | None = None

    # List iteration (mutually exclusive with times)
    items: str | list[Any] | None = None  # Can be "{{var}}" or direct list

    # Optional: customize item variable name (defaults to 'item')
    item_var: str | None = None

    description: str = ''
    machine: str | None = None  # Default machine for children that don't set their own (cascades at parse time)

    def __attrs_post_init__(self):
        """Validate that exactly one of times or items is specified."""
        if (self.times is None) == (self.items is None):
            raise ValueError("LoopAction must specify exactly one of: times or items")
        if self.times is not None and self.times < 1:
            raise ValueError(f"Loop times must be >= 1, got {self.times}")


# Now define ActionType after all classes
ActionType = (
    ClickAction
    | DragAction
    | KeyboardAction
    | IdleAction
    | ScrollAction
    | GotoAction
    | ActionTestAction
    | CommandAction
    | ScreenshotAction
    | BlockAction
    | SaveTimestampAction
    | SaveVariableAction
    | PullAction
    | PauseAction
    | WaitUntilAction
    | LoopAction
    | StopAction
    | ContinueAction
    | SnapshotFilesystemAction
    | PullChangedFilesAction
)


@attrs.define
class MachineSpec:
    """One entry of a playbook's `machines:` section (multi-machine experiments, e.g. a Nextcloud client+server pair)."""

    environment: str  # Environment name to boot this machine from
    depends_on: list[str] = attrs.Factory(list)  # Other machine keys that must finish booting first


@attrs.define
class Playbook:
    actions: list[ActionType]
    settings: Settings = attrs.Factory(Settings)
    variables: VariableRegistry | None = None
    tests: list[Test] = attrs.Factory(list)
    machines: dict[str, MachineSpec] | None = (
        None  # Multi-machine playbooks only; absent/None = today's single implicit VM
    )


def parse_playbook(yaml_path: str | Path) -> Playbook:  # Accept Path or str
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

    converter = build_playbook_converter()

    playbook = converter.structure(data, Playbook)

    # Validate playbook (variable definitions, etc.)
    from adare.types.playbook_validators import validate_playbook

    validate_playbook(playbook)

    return playbook


def build_playbook_converter() -> cattrs.Converter:
    """Build the cattrs converter that structures playbook YAML into action objects.

    Extracted from ``parse_playbook`` so callers that structure a *single* action
    outside a playbook (dev mode's ``adare dev action``) can reuse the exact same
    hook set instead of reaching for ``_structure_action`` with no converter.
    """
    converter = cattrs.Converter()
    converter.forbid_extra_keys = True  # fail on unknown fields
    _register_union_hooks(converter)
    converter.register_structure_hook(
        Offset | None, lambda obj, _: converter.structure(obj, Offset) if obj is not None else None
    )
    converter.register_structure_hook(
        TextMatchConfig | None, lambda obj, _: converter.structure(obj, TextMatchConfig) if obj is not None else None
    )
    _register_strict_hooks(converter)
    return converter


def _register_union_hooks(converter: cattrs.Converter) -> None:
    """Hooks for the union and custom types cattrs cannot structure on its own."""
    converter.register_structure_hook(ActionType, lambda obj, _: _structure_action(obj, converter))
    converter.register_structure_hook(
        ExistsCondition | NotExistsCondition, lambda obj, _: _structure_condition(obj, converter)
    )
    converter.register_structure_hook(
        TargetStrategyType | None, lambda obj, _: _structure_strategy(obj, converter) if obj is not None else None
    )
    converter.register_structure_hook(VariableRegistry, lambda obj, _: _structure_variables(obj))
    converter.register_structure_hook(
        VariableRegistry | None, lambda obj, _: None if obj is None else _structure_variables(obj)
    )
    converter.register_structure_hook(WaitCondition, lambda obj, _: _structure_wait_condition(obj, converter))
    converter.register_structure_hook(
        WaitCondition | None, lambda obj, _: _structure_wait_condition(obj, converter) if obj is not None else None
    )
    converter.register_structure_hook(
        SkipOptions | None, lambda obj, _: _structure_skip_options(obj, converter) if obj is not None else None
    )
    # PullAction.src
    converter.register_structure_hook(str | list[str], lambda obj, _: obj if isinstance(obj, (str, list)) else str(obj))
    # LoopAction.items: passed through as-is, resolved at runtime
    converter.register_structure_hook(str | list[Any] | None, lambda obj, _: obj)
    # TextMatchConfig.allow_missing_chars
    converter.register_structure_hook(
        bool | str | list[str] | None, lambda obj, _: obj if obj is None or isinstance(obj, (bool, str, list)) else None
    )
    # VariableCondition's numeric comparison fields
    converter.register_structure_hook(int | float | None, _structure_optional_numeric)


def _structure_variables(obj) -> VariableRegistry:
    return obj if isinstance(obj, VariableRegistry) else VariableRegistry.from_dict(obj)


def _structure_optional_numeric(obj, _):
    if obj is None or isinstance(obj, (int, float)) or not isinstance(obj, str):
        return obj
    try:
        return int(obj)
    except ValueError:
        try:
            return float(obj)
        except ValueError:
            raise ValueError(f"Cannot convert '{obj}' to numeric value") from None


def structure_action(obj) -> ActionType:
    """Structure one standalone action mapping (e.g. ``{'command': {...}}``).

    Dev mode executes single actions that never pass through ``parse_playbook``,
    so they need their own entry point into the same converter.
    """
    return _structure_action(obj, build_playbook_converter())


# YAML action key -> the attrs class it structures into. Insertion order is the
# resolution order, matching the if/elif chain this replaced. Kept as one table so
# the sibling-`description` handling below cannot silently miss an action type.
_ACTION_CLASSES = {
    'click': ClickAction,
    'drag': DragAction,
    'keyboard': KeyboardAction,
    'idle': IdleAction,
    'scroll': ScrollAction,
    'goto': GotoAction,
    'block': BlockAction,
    'test': ActionTestAction,
    'command': CommandAction,
    'screenshot': ScreenshotAction,
    'save_timestamp': SaveTimestampAction,
    'save_variable': SaveVariableAction,
    'pull': PullAction,
    'pause': PauseAction,
    'wait_until': WaitUntilAction,
    'loop': LoopAction,
    'stop': StopAction,
    'continue': ContinueAction,
    'snapshot_filesystem': SnapshotFilesystemAction,
    'pull_changed_files': PullChangedFilesAction,
}

# Step-level annotations written *beside* the action key rather than inside it:
#
#     - keyboard:
#         key: enter
#       description: 'Case Information: Next'
#       machine: client
#
# ``description:`` is the documented spelling and the one the Autopsy playbooks use
# (352 occurrences across 42 files). It used to be discarded outright: only
# ``obj['<action_key>']`` was structured, so the sibling never reached the action,
# and ``converter.forbid_extra_keys`` guards the *inner* dict so nothing flagged it.
# ``machine:`` follows the identical spelling so a multi-machine playbook can route
# each step without touching its inner mapping.
DESCRIPTION_KEY = 'description'
MACHINE_KEY = 'machine'
SIBLING_FIELDS = (DESCRIPTION_KEY, MACHINE_KEY)


def _structure_action(obj, converter):
    action_key = next((key for key in _ACTION_CLASSES if key in obj), None)
    if action_key is None:
        raise ValueError(f"Unknown action: {obj}")

    body = obj[action_key]
    if action_key == 'test' and isinstance(body, str):
        # Inline test format: - test: testname
        action = ActionTestAction(name=body)
    else:
        action = converter.structure(body, _ACTION_CLASSES[action_key])

    action = _apply_sibling_fields(obj, action_key, action)
    _cascade_machine(action)
    return action


def _apply_sibling_fields(obj, action_key, action):
    """Move step-level siblings (``description:``, ``machine:``) onto the structured action.

    Raises rather than dropping them: a description that vanishes is invisible, and
    a machine routing that vanishes silently sends a step to the wrong VM.
    """
    for sibling_key in SIBLING_FIELDS:
        if sibling_key not in obj:
            continue

        value = obj[sibling_key]
        if not attrs.has(type(action)) or sibling_key not in {field.name for field in attrs.fields(type(action))}:
            raise ValueError(
                f"action '{action_key}' has no '{sibling_key}' field, so the "
                f"{sibling_key} {value!r} written beside it cannot be stored. "
                f"Remove it, or move it inside the '{action_key}:' mapping if that "
                f"action supports one."
            )

        existing = getattr(action, sibling_key, None)
        if existing and existing != value:
            raise ValueError(
                f"action '{action_key}' has two different {sibling_key} values: "
                f"{existing!r} inside the mapping and {value!r} beside it. Keep one."
            )
        setattr(action, sibling_key, value)

    return action


def _cascade_machine(action):
    """Propagate a Block/Loop's ``machine:`` onto children that don't set their own.

    Runs after ``_apply_sibling_fields`` so the block/loop's own ``machine:``
    (whether written beside the ``block:``/``loop:`` key or inside it) is already
    resolved. Recurses so a chain of nested blocks/loops inherits transitively.
    """
    if not isinstance(action, (BlockAction, LoopAction)) or action.machine is None:
        return

    for child in action.actions:
        if getattr(child, 'machine', None) is None:
            child.machine = action.machine
        _cascade_machine(child)


def _structure_condition(obj, converter):
    if 'exists' in obj:
        return converter.structure(obj['exists'], ExistsCondition)
    if 'not_exists' in obj:
        return converter.structure(obj['not_exists'], NotExistsCondition)
    raise ValueError(f"Unknown condition: {obj}")


_STRATEGY_CLASSES = {
    cls.__name__: cls
    for cls in (
        SweepStrategy,
        BestConfidenceStrategy,
        ClosestToStrategy,
        TopLeftStrategy,
        TopRightStrategy,
        BottomLeftStrategy,
        BottomRightStrategy,
        LargestStrategy,
        SmallestStrategy,
    )
}


def _structure_strategy(obj, converter):
    name = next((key for key in _STRATEGY_CLASSES if key in obj), None)
    if name is None:
        raise ValueError(f"Unknown strategy: {obj}")
    return converter.structure(obj[name], _STRATEGY_CLASSES[name])


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


# Classes whose YAML mapping is checked for unknown fields before structuring.
_STRICT_CLASSES = (
    Target,
    Settings,
    ClickAction,
    DragAction,
    KeyboardAction,
    IdleAction,
    ScrollAction,
    GotoAction,
    ActionTestAction,
    CommandAction,
    CaptureSpec,
    ScreenshotAction,
    BlockAction,
    SaveTimestampAction,
    SaveVariableAction,
    PullAction,
    PauseAction,
    WaitUntilAction,
    LoopAction,
    StopAction,
    ContinueAction,
    VariableCondition,
    WaitCondition,
    ExistsCondition,
    NotExistsCondition,
    *_STRATEGY_CLASSES.values(),
    Playbook,
    SnapshotFilesystemAction,
    PullChangedFilesAction,
    PixelChangeConstraint,
    SkipOptions,
    Offset,
    TextMatchConfig,
    MachineSpec,
)


def _register_strict_hooks(converter):
    """Register hooks that reject unknown fields, then structure the class normally.

    They structure through a second converter with the same union hooks: calling
    ``converter`` itself would re-enter the strict hook.
    """
    inner = cattrs.Converter()
    _register_union_hooks(inner)

    def strict_hook_for(cls):
        expected_fields = {field.name for field in attrs.fields(cls)}

        def strict_structure_hook(obj, _):
            if isinstance(obj, dict):
                extra_fields = set(obj.keys()) - expected_fields
                if extra_fields:
                    raise ValueError(
                        f"Unexpected field(s) in {cls.__name__}: {', '.join(sorted(extra_fields))}. "
                        f"Expected fields: {', '.join(sorted(expected_fields))}"
                    )
            return inner.structure(obj, cls)

        return strict_structure_hook

    for cls in _STRICT_CLASSES:
        converter.register_structure_hook(cls, strict_hook_for(cls))

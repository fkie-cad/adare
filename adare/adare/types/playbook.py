from __future__ import annotations
import attrs
from typing import List, Optional, Union
import yaml
import cattrs
from pathlib import Path

@attrs.define
class Settings:
    idle: float

@attrs.define
class Target:
    image: Optional[str] = None
    text: Optional[str] = None
    position: Optional[List[int]] = None

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
    keys: Optional[str] = None
    combination: Optional[List[str]] = None
    when: Optional[List[Union['ExistsCondition', 'NotExistsCondition']]] = None
    description: str = ''

@attrs.define
class ClickAction:
    target: Target
    description: str = ''

@attrs.define
class RightClickAction:
    target: Target
    description: str = ''

@attrs.define
class DoubleClickAction:
    target: Target
    description: str = ''

@attrs.define
class DragAction:
    source: Target
    destination: Target
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
    command: str
    description: str = ''
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
class ActionResult:
    success: bool
    message: str = ''
    data: Optional[dict] = None

@attrs.define
class BlockAction:
    actions: List[ActionType]  # Remove quotes
    description: str = ''
    when: Optional[List[Union['ExistsCondition', 'NotExistsCondition']]] = None

# Now define ActionType after all classes
ActionType = Union[
    ClickAction, RightClickAction, DoubleClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction, ActionTestAction, 
    CommandAction, ScreenshotAction, BlockAction
]

@attrs.define
class Config:
    settings: Settings
    actions: List[ActionType]

def parse_config(yaml_path: Union[str, Path]) -> Config:  # Accept Path or str
    yaml_path = Path(yaml_path)  # Ensure it's a Path object
    with yaml_path.open('r') as f:
        data = yaml.safe_load(f)
    converter = cattrs.Converter()
    # Register structure hooks for Union types if needed
    converter.register_structure_hook(
        ActionType,
        lambda obj, _: _structure_action(obj, converter)
    )
    converter.register_structure_hook(
        Union[ExistsCondition, NotExistsCondition],
        lambda obj, _: _structure_condition(obj, converter)
    )
    return converter.structure(data, Config)

def _structure_action(obj, converter):
    if 'click' in obj:
        return converter.structure(obj['click'], ClickAction)
    if 'right_click' in obj:
        return converter.structure(obj['right_click'], RightClickAction)
    if 'double_click' in obj:
        return converter.structure(obj['double_click'], DoubleClickAction)
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
        return converter.structure(obj['test'], ActionTestAction)
    if 'command' in obj:
        return converter.structure(obj['command'], CommandAction)
    if 'screenshot' in obj:
        return converter.structure(obj['screenshot'], ScreenshotAction)
    raise ValueError(f"Unknown action: {obj}")

def _structure_condition(obj, converter):
    if 'exists' in obj:
        return converter.structure(obj['exists'], ExistsCondition)
    if 'not_exists' in obj:
        return converter.structure(obj['not_exists'], NotExistsCondition)
    raise ValueError(f"Unknown condition: {obj}")
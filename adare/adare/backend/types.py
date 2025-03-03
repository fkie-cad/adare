import attrs
from typing import Callable

@attrs.define
class Step:
    label: str
    description: str
    thread: bool
    func: Callable
    repeatable: bool = attrs.field(default=False)
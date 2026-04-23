from collections.abc import Callable

import attrs


@attrs.define
class Step:
    label: str
    description: str
    thread: bool
    func: Callable
    repeatable: bool = attrs.field(default=False)

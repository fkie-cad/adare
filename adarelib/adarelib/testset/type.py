# external imports
# configure logging
import logging

import attrs

# internal imports
from adarelib.common.variables import VariableRegistry

log = logging.getLogger(__name__)


@attrs.define
class Test:
    name: str
    function: str
    description: str = ''
    parameter: dict = {}
    variables: VariableRegistry | None = None
    expect_to_fail: bool = False
    timeout: float = 120.0  # Default 2 minutes (conservative with testfunction caching)
    # Names of other tests that must have passed before this one for its result to count
    # (proof outside the UI, e.g. "the file existed before it was deleted"); else INCONCLUSIVE
    controls: list = attrs.Factory(list)


@attrs.define
class TestsetFile:
    name: str
    tests: list[Test]
    description: str = ''

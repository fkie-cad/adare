# external imports
import attrs
from typing import Optional

# internal imports
from adarelib.common.variables import VariableRegistry

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class Test:
    name: str
    function: str
    description: str = ''
    parameter: dict = {}
    variables: Optional[VariableRegistry] = None
    expect_to_fail: bool = False


@attrs.define
class TestsetFile:
    name: str
    tests: list[Test]
    description: str = ''

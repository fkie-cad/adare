# external imports
import attrs

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class Test:
    name: str
    function: str
    description: str = ''
    parameter: dict = {}


@attrs.define
class TestsetFile:
    name: str
    tests: list[Test]
    description: str = ''

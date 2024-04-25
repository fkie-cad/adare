# external imports
import attrs

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class Test:
    name: str
    type: str
    params: dict = {}
    description: str = ''
    depends_on: list[str] = []


@attrs.define
class Command:
    name: str
    command: str
    tool: str
    description: str = ''


@attrs.define
class TestsetFile:
    name: str
    tests: list[Test]
    commands: list[Command] = attrs.Factory(list)
    description: str = ''

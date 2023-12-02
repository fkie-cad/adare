# external imports
import attr
from typing import Union

# configure logging
import logging
log = logging.getLogger(__name__)


@attr.define
class FTest:
    name: str
    description: str
    type: str
    params: dict


@attr.define
class FToolTest:
    tool: str
    command: str
    tests: list[FTest]


@attr.define
class FTestsetFile:
    name: str
    tests: list[Union[FTest, FToolTest]]
    description: str = ''


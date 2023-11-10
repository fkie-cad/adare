# external imports
import attrs

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class TestDetail:
    name: str
    type: str
    data: str


@attrs.define
class TestDetailText(TestDetail):
    data = attrs.field(converter=str)
    type = attrs.field(default='text')


@attrs.define
class TestDetailDict(TestDetail):
    data = attrs.field(converter=str)
    type = attrs.field(default='dict')


@attrs.define
class TestDetailList(TestDetail):
    data = attrs.field(converter=str)
    type = attrs.field(default='list')



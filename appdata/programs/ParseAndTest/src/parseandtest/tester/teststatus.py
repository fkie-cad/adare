# external imports
import attrs

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class TestStatus:
    status: str


@attrs.define
class TestFailed(TestStatus):
    status = attrs.field(default='failed', init=False)


@attrs.define
class TestSuccess(TestStatus):
    status = attrs.field(default='success', init=False)


@attrs.define
class TestMissingkey(TestStatus):
    status = attrs.field(default='missing key', init=False)


@attrs.define
class TestInputError(TestStatus):
    status = attrs.field(default='input error', init=False)


@attrs.define
class TestError(TestStatus):
    status = attrs.field(default='error', init=False)
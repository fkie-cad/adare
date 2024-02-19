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
class TestMissingKey(TestStatus):
    status = attrs.field(default='missing key', init=False)


@attrs.define
class TestSyntaxError(TestStatus):
    status = attrs.field(default='syntax error', init=False)


@attrs.define
class TestError(TestStatus):
    status = attrs.field(default='error', init=False)



# external imports
import attrs
from datetime import datetime
from typing import Optional

# internal imports
from adarevm.config import TIMESTAMP_FORMAT
from adarevm.testset.teststatus import TestStatus


# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define(frozen=True)
class TestResult:
    name: str
    function: str
    function_options: dict
    function_description: str
    result: TestStatus
    details: list = attrs.field(default=attrs.Factory(list))
    description: Optional[str] = ''

    # always set timestamp on initialization
    timestamp: str = attrs.field(default=attrs.Factory(lambda: datetime.now().strftime(TIMESTAMP_FORMAT)))


@attrs.define
class TestOutcome:
    TestResultList: list = attrs.field(default=attrs.Factory(list))

    def add_test_result(self, testresult: TestResult):
        self.TestResultList.append(testresult)

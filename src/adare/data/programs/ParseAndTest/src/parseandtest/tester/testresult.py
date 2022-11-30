# external imports
import attrs
from typing import List, Optional

# internal imports
from parseandtest.tester.teststatus import TestStatus
from parseandtest.tester.testdetail import TestDetail


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
    details: List[TestDetail] = attrs.field(default=attrs.Factory(list))
    description: Optional[str] = ''


@attrs.define
class TestOutcome:
    TestResultList: list = attrs.field(default=attrs.Factory(list))

    def add_test_result(self, testresult: TestResult):
        self.TestResultList.append(testresult)

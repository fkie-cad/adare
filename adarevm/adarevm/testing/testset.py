from collections.abc import Callable
from pathlib import Path
import shutil
from typing import Awaitable

from adarelib.testset.parser import parse_testsetfile
from adarelib.testset.type import TestsetFile
from adarelib.testset.testfunction import import_basictest_subclasses, get_missing_testfunctions, structure_tests
from adarelib.constants import StatusEnum
from adarelib.event.event import TestEvent
from adarevm.core.events import EventCtxManager
from adarevm.automation.shell import execute_on_shell
from adarevm.exception import LoggedErrorException

import logging
log = logging.getLogger(__name__)


class TestsetExecutionError(LoggedErrorException):
    pass


class Testset:
    supported_tests: dict
    testsetfile: TestsetFile
    tests: dict
    log_func: Callable[[str], Awaitable[None]]
    executed_commands: list

    def __init__(self, testfunctions_directory: Path, testsetfile: Path, log_func: Callable[[str], Awaitable[None]]):
        self.supported_tests = import_basictest_subclasses(testfunctions_directory)
        self.testsetfile: TestsetFile = parse_testsetfile(testsetfile)

        if get_missing_testfunctions(
                self.testsetfile, self.supported_tests
        ):
            raise TestsetExecutionError(log, 'testset contains tests that are not supported by the testfunction collection')

        self.tests, self.structure_error_dict = structure_tests(self.testsetfile, self.supported_tests)
        if self.structure_error_dict:
            raise TestsetExecutionError(log, 'testset contains tests that are not supported by the testfunction collection')

        self.log_func = log_func

    def test(self, name: str, variables: dict):
        if name not in self.tests:
            log.error(f'test with name {name} does NOT exist')
            raise TestsetExecutionError(log, f'test with name {name} does NOT exist')
        test = self.tests[name]

        test.variables = variables
        with EventCtxManager(
                TestEvent(
                    test_name=name, status=StatusEnum.RUNNING
                ),
                self.log_func
        ) as event_ctx:
            test_result = test.test()
            event_ctx.update(
                TestEvent(
                    test_name=name, status=StatusEnum.FINISHED, result=test_result
                )
            )

    def testall(self, variables: dict):
        for test in self.tests:
            self.test(test, variables)

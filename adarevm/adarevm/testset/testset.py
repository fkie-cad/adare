from collections.abc import Callable
from pathlib import Path
import shutil
from typing import Awaitable

from adarelib.parsers import parse_testsetfile
from adarelib.types.testset import TestsetFile
from adarelib.testfunction import import_basictest_subclasses, get_missing_testfunctions, structure_tests
from adarelib.types.event import TestEvent, CommandEvent
from adarevm.event import EventCtxManager
from adarelib.config import StatusEnum
from adarevm.shell import execute_on_shell
from adarelib.exceptions import LoggedErrorException

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
        self.executed_commands = []

    def execute_command(self, command_name: str):
        available_commands = [com.name for com in self.testsetfile.commands]
        if command_name not in available_commands:
            raise TestsetExecutionError(log, f'command {command_name} is not available')
        # retrieve the command from the testsetfile
        command = next(com for com in self.testsetfile.commands if com.name == command_name)

        with EventCtxManager(
                CommandEvent(
                    name=command_name, command=command.command, status=StatusEnum.RUNNING,
                ),
                self.log_func
        ) as event_ctx:
            toolpath = command.command.split(' ')[0]
            toolpath = f'{toolpath}'
            command_path = f'{command.command}'
            if not shutil.which(toolpath):
                log.error(f'tool with path {toolpath} does NOT exist')
                event_ctx.update(
                    CommandEvent(
                        name=command_name, command=command.command, status=StatusEnum.FAILED,
                        error=f'tool with path {toolpath} does NOT exist'
                    )
                )
                raise TestsetExecutionError(log, f'tool with path {toolpath} does NOT exist')

            ret = execute_on_shell(command_path.split(" "))
            event_ctx.update(
                CommandEvent(
                    name=command_name, command=command.command, status=StatusEnum.FINISHED,
                    returncode=ret['returncode'], stdout=ret['stdout']
                )
            )
            self.executed_commands.append(command_name)

    def __check_if_command_already_executed(self, command_name: str) -> bool:
        return any(event.name == command_name for event in self.executed_commands)

    def test(self, name: str, variables: dict):
        if name not in self.tests:
            log.error(f'test with name {name} does NOT exist')
            raise TestsetExecutionError(log, f'test with name {name} does NOT exist')
        test = self.tests[name]

        test_in_testsetfile = next(t for t in self.testsetfile.tests if t.name == name)
        if test_in_testsetfile.depends_on:
            for dependency in test_in_testsetfile.depends_on:
                if not self.__check_if_command_already_executed(dependency):
                    self.execute_command(dependency)
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

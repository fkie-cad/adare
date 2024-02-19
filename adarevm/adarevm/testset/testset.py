from pathlib import Path
from subprocess import Popen, PIPE
import shutil

from adarelib.testsetfile.parser import parse_testsetfile
from adarelib.testsetfile.fileformat import TestsetFile
from adarelib.testfunction import import_basictest_subclasses, check_if_tests_exist, structure_tests

from adarevm.event import EventSystem, CommandEnd, CommandStart

import logging

log = logging.getLogger(__name__)


class TestsetExecutionError(Exception):
    pass


class Testset:
    supported_tests: dict
    testsetfile: TestsetFile
    tests: dict

    event_system: EventSystem

    def __init__(self, testfunctions_directory: Path, testsetfile: Path, event_system: EventSystem):
        self.supported_tests = import_basictest_subclasses(testfunctions_directory)
        self.testsetfile: TestsetFile = parse_testsetfile(testsetfile)

        if unsupported_testfunctions := check_if_tests_exist(
                self.testsetfile, self.supported_tests
        ):
            log.error(
                f'testset contains tests that are not supported by the testfunction collection: {unsupported_testfunctions}')
            raise TestsetExecutionError('testset contains tests that are not supported by the testfunction collection')

        self.tests, self.structure_error_dict = structure_tests(self.testsetfile, self.supported_tests)
        if self.structure_error_dict:
            log.error('testset contains tests that are not supported by the testfunction collection')
            raise TestsetExecutionError('testset contains tests that are not supported by the testfunction collection')

        self.event_system = event_system

    def execute_command(self, command_name: str):
        available_commands = [com.name for com in self.testsetfile.commands]
        if command_name not in available_commands:
            log.error(f'command {command_name} is not available')
            raise TestsetExecutionError(f'command {command_name} is not available')
        self.event_system.log(
            CommandStart(
                command_name=command_name
            )
        )
        # retrieve the command from the testsetfile
        command = next(com for com in self.testsetfile.commands if com.name == command_name)

        toolpath = command.command.split(' ')[0]
        if not shutil.which(toolpath):
            log.error(f'tool with path {toolpath} does NOT exist')
            toolpath = f'./{toolpath}'
            self.command = f'./{command.command}'
            if not shutil.which(toolpath):
                log.error(f'tool with path {toolpath} does NOT exist')
                raise TestsetExecutionError(f'tool with path {toolpath} does NOT exist')

        proc = Popen(self.command, stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()

        stdout = stdout.decode("utf-8")
        stdout = stdout.replace("\r", "")
        stdout = stdout.split("\n")
        for line in stdout:
            log.debug(line)
        stderr = stderr.decode("utf-8")
        stderr = stderr.replace("\r", "")
        stderr = stderr.split("\n")
        ret = {
            'returncode': proc.returncode,
            'stdout': stdout,
            'stderr': stderr
        }
        log.debug(
            f"'{self.command}' exited with return code: " + str(ret['returncode'])
        )
        if ret['returncode'] != 0:
            log.error(
                f"{self.command} exited with an error (return code "
                + str(ret['returncode'])
                + ")"
            )
            for line in stderr:
                log.error(line)
            raise TestsetExecutionError(f"{self.command} exited with an error (return code " + str(ret['returncode']) + ")")
        else:
            log.info(f'({self.command})  exited successfully.')
        self.event_system.log(
            CommandEnd(
                command_name=command_name,
            )
        )

    def __check_if_command_already_executed(self, command_name: str):
        return command_name in [e.name for e in self.event_system.data.events]

    def test(self, name: str):
        if name not in self.tests:
            log.error(f'test with name {name} does NOT exist')
            raise TestsetExecutionError(f'test with name {name} does NOT exist')
        test = self.tests[name]
        test_in_testsetfile = next(t for t in self.testsetfile.tests if t.name == name)
        if test_in_testsetfile.depends_on:
            for dependency in test_in_testsetfile.depends_on:
                if not self.__check_if_command_already_executed(dependency):
                    self.execute_command(dependency)
        events = test.test()
        for event in events:
            self.event_system.log(event)
        self.event_system.save()

    def testall(self):
        for test in self.tests:
            self.test(test)

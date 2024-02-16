# external imports
import shutil
from typing import Optional
import attrs
import cattrs
from subprocess import Popen, PIPE


# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class TestContainer:
    tests: list
    tool: Optional[str] = None
    command: Optional[str] = None

    def execute_command(self):
        if not self.command:
            return
        toolpath = self.command.split(' ')[0]
        if not shutil.which(toolpath):
            log.error(f'tool with path {toolpath} does NOT exist')
            toolpath = f'./{toolpath}'
            self.command = f'./{self.command}'
            if not shutil.which(toolpath):
                log.error(f'tool with path {toolpath} does NOT exist')
                return

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
        log.debug("'" + self.command + "' exited with return code: " + str(ret['returncode']))
        if ret['returncode'] != 0:
            log.error(self.command + " exited with an error (return code " + str(ret['returncode']) + ")")
            for line in stderr:
                log.error(line)
        else:
            log.info(f'({self.command})  exited successfully.')
        return

    def test(self, variables, supported_classes) -> (list, list):
        self.execute_command()
        results = []
        unsupported_types = []
        for test in self.tests:
            if test['type'] in supported_classes.keys():
                testclass = supported_classes[test['type']]
            else:
                unsupported_types.append(test['type'])
                continue
            try:
                testclass_instance = cattrs.structure(test, testclass)
            except cattrs.errors.ClassValidationError as e:
                if 'name' in test.keys():
                    log.error(f'an test ({test["name"]}) has missing/wrong parameters in the input file -> see exception below')
                else:
                    log.error(f'an test has missing/wrong parameters in the input file -> see exception below')
                log.error(e, exc_info=True)
                continue
            testresult = testclass_instance.test(variables)
            results.append(testresult)
        return unsupported_types, results

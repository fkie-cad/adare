# external imports
from pathlib import Path

# internal imports
from adare.config.configdirectory import TEMPLATES_DIR
from adare.backend.testfunction.exceptions import TestfunctionDirectoryCreationError, TestfunctionCreationError

# configure logging
import logging
log = logging.getLogger(__name__)


class TestfunctionDirectory:
    path: Path

    def __init__(self, project: Path):
        self.path = project / 'testfunctions'
        if not self.path.exists():
            try:
                self.path.mkdir()
            except OSError as e:
                raise TestfunctionDirectoryCreationError(
                    log,
                    message=f'Error creating testfunction directory: {e.strerror}',
                ) from e

    def __testfunction_exists(self, testfunction: str):
        return (self.path / testfunction).exists()

    def create_testfunction(self, testfunction: str):
        testfunction_path = self.path / testfunction
        testfunction_template = TEMPLATES_DIR / 'testfunction' / 'testfunction.py'
        if self.__testfunction_exists(testfunction):
            raise TestfunctionCreationError(
                log,
                message=f'Testfunction {testfunction} already exists',
            )

        try:
            with open(testfunction_path, 'w') as f:
                f.write(testfunction_template.read_text())
        except OSError as e:
            raise TestfunctionCreationError(
                log,
                message=f'Error creating testfunction file: {e.strerror}',
            ) from e
        return testfunction_path

    def remove_testfunction(self, testfunction: str):
        testfunction_path = self.path / testfunction
        if not self.__testfunction_exists(testfunction):
            raise TestfunctionCreationError(
                log,
                message=f'Testfunction {testfunction} does not exist',
            )
        try:
            testfunction_path.unlink()
        except OSError as e:
            raise TestfunctionCreationError(
                log,
                message=f'Error removing testfunction file: {e.strerror}',
            ) from e
        return testfunction_path

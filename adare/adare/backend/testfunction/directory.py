# external imports
from pathlib import Path
import shutil

# internal imports
from adare.config.configdirectory import TEMPLATES_DIR
from adare.backend.testfunction.exceptions import TestfunctionDirectoryCreationError, TestfunctionCreationError, \
    TestfunctionMissingFileError

# configure logging
import logging

log = logging.getLogger(__name__)


class TestfunctionDirectory:
    path: Path
    requirements: Path
    pythonfile: Path

    def __init__(self, project: Path, name: str):
        self.path = project / 'testfunctions' / name
        self.requirements = self.path / 'requirements.txt'
        self.pythonfile = self.path / f'{name}.py'

    def testfunction_exists(self):
        return self.pythonfile.exists()

    def create_testfunction(self):
        testfunction_template = TEMPLATES_DIR / 'testfunction' / 'testfunction.py'
        if self.testfunction_exists():
            raise TestfunctionCreationError(
                log,
                message=f'Testfunction {self.path.name} already exists',
            )

        try:
            with open(self.pythonfile, 'w') as f:
                f.write(testfunction_template.read_text())
        except OSError as e:
            raise TestfunctionCreationError(
                log,
                message=f'Error creating testfunction file: {e.strerror}',
            ) from e

    def remove_testfunction(self):
        if not self.testfunction_exists():
            raise TestfunctionCreationError(
                log,
                message=f'Testfunction {self.path.name} does not exist',
            )
        try:
            shutil.rmtree(self.path)
        except OSError as e:
            raise TestfunctionCreationError(
                log,
                message=f'Error removing testfunction file: {e.strerror}',
            ) from e

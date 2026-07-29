# external imports
# configure logging
import logging
import shutil
from pathlib import Path

from adare.backend.testfunction.exceptions import (
    TestfunctionCreationError,
)

# internal imports
from adare.config.configdirectory import TEMPLATES_DIR

log = logging.getLogger(__name__)


# Fallback skeleton used when the shipped template is absent (e.g. running from
# a source checkout where appdata/ has not been installed). Mirrors the docs
# quickstart so `adare test create` never hard-depends on install state.
_INLINE_SKELETON = '''\
# ADARE testfunction collection (scaffolded by `adare test create`).
#
# Rules: the .py file must be named exactly like its directory, every function's
# first parameter must be `ctx`, and every other parameter must be annotated.
# Reference a test from a playbook as `<collection>.<name>`.

from pathlib import Path

from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

import logging
log = logging.getLogger(__name__)


@testfunction(
    name='file_contains_word',
    description='tests if a file contains the given word',
    category=HostModeCategory.FILE_BASED,
)
def file_contains_word(ctx, dst: str, word: str, case_sensitive: bool = True):
    dst_path, status = ctx.resolve_globfilepath(dst)
    ctx.error_if(not dst_path, f'File {dst} could not be resolved ({status})')

    with open(dst_path, encoding='utf-8') as f:
        content = f.read()

    search_word = word
    if not case_sensitive:
        content = content.lower()
        search_word = word.lower()

    ctx.fail_if(search_word not in content, f'Word "{word}" not found in {dst}')
    return f'Word "{word}" found in {dst}'
'''

_INLINE_REQUIREMENTS = (
    '# Python dependencies for this testfunction collection (one per line).\n'
    '# Installed into ADARE\'s interpreter when the collection is loaded.\n'
)


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
        if self.testfunction_exists():
            raise TestfunctionCreationError(
                log,
                message=f'Testfunction {self.path.name} already exists',
            )

        # Resolve template content, falling back to an inline skeleton when the
        # shipped template is missing so `create` works from a source checkout.
        template_dir = TEMPLATES_DIR / 'testfunction'
        py_template = template_dir / 'testfunction.py'
        req_template = template_dir / 'requirements.txt'

        try:
            python_content = py_template.read_text() if py_template.is_file() else _INLINE_SKELETON
        except OSError as e:
            log.warning(f'Could not read testfunction template ({e}); using inline skeleton')
            python_content = _INLINE_SKELETON

        try:
            requirements_content = req_template.read_text() if req_template.is_file() else _INLINE_REQUIREMENTS
        except OSError as e:
            log.warning(f'Could not read requirements template ({e}); using inline default')
            requirements_content = _INLINE_REQUIREMENTS

        try:
            # create_testfunction never mkdir'd its target dir before, so the
            # open() below raised FileNotFoundError for a fresh collection.
            self.path.mkdir(parents=True, exist_ok=True)
            self.pythonfile.write_text(python_content)
            # The `create` success message tells users to edit requirements.txt,
            # so it must actually exist after scaffolding.
            self.requirements.write_text(requirements_content)
        except OSError as e:
            raise TestfunctionCreationError(
                log,
                message=f'Error creating testfunction files: {e.strerror}',
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

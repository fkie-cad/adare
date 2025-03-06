from adarevm.action.experiment import Experiment, KEYMAP
from pathlib import Path
from typing import Callable, Awaitable
from adarevm.testset.testset import Testset

import logging

log = logging.getLogger(__name__)


class {{ name }}(Experiment):
    description = ''

    def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset,
                 log_func: Callable[[str], Awaitable[None]]):
        """
            initialization function which in most cases should not be changed (except there is a need to use a different display controller or computer vision backend for guibot)
        """
        super().__init__(img_folder, tessdata_folder, testset, log_func)

    def prepare(self) -> tuple[bool, str]:
        """
            this function can be used to execute some commands before the clicks happen (e.g. creating a file)
        """
        pass

    def run(self) -> tuple[bool, str]:
        """
            this function should be used to execute the gui automation steps
        """
        log.info(f'experiment {self.name} started')

        pass

        log.info(f'experiment {self.name} done')

        return True, ''
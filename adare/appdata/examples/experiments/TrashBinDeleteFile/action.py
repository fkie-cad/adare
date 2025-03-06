from adarevm.action.experiment import Experiment, KEYMAP
from pathlib import Path
from typing import Callable, Awaitable
from adarevm.testset.testset import Testset

import logging

log = logging.getLogger(__name__)


class TrashBinDeleteFile(Experiment):
    description = 'delete file and check trash bin'

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
        # create file C:/Users/vagrant/Documents/testfile
        with open('C:/Users/vagrant/Documents/testfile', 'w') as f:
            f.write('test')
        return True, ''

    def run(self) -> tuple[bool, str]:
        """
            this function should be used to execute the gui automation steps
        """
        log.info(f'experiment {self.name} started')

        # place the code to execute some stuff here
        match = self.find('files.png')
        if match:
            self.click(match[0])
            self.idle(2)
        else:
            error_name = 'find failed'
            error_msg = 'could not find files.png'
            self.error(error_name, error_msg)
            return False, f'{error_name}: {error_msg}'

        match = self.find('documents.png')
        if match:
            self.click(match[0])
            self.idle(2)
        else:
            error_name = 'find failed'
            error_msg = 'could not find documents.png'
            self.error(error_name, error_msg)
            return False, f'{error_name}: {error_msg}'

        match = self.find('testfile.png')
        if match:
            self.click(match[0])
            self.idle(2)
        else:
            error_name = 'find failed'
            error_msg = 'could not find testfile.png'
            self.error(error_name, error_msg)
            return False, ''

        self.press_keys([KEYMAP.DELETE])
        self.save_time('DELETIONDATE')

        self.run_test('existencefile')
        self.run_test('deletedfileInfo')

        log.info(f'experiment {self.name} done')

        return True, ''
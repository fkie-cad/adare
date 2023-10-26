from pathlib import Path
import sys

from guiautomation.Experiment.Experiment import Experiment
from guiautomation.run import run
from guibot.guibot import GuiBot

import logging
log = logging.getLogger(__name__)


class deletefile(Experiment):
    description = "Delete file from home folder to Trash Bin (Ubuntu)"
    guibot: GuiBot = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def prepare(self):
        file = "C:/Users/vagrant/Documents/testfile"
        log.info(f'create the file {file}.')
        with open(file, mode="w") as f:
            f.write("GEHEIM!")
        log.info(f'file {file} created.')

    def run(self):
        guibot = self.guibot

        log.info(f'experiment {type(self).__name__} started')

        match = self.find('files.png')
        if match:
            guibot.click(match[0])
            guibot.idle(5)
        else:
            log.error('files.png button does not exist')
            return 'failed'

        match = self.find_text('Documents')
        if match:
            guibot.click(match[0])
            guibot.idle(5)
        else:
            log.error('documents text does not exist')
            return 'failed'

        match = self.find_text('testfile')
        if match:
            guibot.click(match[0])
            guibot.idle(5)
            guibot.press_keys(guibot.dc_backend.keymap.DELETE)
            self.save_time("DELETIONDATE")
        else:
            log.error('testfile text cant be found')
            return 'failed'

        log.info(f'experiment {type(self).__name__} done')
        return self.status


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('missing file for config path')
        exit(-1)
    run(deletefile, config_file=Path(sys.argv[1]))

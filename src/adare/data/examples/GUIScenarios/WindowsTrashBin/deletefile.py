from guiautomation.Scenario.Scenario import Scenario
from guibot.guibot import GuiBot
from pathlib import Path

import guiautomation.config as config
import logging

log = logging.getLogger(__name__)


class deletefile(Scenario):
    description = "Delete file from home folder to Trash Bin (Ubuntu)"
    guibot = None

    def __init__(self):
        super().__init__()

    def prepare(self):
        file = "C:/Users/vagrant/Documents/testfile"
        log.info(f'create the file {file}.')
        with open(file, mode="w") as f:
            f.write("GEHEIM!")
        log.info(f'file {file} created.')

    def run(self):
        guibot = self.guibot

        log.info(f'scenario {type(self).__name__} started')

        if guibot.exists('files.png'):
            guibot.click('files.png').idle(5)
        else:
            log.error('files.png button does not exist')
            return 'failed'
        if guibot.exists('documents.png'):
            guibot.click('documents.png').idle(5)
        else:
            log.error('documents.png button does not exist')
            return 'failed'
        if guibot.exists('testfile.png'):
            guibot.click('testfile.png').idle(5)
            guibot.press_keys(guibot.dc_backend.keymap.DELETE)
            self.save_time("DELETIONDATE")
        else:
            log.error('testfile.png icon cant be found')
            return 'failed'

        log.info(f'scenario {type(self).__name__} done')
        return self.status

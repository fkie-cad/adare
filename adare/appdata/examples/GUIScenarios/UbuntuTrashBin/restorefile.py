from guiautomation.experiment.experiment import experiment
from guibot.guibot import GuiBot
from pathlib import Path

import guiautomation.config as config
import logging

log = logging.getLogger(__name__)


class restorefile(experiment):
    description = "Restore file (testfile) from Trash Bin to home folder (Ubuntu)"
    guibot = None

    def __init__(self):
        super().__init__()
        self.guibot = GuiBot()
        log.info(f'GuiBot Object created with display controller(dc) backend {str(type(self.guibot.dc_backend).__name__)} and  computer vision (cv) backend  {str(type(self.guibot.cv_backend).__name__)}')
        self.guibot.add_path(self.img_folder)

    def prepare(self):
        file = "/home/vagrant/testfile"
        log.info(f'create the file {file}.')
        with open(file, mode="w") as f:
            f.write("GEHEIM!")
        log.info(f'file {file}  created.')

        guibot = self.guibot
        if guibot.exists('files_taskbar.png'):
            guibot.click('files_taskbar.png').idle(5)
        else:
            log.error('files_taskbar.png does not exist')
            return -1
        if guibot.exists('testfile.png'):
            guibot.click('testfile.png').idle(5)
            guibot.press_keys(guibot.dc_backend.keymap.DELETE)
        else:
            log.error('testfile.png icon cant be found')
            return -1

    def run(self):
        guibot = self.guibot

        log.info(f'experiment {type(self).__name__} started')

        if guibot.exists('trashbin_files.png'):
            guibot.click('trashbin_files.png').idle(5)
        else:
            log.error('trashbin_files.png does not exist')
            return -1

        if guibot.exists('testfile.png'):
            guibot.click('testfile.png').idle(5)
        else:
            log.error('testfile.png icon cant be found')
            return -1
        if guibot.exists('restoretrashbin.png'):
            guibot.click('restoretrashbin.png').idle(5)
        else:
            log.error('restoretrashbin.png does not exist')
            return -1

        log.info(f'experiment {type(self).__name__} done')

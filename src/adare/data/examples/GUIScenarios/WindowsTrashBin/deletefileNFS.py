from guiautomation.Scenario.Scenario import Scenario
from guibot.guibot import GuiBot
from pathlib import Path

import guiautomation.config as config
import logging

log = logging.getLogger(__name__)


class deletefileNFS(Scenario):
    description = "Delete file from home folder to Trash Bin (Ubuntu)"
    guibot = None

    def __init__(self):
        super().__init__()
        self.guibot = GuiBot()
        log.info(f'GuiBot Object created with display controller(dc) backend {str(type(self.guibot.dc_backend).__name__)} and  computer vision (cv) backend  {str(type(self.guibot.cv_backend).__name__)}')
        self.guibot.add_path(self.img_folder)

    def prepare(self):
        file = "X:/testfile"
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
            return -1
        if guibot.exists('mypc.png'):
            guibot.click('mypc.png').idle(5)
        else:
            log.error('mypc.png button does not exist')
            return -1
        if guibot.exists('networkshare.png'):
            guibot.double_click('networkshare.png').idle(5)
        else:
            log.error('networkshare.png button does not exist')
            return -1
        if guibot.exists('testfile.png'):
            guibot.click('testfile.png').idle(5)
            guibot.press_keys(guibot.dc_backend.keymap.DELETE).idle(5)
            guibot.press_keys(guibot.dc_backend.keymap.ENTER)
            self.save_time("DELETIONDATE")
        else:
            log.error('testfile.png icon cant be found')
            return -1

        log.info(f'scenario {type(self).__name__} done')

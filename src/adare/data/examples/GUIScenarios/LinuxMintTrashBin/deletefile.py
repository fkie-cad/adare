from guiautomation.Scenario.Scenario import Scenario
from guibot.guibot import GuiBot
from pathlib import Path

import guiautomation.config as config
import logging

log = logging.getLogger(__name__)


class deletefile(Scenario):
    description = "Delete file from home folder to Trash Bin (Linux Mint 20.03)"
    guibot = None

    def __init__(self):
        super().__init__()
        self.guibot = GuiBot()
        log.info("GuiBot Object created with display controller(dc) backend " + str(
            type(self.guibot.dc_backend).__name__) + " and  computer vision (cv) backend " + str(
            type(self.guibot.cv_backend).__name__))
        self.guibot.add_path(self.img_folder)

    def prepare(self):
        file = "/home/vagrant/testfile"
        log.info(f'create the file {file}.')
        f = open(file, mode="w")
        f.write("GEHEIM!")
        f.close()
        log.info(f'file {file}  created.')

    def run(self):
        guibot = self.guibot

        log.info(f'scenario {type(self).__name__} started')

        if guibot.exists('files_in_taskbar.png'):
            guibot.click('files_in_taskbar.png').idle(5)
        else:
            log.error('files_in_taskbar.png button does not exist')
            return -1
        if guibot.exists('testfile.png'):
            guibot.click('testfile.png').idle(5)
            guibot.press_keys(guibot.dc_backend.keymap.DELETE)
            self.save_time("checkdeletiontimestamp")
        else:
            log.error('testfile.png icon cant be found')
            return -1

        log.info(f'scenario {type(self).__name__} done')

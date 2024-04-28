from adarevm.action.experiment import Experiment
from guibot.guibot import GuiBot
from pathlib import Path

import logging
log = logging.getLogger(__name__)


class Deletetest(Experiment):
    description = 'place the description of your experiment here'

    def __init__(self, img_folder: Path, tessdata_folder: Path, testset ,eventsystem):
        """
            initialization function which in most cases should not be changed (except there is a need to use a different display controller or computer vision backend for guibot)
        """
        super().__init__(img_folder, tessdata_folder, testset , eventsystem)

    def prepare(self):
        """
            this function can be used to execute some commands before the clicks happen (e.g. creating a file)
        """
        # create file C:/Users/vagrant/Documents/testfile
        with open('C:/Users/vagrant/Documents/testfile', 'w') as f:
            f.write('test')

    def run(self):
        """
            this function should be used to execute the gui automation steps
        """
        log.info(f'experiment {type(self).__name__} started')

        # place the code to execute some stuff here
        match = self.find('files.png')
        if match:
            self.click(match[0])
            self.idle(2)
        else:
            self.error('find failed','could not find files.png')
            return
        
        self.run_test('existencefile')


        log.info(f'experiment {type(self).__name__} done')

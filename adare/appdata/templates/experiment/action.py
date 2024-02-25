from adarevm.action.experiment import Experiment
from guibot.guibot import GuiBot

import logging
log = logging.getLogger(__name__)


class {{ name }}(Experiment):
    description = 'place the description of your experiment here'

    def __init__(self):
        """
            initialization function which in most cases should not be changed (except there is a need to use a different display controller or computer vision backend for guibot)
        """
        super().__init__()

    def prepare(self):
        """
            this function can be used to execute some commands before the clicks happen (e.g. creating a file)
        """
        pass

    def run(self):
        """
            this function should be used to execute the gui automation steps
        """
        log.info(f'experiment {type(self).__name__} started')

        # place the code to execute some stuff here


        log.info(f'experiment {type(self).__name__} done')

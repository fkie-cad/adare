from adarelib.types.ws import EXPERIMENT, DONE
from adarevm.msghandler.strategies.base_handler import MessageStrategy
from adarevm.config import SHARED_BASE_DIR
from adarevm.testset.testset import Testset
from adarevm.action.experiment import Experiment
from adarelib.helperfunctions.module import import_module_from_pyfile
from pathlib import Path
import traceback
from typing import Type, Callable, Awaitable


import logging
log = logging.getLogger(__name__)


def _load_action_from_file(experiment_file: Path) -> Type[Experiment] or None:
    module = import_module_from_pyfile(experiment_file)
    # get child class of Experiment
    for name, obj in module.__dict__.items():
        if isinstance(obj, type) and issubclass(obj, Experiment) and obj != Experiment:
            return obj

class ExperimentHandler(MessageStrategy):

    def handle(self, command_type, command: EXPERIMENT, send_callback: Callable[[str], Awaitable[None]]):
        shared_base_dir = Path(SHARED_BASE_DIR)
        action_file = shared_base_dir/'experiment'/'action.py'
        testset_file = shared_base_dir/'experiment'/'testset.yml'
        img_dir = shared_base_dir/'experiment'/'img'
        tessdata = shared_base_dir/'tessdata'
        testfunction_dir = shared_base_dir/'testfunctions'

        testset = Testset(
            testfunctions_directory=testfunction_dir,
            testsetfile=testset_file,
            log_func=send_callback,
        )

        experiment_class = _load_action_from_file(action_file)

        experiment = experiment_class(
            tessdata_folder=tessdata,
            img_folder=img_dir,
            testset=testset,
            log_func=send_callback,
        )
        try:
            success, error_msg = experiment.prepare()
            log.debug(f'preparation of experiment {experiment.__class__} done')

            success, error_msg = experiment.run()
            log.debug(f'experiment {experiment.__class__} finished')
            if success:
                send_callback(DONE(name='experiment').encode())
            else:
                send_callback(DONE(name='experiment', error=True, out_msg='', err_msg=error_msg).encode())
        except Exception as e:
            error_str = traceback.format_exc()
            log.error(f'Error in experiment {experiment.__class__}:')
            log.error(e, exc_info=True)
            done = DONE(name='experiment', error=True, out_msg='', err_msg=error_str)
            send_callback(done.encode())


# external imports
from pathlib import Path
from typing import Type
import argparse
import cattrs
import sys

# internal imports
from adarelib.helperfunctions.yaml import yaml_to_dict
from adarelib.experimentconfig import ExperimentConfig
from adarelib.event import EventSystem
from adarelib.types.event import ErrorEvent
from adarevm.testset.testset import Testset
from adarevm.action.experiment import Experiment
from adarelib.helperfunctions.module import import_module_from_pyfile
from adarelib.exceptions import LoggedErrorException
from adarelib.breakpoint import BP_BOX_BEFORE_ACTION, BP_BOX_BEFORE_BOX_STOP

# logging configuration
from adarelib.logger import logger
import logging as log


def setup_logging(arguments, commandline, logfile: Path):
    logger.setup_logger(logfile=logfile)
    log.info(f'COMMAND: {" ".join(commandline)}')
    # # set logging level of guibot.finder to ERROR
    # guibot_finder_logger = logging.getLogger('guibot.finder')
    # guibot_finder_logger.setLevel(logging.ERROR)


def _load_action_from_file(experiment_file: Path) -> Type[Experiment]:
    module = import_module_from_pyfile(experiment_file)
    # get child class of Experiment
    for name, obj in module.__dict__.items():
        if isinstance(obj, type) and issubclass(obj, Experiment) and obj != Experiment:
            return obj


def run_action(config, event_system):
    testset = Testset(
        testfunctions_directory=Path(config.testfunction_directory),
        testsetfile=Path(config.testset),
        event_system=event_system
    )

    event_system.stage = 'init experiment'
    # get experiment class
    ExperimentClass = _load_action_from_file(Path(config.action))
    experiment = ExperimentClass(
        tessdata_folder=Path(config.tessdata).absolute(),
        img_folder=Path(config.img),
        testset=testset,
        eventsystem=event_system,
    )

    event_system.stage = 'prepare experiment'
    experiment.prepare()
    log.debug(f'preparation of experiment {experiment.__class__} done')
    event_system.stage = 'run experiment'
    experiment.run()
    log.debug(f'experiment {experiment.__class__} finished')


def main():
    parser = argparse.ArgumentParser(description='run an experiment')
    parser.add_argument('config', type=Path, help='path to the config file')
    args = parser.parse_args()

    config_file = args.config
    # parse yaml config file
    config_dict = yaml_to_dict(config_file)
    try:
        config: ExperimentConfig = cattrs.structure(config_dict, ExperimentConfig)
    except cattrs.ClassValidationError as e:
        print(f'config file {config_file} does not contain all required attributes')
        print(e)
        sys.exit(1)

    setup_logging(args, sys.argv, Path(config.logfile))

    event_system = EventSystem(
            path=Path(config.eventfile),
            experiment_name=config.experiment,
    )
    event_system.stage = 'init testset'
    try:
        BP_BOX_BEFORE_ACTION.trigger_on_guest_if_in_breakpoints(config.breakpoints, Path(config.breakpoint_directory))
        run_action(config, event_system)
    except LoggedErrorException as e:
        event_system.log(
            ErrorEvent(
                error_name=e.error_name,
                error=e.message,
            )
        )
    finally:
        BP_BOX_BEFORE_BOX_STOP.trigger_on_guest_if_in_breakpoints(config.breakpoints, Path(config.breakpoint_directory))
    sys.exit(0)

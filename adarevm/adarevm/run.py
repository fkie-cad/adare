# external imports
import logging
from pathlib import Path
from typing import Type
import argparse
import cattrs
import sys

# internal imports
from adarelib.helperfunctions.yaml import yaml_to_dict
from adarelib.experimentconfig import ExperimentConfig
from adarevm.event import EventSystem
from adarevm.testset.testset import Testset
from adarevm.action.experiment import Experiment
from adarelib.helperfunctions.module import import_module_from_pyfile

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

    testset = Testset(
        testfunctions_directory=Path(config.testfunction_directory),
        testsetfile=Path(config.testset),
        event_system=event_system
    )
    
    # get experiment class
    ExperimentClass = _load_action_from_file(Path(config.action))
    experiment = ExperimentClass(
        tessdata_folder=Path(config.tessdata).absolute(),
        img_folder=Path(config.img),
        testset=testset,
        eventsystem=event_system,
    )

    experiment.prepare()
    log.debug(f'preparation of experiment {experiment.__class__} done')
    experiment.run()
    log.debug(f'experiment {experiment.__class__} finished')






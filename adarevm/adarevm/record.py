from pathlib import Path

from mouseinfo import screenshot

from adarevm.record.recorder import Recorder
import argparse
import sys
from adarelib.helperfunctions.yaml import yaml_to_dict
from adarelib.experimentconfig import RecordConfig
import cattrs

from adarelib.logger import logger
import logging as log


def setup_logging(commandline, logfile: Path):
    logger.setup_logger(logfile=logfile)
    log.info(f'COMMAND: {" ".join(commandline)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='record an experiment')
    parser.add_argument('config', type=Path, help='path to the config file')
    args = parser.parse_args()

    exit_code = 0
    config_file = args.config
    # parse yaml config file
    config_dict = yaml_to_dict(config_file)
    try:
        config: RecordConfig = cattrs.structure(config_dict, RecordConfig)
    except cattrs.ClassValidationError as e:
        print(f'config file {config_file} does not contain all required attributes')
        print(e)
        exit(1)


    setup_logging(sys.argv, Path(config.logfile))

    recorder_dir = Path(config.directory)
    screenshot_directory = recorder_dir / 'screenshots'
    screenshot_directory.mkdir(exist_ok=True)
    recorder = Recorder(screenshot_directory, screenshot_directory/'log.txt', trigger_keys=set(config.start_stop_key_combination))
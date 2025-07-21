from pathlib import Path
import cattrs
from adarelib.testset.type import TestsetFile
from adarelib.testset.yaml.customloader import YAML_TESTSET_LOADER
from adarelib.helper.yaml import yaml_to_dict

import logging
log = logging.getLogger(__name__)

def parse_testsetfile(testset_file: Path) -> TestsetFile:
    """
    Parses a testset file and returns a TestsetFile object.

    Can raise:
        cattrs.BaseValidationError

    :param testset_file: Path to the testset file.
    :return: A TestsetFile object.
    """
    log.debug(f'start to read input yaml file ({testset_file})')
    parsed_input = yaml_to_dict(testset_file, loader=YAML_TESTSET_LOADER)
    if not parsed_input:
        log.info(f'parsing input yaml file ({testset_file}) was NOT successful')
        return None
    log.debug(f'read input yaml file ({testset_file}) was successful')
    testsetfile: TestsetFile = cattrs.structure(parsed_input, TestsetFile)
    log.debug(f'testsetfile {testset_file} got successfully parsed')
    return testsetfile


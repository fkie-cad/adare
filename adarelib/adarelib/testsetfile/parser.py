# external imports
from pathlib import Path
import cattrs

# internal imports
from adare.customyaml.customloader import create_yaml_loader_dumper_inputfiles
from adare.helperFunctions.yaml import yaml_to_dict
from adare.testsetfile.fileformat import FTestsetFile

# logging configuration
import logging
log = logging.getLogger(__name__)


def parse_testsetfile(testset_file: Path) -> FTestsetFile or None:
    """
    parses a testsetfile and returns a TestsetFile object
    :param testset_file: path to the testsetfile
    :return: TestsetFile object
    """
    log.debug(f'start to read input yaml file ({testset_file})')
    loader, dumper = create_yaml_loader_dumper_inputfiles()
    parsed_input = yaml_to_dict(testset_file, loader=loader)
    if not parsed_input:
        log.info(f'parsing input yaml file ({testset_file}) was NOT successful')
        return None
    log.debug(f'read input yaml file ({testset_file}) was successful')
    try:
        testsetfile: FTestsetFile = cattrs.structure(parsed_input, FTestsetFile)
    except cattrs.BaseValidationError as e:
        log.error(f'parsing errors while parsing testsetfile {testset_file}:')
        exec_msgs = cattrs.transform_error(e)
        for msg in exec_msgs:
            log.error(msg)
        return None
    log.debug(f'testsetfile {testset_file} got successfully parsed')
    return testsetfile



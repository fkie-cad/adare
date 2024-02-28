# external imports
import cattrs
from pathlib import Path

# internal imports
from adarelib.types import ExperimentMetadata, TestsetFile, EnvironmentMetadata
from adarelib.exceptions import DataStructuringError
from adarelib.customyaml.customloader import create_yaml_loader_dumper_inputfiles
from adarelib.helperfunctions.yaml import yaml_to_dict

# configure logging
import logging
log = logging.getLogger(__name__)


def parse_metadata_file(metadata_file: Path) -> ExperimentMetadata:
    try:
        json_dict = yaml_to_dict(metadata_file)
        metadata = cattrs.structure(json_dict, ExperimentMetadata)
    except cattrs.BaseValidationError as e:
        log.error(f'parsing errors while parsing metadata file {metadata_file}:')
        exec_msgs = cattrs.transform_error(e)
        exec_msgs_str = "\n".join(exec_msgs)
        raise DataStructuringError(
            log,
            message=f'parsing errors while parsing metadata file {metadata_file}:{exec_msgs_str}',
            possible_solutions=[
                'fix the structure of the metadata file',
            ]
        ) from e
    return metadata


def parse_testsetfile(testset_file: Path) -> TestsetFile:
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
        testsetfile: TestsetFile = cattrs.structure(parsed_input, TestsetFile)
    except cattrs.BaseValidationError as e:
        error_msg = "\n".join(cattrs.transform_error(e))
        raise DataStructuringError(
            log,
            message=f'parsing errors while parsing testset file {testset_file}:{error_msg}',
            possible_solutions=[
                'fix the structure of the testset file',
            ]
        ) from e
    log.debug(f'testsetfile {testset_file} got successfully parsed')
    return testsetfile


def parse_environment_file(environment_file: Path) -> EnvironmentMetadata|None:
    environment_dict = yaml_to_dict(environment_file)
    try:
        environment = cattrs.structure(environment_dict, EnvironmentMetadata)
    except cattrs.BaseValidationError as e:
        error_msg = "\n".join(cattrs.transform_error(e))
        raise DataStructuringError(
            log,
            message=f'parsing errors while parsing environment file {environment_file}:{error_msg}',
            possible_solutions=[
                'fix the structure of the environment file',
            ]
        ) from e
    return environment

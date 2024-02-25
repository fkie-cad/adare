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
        metadata = cattrs.structure(metadata_file.read_text(), ExperimentMetadata)
    except cattrs.BaseValidationError as e:
        log.error(f'parsing errors while parsing metadata file {metadata_file}:')
        exec_msgs = cattrs.transform_error(e)
        raise DataStructuringError(
            metadata_file, 'ExperimentMetadata', "\n".join(exec_msgs)
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
            file=testset_file,
            class_name='TestsetFile',
            error=error_msg
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
            file=environment_file,
            class_name='EnvironmentMetadata',
            error=error_msg
        ) from e
    return environment

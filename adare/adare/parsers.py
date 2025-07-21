# external imports
import cattrs
from pathlib import Path


try:
    from adare.types.experiment import ExperimentMetadata
    from adare.types.environment import EnvironmentMetadata
except ImportError:
    # Should not happen after consolidation
    pass
from adare.exceptions import DataStructuringError
from adarelib.helper.yaml import yaml_to_dict

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

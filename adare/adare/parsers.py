# external imports
# configure logging
import logging
from pathlib import Path

import cattrs

from adare.exceptions import DataStructuringError
from adare.types.experiment import ExperimentMetadata
from adarelib.helper.yaml import yaml_to_dict

log = logging.getLogger(__name__)


def parse_metadata_file(metadata_file: Path) -> ExperimentMetadata:
    try:
        json_dict = yaml_to_dict(metadata_file)
        # Handle empty YAML files (yaml.safe_load returns None for empty files)
        json_dict = json_dict or {}
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
            ],
        ) from e
    return metadata

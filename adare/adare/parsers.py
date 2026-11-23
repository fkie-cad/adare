# external imports
# configure logging
import logging
from pathlib import Path
from typing import Any

import attrs
import cattrs

from adare.exceptions import DataStructuringError
from adare.types.experiment import ExperimentMetadata
from adarelib.helper.yaml import yaml_to_dict

log = logging.getLogger(__name__)


def _drop_null_defaults(raw: Any) -> Any:
    """Treat a key that is present but empty (``environments:`` with nothing after it) as absent.

    YAML reads such a key as ``null``; for every field that has a default (the lists
    ``environments``/``tags``/``usb``/``disk`` and ``description``) that means "use the default".
    Fields whose default is ``None`` (``smb``, ``nfs``, ``ocr``) are left alone.
    """
    if not isinstance(raw, dict):
        return raw  # not a mapping: leave it to cattrs to report
    defaulted = {
        field.name
        for field in attrs.fields(ExperimentMetadata)
        if isinstance(field.default, attrs.Factory)  # type: ignore[arg-type]
    }
    return {key: value for key, value in raw.items() if not (value is None and key in defaulted)}


def parse_metadata_file(metadata_file: Path) -> ExperimentMetadata:
    try:
        json_dict = yaml_to_dict(metadata_file)
        # Handle empty YAML files (yaml.safe_load returns None for empty files)
        json_dict = _drop_null_defaults(json_dict or {})
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

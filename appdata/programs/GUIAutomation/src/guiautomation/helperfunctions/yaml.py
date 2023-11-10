# internal imports
import yaml
from pathlib import Path

# setup logging
import logging
log = logging.getLogger(__name__)


def yaml_to_dict(file: Path):
    data = yaml.safe_load(file.read_text())
    return data


def dict_to_yaml(file: Path, data):
    with open(file.as_posix(), 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False)

import yaml
from pathlib import Path

import logging
log = logging.getLogger(__name__)


def yaml_to_dict(path):
    data = yaml.safe_load(Path(path).read_text())
    return data


def dict_to_yaml(file, data):
    with open(file, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False)

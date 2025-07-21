# external imports
import yaml
from pathlib import Path

# setup logging
import logging
log = logging.getLogger(__name__)


def yaml_to_dict(file: Path, loader=None):
    return (
        yaml.load(file.read_text(), Loader=loader) if loader else yaml.safe_load(file.read_text())
    )


def dict_to_yaml(file: Path, data, dumper=None):
    with open(file.as_posix(), 'w') as f:
        if not dumper:
            yaml.safe_dump(data, f, sort_keys=False)
        else:
            yaml.dump(data, f, Dumper=dumper)

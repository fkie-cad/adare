"""Load the repo's ``scripts/*.py`` (not a package) as modules for their tests."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[4] / 'scripts'


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f'scripts_{name}', SCRIPTS / f'{name}.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module

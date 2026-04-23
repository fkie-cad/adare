import importlib.util
from pathlib import Path


def import_module_from_pyfile(file: Path):
    # create module from spec
    module_name = file.stem
    spec = importlib.util.spec_from_file_location(module_name, file)

    # load the module from the spec
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

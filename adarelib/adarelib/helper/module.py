from pathlib import Path
import importlib.util
import re


def import_module_from_pyfile(file: Path):
    file = Path(file)

    # Derive a unique module name from the full file path rather than the bare
    # file stem. A bare stem like "json"/"csv"/"xml" collides with an already
    # imported stdlib module: sys.modules would then resolve the loaded module's
    # __name__ to the *stdlib* module, so any decorator (e.g. @testfunction) that
    # injects generated classes via sys.modules.get(func.__module__) writes them
    # into the stdlib module instead of this one, and the testfunction loader
    # can't discover them. A path-derived name never collides.
    module_name = 'adare_dynmod_' + re.sub(r'\W+', '_', str(file.resolve()))
    spec = importlib.util.spec_from_file_location(module_name, file)

    # load the module from the spec
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

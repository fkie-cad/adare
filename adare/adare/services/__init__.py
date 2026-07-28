# Services module - business logic layer
#
# Attribute access below is lazy (PEP 562): nothing here is imported eagerly,
# since eagerly importing e.g. EnvironmentService also runs os_catalog's
# module-level profile scan, which then fires for commands that never touch
# environments (e.g. `adare experiment list`).
__all__ = ['ProjectService', 'EnvironmentService', 'VMService', 'ExperimentService', 'TestfunctionService', 'ManageService', 'ShowService', 'WebService']

_SERVICE_MODULES = {
    'ProjectService': 'project_service',
    'EnvironmentService': 'environment_service',
    'VMService': 'vm_service',
    'ExperimentService': 'experiment_service',
    'TestfunctionService': 'testfunction_service',
    'ManageService': 'manage_service',
    'ShowService': 'show_service',
    'WebService': 'web_service',
}


def __getattr__(name):
    module_name = _SERVICE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, name)

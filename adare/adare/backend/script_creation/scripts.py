# external imports
# configure logging
import logging
from pathlib import Path

# internal imports
from adare.backend.script_creation.Script import Script

log = logging.getLogger(__name__)


class PostsetupInstallationsScript(Script):
    def __init__(self, name: str, source_directory: Path, log_directory: Path, postsetup_installations: list, render_wrapper: bool = False):
        super().__init__(name, source_directory, log_directory=log_directory, render_wrapper=render_wrapper)
        if postsetup_installations:
            var = {
                'installations': [[installation.name, installation.description, installation.command] for installation
                                  in postsetup_installations],
            }
            self.update_variables(var)
        else:
            self.disable_render()


class RunExperimentScript(Script):
    def __init__(self,
                 name: str,
                 source_directory: Path,
                 log_directory: Path,
                 path_directories: list[Path],
                 adarevm_path: Path,
                 experiment_config_file: Path,
                 render_wrapper: bool = False
                 ):
        super().__init__(name, source_directory, log_directory=log_directory, render_wrapper=render_wrapper)
        var = {
            'log_directory': log_directory,
            'path_directories': path_directories,
            'adarevm': adarevm_path,
            'experiment_config_file': experiment_config_file,
        }
        self.update_variables(var)


class MountNetworkDriveScript(Script):
    def __init__(self, name: str, source_directory: Path, log_directory:Path = None, share_information_list: list = None,
                 render_wrapper: bool = False):
        super().__init__(name, source_directory, log_directory=log_directory, render_wrapper=render_wrapper)
        if share_information_list:
            var = {
                'share': share_information_list,
            }
            self.update_variables(var)
        else:
            self.disable_render()


class SaveInstalledPackagesScript(Script):
    def __init__(self, name: str, source_directory: Path, log_directory: Path = None, render_wrapper: bool = False):
        super().__init__(name, source_directory, log_directory=log_directory, render_wrapper=render_wrapper)


class SetScreenResolutionScript(Script):
    def __init__(self, name: str, source_directory: Path, resolution: tuple, log_directory: Path = None, render_wrapper: bool = False):
        super().__init__(name, source_directory, log_directory=log_directory, render_wrapper=render_wrapper)
        var = {
            'x': resolution[0],
            'y': resolution[1]
        }
        self.update_variables(var)


class ShutdownScript(Script):
    def __init__(self, name: str, source_directory: Path, log_directory: Path = None, render_wrapper: bool = False):
        super().__init__(name, source_directory, log_directory=log_directory, render_wrapper=render_wrapper)

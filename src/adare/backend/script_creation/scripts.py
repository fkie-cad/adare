# external imports
from pathlib import Path

# internal imports
from adare.backend.script_creation.Script import Script
from adare.backend.attrs_classes import EnvironmentConfiguration

# configure logging
import logging
log = logging.getLogger(__name__)


class PostsetupInstallationsScript(Script):
    def __init__(self, name: str, source_directory: Path, configuration: EnvironmentConfiguration = None, render_wrapper: bool = False):
        super().__init__(name, source_directory, render_wrapper=render_wrapper)
        if configuration:
            var = {
                'installations': [[installation.name, installation.description, installation.command] for installation in configuration.postsetupinstallations],
            }
            self.update_variables(var)
        else:
            self.disable_render()


class RunExperimentScript(Script):
    def __init__(self, name: str,
                 source_directory: Path,
                 experiment_path: Path,
                 tessdata_directory: Path = None,
                 experiment_config_file: Path = None,
                 experiment: str = None,
                 result_file: Path = None,
                 project_script_directory: Path = None,
                 additional_tool_directory: Path = None,
                 render_wrapper: bool = False):
        super().__init__(name, source_directory, render_wrapper=render_wrapper)
        if experiment and result_file:
            var = {
                'gui_experiment': experiment,
                'inputfile': (experiment_path/f'{experiment}.yml').as_posix(),
                'outputfile': result_file.as_posix(),
                'result_directory': result_file.parent.as_posix(),
                'img_directory': (experiment_path/f'img').as_posix(),
                'tessdata_directory': tessdata_directory.as_posix(),
                'experiment_config_file': experiment_config_file.as_posix(),
                'experiment_file': (experiment_path/f'{experiment}.py').as_posix(),
                'project_script_directory': project_script_directory.as_posix(),
                'additional_tool_directory': additional_tool_directory.as_posix(),
            }
            self.update_variables(var)
        else:
            self.disable_render()


class MountNetworkDriveScript(Script):
    def __init__(self, name: str, source_directory: Path, share_information_list: list = None, render_wrapper: bool = False):
        super().__init__(name, source_directory, render_wrapper=render_wrapper)
        if share_information_list:
            var = {
                'share': share_information_list,
            }
            self.update_variables(var)
        else:
            self.disable_render()


class SaveInstalledPackagesScript(Script):
    def __init__(self, name: str, source_directory: Path, render_wrapper: bool = False):
        super().__init__(name, source_directory, render_wrapper=render_wrapper)

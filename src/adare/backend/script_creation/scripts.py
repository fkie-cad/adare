# external imports
from pathlib import Path

# internal imports
from adare.backend.script_creation.Script import Script
from adare.backend.attrs_classes import EnvironmentConfiguration, EnvironmentSetup

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


class RunExperimentTemplateScript(Script):
    def __init__(self, name: str, source_directory: Path, setup: EnvironmentSetup, render_wrapper: bool = False):
        super().__init__(name, source_directory, render_wrapper=render_wrapper)
        var = {
            'resolution': setup.resolution,
            'settings': setup.settings,
            'gui': setup.gui,
            'gui_scenario': "{{ gui_scenario }}",
            'inputfile': "{{ inputfile }}",
            'outputfile': "{{ outputfile }}",
            'log_directory': "{{ log_directory }}",
            'resultfolder': "{{ resultfolder }}",
            'pauseafterGUIAutmation': setup.pause_after_gui_automation
        }
        self.update_variables(var)


class RunExperimentScript(Script):
    def __init__(self, name: str, source_directory: Path, scenario: str = None, result_file: Path = None, render_wrapper: bool = False):
        super().__init__(name, source_directory, render_wrapper=render_wrapper)
        if scenario and result_file:
            var = {
                'gui_scenario': scenario,
                'inputfile': f'/vagrant/input/{scenario}.yml',
                'outputfile': result_file.as_posix(),
                'resultfolder': result_file.parent.as_posix(),
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

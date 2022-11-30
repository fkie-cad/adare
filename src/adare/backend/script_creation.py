# external imports
from pathlib import Path
import jinja2
import os

# internal imports
from adare.helperFunctions.jinja import jinjafeatures
from adare.backend.attrs_classes import EnvironmentConfiguration, EnvironmentSetup

# configure logging
import logging
log = logging.getLogger(__name__)


class Script:
    """
    abstract class used as parent class for various scripts
    (provide possibility to write the script and to remove the script)
    """
    P_path: Path
    __jinja: jinja2.Environment
    __jinja_template: jinja2.Template
    variables: dict

    def __init__(self, path: str, template: str, jinja_environment: jinja2.Environment = None, variables: dict or None = None):
        self.P_path = Path(path)
        if not variables:
            self.variables = {}
        else:
            self.variables = variables
        if jinja_environment:
            self.__jinja = jinja_environment
        else:
            self.__jinja = jinjafeatures.init_jinja_environment(template)
        if not self.__jinja:
            log.error(f'jinja environment for template folder {template} could not be created')
        try:
            self.__jinja_template = self.__jinja.get_template(Path(template).name)
        except jinja2.TemplateError as e:
            log.error(e, exc_info=True)
            log.error(f'template {Path(template).name} could not be found in the provided jinja environment')
            return

    def set_variables(self, var: dict):
        self.variables = var

    def write(self):
        with open(self.P_path.as_posix(), mode='w+') as f:
            f.write(self.__jinja_template.render(self.variables))

    def remove(self):
        os.remove(self.P_path.as_posix())


class PostsetupInstallationsScript(Script):
    def __init__(self, path: str, template: str, configuration: EnvironmentConfiguration, logfolder: str, jinja_environment: jinja2.Environment = None):
        super().__init__(path, template, jinja_environment)
        var = {
            'installations': [],
            'logfolder': logfolder
        }
        for installation in configuration.postsetupinstallations:
            var['installations'].append([installation.name, installation.description, installation.command])
        self.set_variables(var)


class RunExperimentTemplateScript(Script):
    def __init__(self, path: str, template: str, setup: EnvironmentSetup, jinja_environment: jinja2.Environment = None):
        super().__init__(path, template, jinja_environment)
        var = {
            'resolution': setup.resolution,
            'settings': setup.settings,
            'gui': setup.gui,
            'gui_scenario': "{{ gui_scenario }}",
            'inputfile': "{{ inputfile }}",
            'outputfile': "{{ outputfile }}",
            'logfolder': "{{ logfolder }}",
            'pauseafterGUIAutmation': setup.pause_after_gui_automation
        }
        self.set_variables(var)


class RunExperimentScript(Script):
    def __init__(self, path: str, template: str, scenario: str, resultfile: str, logfolder: str, jinja_environment: jinja2.Environment = None):
        super().__init__(path, template, jinja_environment)
        var = {
            'gui_scenario': scenario,
            'inputfile': f'/vagrant/input/{scenario}.yml',
            'outputfile': resultfile,
            'logfolder': logfolder
        }
        self.set_variables(var)


class MountNetworkDriveScript(Script):
    def __init__(self, path: str, template: str, share_information_list: list, logfolder: str, jinja_environment: jinja2.Environment = None):
        super().__init__(path, template, jinja_environment)
        var = {
            'share': share_information_list,
            'logfolder': logfolder
        }
        self.set_variables(var)


class SaveInstalledPackagesScript(Script):
    def __init__(self, path: str, template: str, logfolder: str, jinja_environment: jinja2.Environment = None):
        super().__init__(path, template, jinja_environment)
        var = {
            'logfolder': logfolder
        }
        self.set_variables(var)

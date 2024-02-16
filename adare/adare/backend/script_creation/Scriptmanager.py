# external imports
from pathlib import Path

# internal imports
from adare.backend.script_creation.Script import Script

# configure logging
import logging
log = logging.getLogger(__name__)


class ScriptManager:
    scripts: list[Script]
    script_directory_vm_view: Path
    log_directory: Path = None
    wrapper_template: Path

    def __init__(self, script_directory_vm_view: Path, wrapper_template: Path):
        self.scripts = []
        self.script_directory_vm_view = script_directory_vm_view
        self.wrapper_template = wrapper_template

    def set_log_directory_vm_view(self, log_directory_vm_view: Path):
        self.log_directory = log_directory_vm_view

    def add_script(self, script: Script):
        script.set_scripts_path_remote(self.script_directory_vm_view)
        script.set_wrapper_template(self.wrapper_template)
        script.update_variables({'log_directory': self.log_directory.as_posix()})
        self.scripts.append(script)

    def render_to_environment(self, environment_script_directory: Path):
        for script in self.scripts:
            script.render(environment_script_directory)

    def remove_scripts_from_environment(self):
        for script in self.scripts:
            script.remove_rendered_script(delete_wrapper=True)

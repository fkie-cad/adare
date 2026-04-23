# external imports
# configure logging
import logging
from pathlib import Path

from adare.backend.experiment.directory import ExperimentRunDirectory

# internal imports
from adare.backend.script_creation.Script import Script

log = logging.getLogger(__name__)


class ScriptManager:
    scripts: list[Script]
    wrapper_template: Path

    experiment_run_directory: ExperimentRunDirectory
    shared_root_directory_host: Path
    shared_root_directory_vm: Path

    def __init__(self, experiment_run_directory: ExperimentRunDirectory, shared_root_directory_host: Path,
                 shared_root_directory_vm: Path, wrapper_template: Path):
        self.scripts = []
        self.wrapper_template = wrapper_template
        self.experiment_run_directory = experiment_run_directory
        self.shared_root_directory_host = shared_root_directory_host
        self.shared_root_directory_vm = shared_root_directory_vm

    def add_script(self, script: Script):
        script.set_scripts_path_remote(self.experiment_run_directory.get_path_relative_to_shared_directory(
            'scripts_directory', self.shared_root_directory_host, self.shared_root_directory_vm))
        script.set_wrapper_template(self.wrapper_template)
        self.scripts.append(script)

    def render(self, render_directory: Path):
        for script in self.scripts:
            script.render(render_directory)

    def remove_scripts(self):
        for script in self.scripts:
            script.remove_rendered_script(delete_wrapper=True)

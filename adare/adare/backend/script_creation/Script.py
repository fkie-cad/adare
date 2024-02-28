# external imports
import shutil
from pathlib import Path
import jinja2
import os

# internal imports
from adarelib.helperfunctions.jinja import jinjafeatures

# configure logging
import logging
log = logging.getLogger(__name__)


class Script:
    """
    abstract class used as parent class for various scripts
    (provide possibility to write the script and to remove the script)
    """
    name: str
    variables: dict
    directory: Path
    destination_directory: Path = None
    destination_script_path: Path = None
    scripts_path_remote: Path = None
    wrapper = None
    render_wrapper: bool = False
    wrapper_template: Path = None
    only_copy: bool

    def __init__(self, name: str, source_directory: Path, variables: dict or None = None, render_wrapper: bool = False, only_copy: bool = False):
        self.name = name
        self.variables = variables or {}
        self.is_template = True
        self.directory = source_directory
        self.render_wrapper = render_wrapper
        self.only_copy = only_copy

    def set_scripts_path_remote(self, path: Path):
        self.variables['scripts_directory'] = path.as_posix()
        self.scripts_path_remote = path

    def set_wrapper_template(self, file: Path):
        self.wrapper_template = file

    def create_wrapper(self):
        """
        create a wrapper for the script (needed to save exit code of the script due to the missing capability
        of vagrant to store provisioner exit codes)
        """
        wrapper_script = Script(
            name=self.wrapper_template.name,
            source_directory=self.wrapper_template.parent,
        )
        script_path = (self.scripts_path_remote / f'{self.name}')
        script_name = script_path.stem
        wrapper_script.update_variables(
            {
                'script': script_path.as_posix(),
                'scripts_directory': self.scripts_path_remote.as_posix(),
                'name': script_name
            }
        )
        if self.destination_directory:
            wrapper_script.render(self.destination_directory, name=f'wrapper_{self.name}')
            self.wrapper = wrapper_script
            return wrapper_script
        else:
            log.error('script was not rendered, therefore no wrapper could be created')
            return None

    def disable_render(self):
        """
        disable the opportunity to render the script (only copy is possible)
        """
        self.only_copy = False

    def update_variables(self, var: dict):
        """
        update the variables used for rendering
        """
        self.variables.update(var)

    def render(self, destination_directory: Path, name: str = None):
        """
        render the script
        """
        destination_directory = destination_directory
        if name:
            destination_script_path = destination_directory / name
        else:
            destination_script_path = destination_directory / self.name

        if not self.only_copy:
            jinja_env = jinjafeatures.init_jinja_environment(self.directory)
            if not jinja_env:
                log.error(f'jinja environment for directory {self.directory} could not be created')
                return
            template_name = self.name
            try:
                jinja_template = jinja_env.get_template(template_name)
            except jinja2.TemplateError as e:
                log.error(e, exc_info=True)
                log.error(f'template {template_name} could not be found in the provided jinja environment')
                return
            with open(destination_script_path.as_posix(), mode='w+') as f:
                f.write(jinja_template.render(self.variables))
        else:
            self.copy(destination_directory)

        # set here to check whether rendering was successful
        self.destination_directory = destination_directory
        self.destination_script_path = destination_script_path

        if self.render_wrapper and not self.wrapper:
            self.create_wrapper()

    def copy(self, destination_directory: Path, name: str = None):
        """
        copy the script
        """
        source_script_path = self.directory / self.name
        if name:
            destination_script_path = destination_directory / name
        else:
            destination_script_path = destination_directory / self.name
        shutil.copy(source_script_path, destination_script_path)
        log.info(f'script file {source_script_path} got copied successfully to {self.destination_script_path}')

    def remove_rendered_script(self, delete_wrapper=True):
        """
        remove the rendered script (as well as the created wrapper)
        """
        if not self.destination_script_path:
            log.error(f'rendered script {self.name} could not be deleted because it was not rendered before')
            return
        os.remove(self.destination_script_path.as_posix())
        if delete_wrapper and self.wrapper:
            self.wrapper.remove_rendered_script()

    def exists(self) -> bool:
        """
        check if the rendered script already/still exists
        """
        return self.destination_script_path.is_file()

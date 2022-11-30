# external imports
import pkg_resources
from subprocess import Popen, PIPE
from datetime import datetime, timezone
from guibot.guibot import GuiBot
from pathlib import Path
import re

# internal imports
from guiautomation.yamlfeatures.basics import dict_to_yaml, yaml_to_dict

# logging
import logging
import guiautomation.config as config

log = logging.getLogger(__name__)


class Scenario:
    description = None
    vars_tmp_file = config.VARIABLES_FILE
    img_folder: Path = None
    vars: dict

    def __init__(self):
        self.img_folder = Path(pkg_resources.resource_filename('guiautomation.Scenario', 'data/img'))
        self.__load_vars()
        self.guibot = GuiBot()
        log.info(f'GuiBot Object created with display controller(dc) backend {str(type(self.guibot.dc_backend).__name__)} and  computer vision (cv) backend  {str(type(self.guibot.cv_backend).__name__)}')
        self.guibot.add_path(self.img_folder.as_posix())

    def prepare(self):
        pass

    def exists(self, name: str) -> bool:
        if (self.img_folder/name).is_file():
            return self.guibot.exists(name)
        else:
            matches = 0
            pattern = fr'\b{name}_[0-9]+\b'
            compiled_pattern = re.compile(pattern)
            for file in self.img_folder.iterdir():
                if compiled_pattern.match(file.name):
                    matches += 1
            if matches > 0:
                return True
        return False



    def __load_vars(self):
        try:
            self.vars = yaml_to_dict(self.vars_tmp_file)
        except FileNotFoundError:
            self.vars = {}

    def __save_vars(self):
        dict_to_yaml(self.vars_tmp_file, self.vars)

    def save_time(self, name):
        key = f'TIMESTAMP.{name}'
        if key in self.vars.keys():
            log.error(f'time can\'t be saved because key {key} is already existing in the variables file')
            return
        self.vars[key] = datetime.now(timezone.utc).astimezone().strftime(config.TIMESTAMP_FORMAT)
        self.__save_vars()

    def save_variable(self, name, value):
        key = f'{name}'
        forbidden_keys = [f'TIMESTAMP.{key}']
        for k in forbidden_keys:
            if k in self.vars.keys():
                log.error(f'key {k} does exist in variable file and therefore key {name} can NOT be added to the storage')
                return
        if key in self.vars.keys():
            log.error(f'value {value} can\'t be saved because key {key} is already existing in the variables file')
            return
        self.vars[key] = value
        self.__save_vars()

    def exec_shellcommand(self, command: list, cwd=None):
        log.info("run command '" + " ".join(command) + "'")
        if not cwd:
            proc = Popen(command, stdout=PIPE, stderr=PIPE)
        else:
            proc = Popen(command, stdout=PIPE, stderr=PIPE, cwd=cwd)
        stdout, stderr = proc.communicate()
        ret = {
            'returncode': proc.returncode,
            'stdout': stdout.decode("utf-8"),
            'stderr': stderr.decode("utf-8")
        }
        log.debug("'" + " ".join(command) + "' exited with returncode: " + str(ret['returncode']))
        if ret['stdout']:
            log.debug(
                "'" + " ".join(command) + "' exited with stdout: " + ret['stdout'])
        if ret['stderr']:
            log.debug(
                "'" + " ".join(command) + "' exited with stderr: " + ret['stderr'])
        if ret['returncode'] != 0:
            log.error(" ".join(command) + " exited with an error (returncode " + str(ret['returncode']) + ")")
        else:
            log.info(f'({" ".join(command)}) exited successfully.')
        return ret

    def run(self):
        pass

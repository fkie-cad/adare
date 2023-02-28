# external imports
from subprocess import Popen, PIPE
from datetime import datetime, timezone
from guibot.guibot import GuiBot
import guibot.match
import guibot.errors
from guibot.finder import Finder, TemplateFinder, TextFinder
from pathlib import Path
from guiautomation.helperfunctions.text import slugify

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
    status: str = 'success'
    template_match_files: dict
    text_match_file: Path
    scenario_log_file: Path
    tessdata_path: Path

    def __init__(self, img_folder: Path, tessdata_folder: Path, scenario_log_file: Path = None):
        #self.img_folder = Path(pkg_resources.resource_filename('guiautomation.Scenario', 'data/img'))
        self.img_folder = img_folder
        self.__load_vars()
        self.guibot = GuiBot()
        log.info(f'GuiBot Object created with display controller(dc) backend {str(type(self.guibot.dc_backend).__name__)} and  computer vision (cv) backend  {str(type(self.guibot.cv_backend).__name__)}')
        self.guibot.add_path(self.img_folder.as_posix())
        self.scenario_log_file = scenario_log_file
        self.template_match_files = {}
        self.text_match_files = None
        self.tessdata_folder = tessdata_folder

    def prepare(self):
        """
        This method can be used in child classes to do stuff before running the gui automation scenario.
        This can include creating/removing/changing a file or other.
        In cases where a shell/powershell command should be run the method exec_shellcommand.
        """
        pass

    def create_match_file_from_finder(self, name: str, finder: Finder):
        """
        creates a guibot match file given a guibot finder
        """
        Finder.to_match_file(finder, (self.img_folder/name).as_posix())

    def __get_cv_template_matcher(self, similarity: float) -> Path:
        similarity_100 = int(similarity*100)
        similarity_str = str(similarity_100).replace('.', '')
        match_file = self.img_folder/f'cv_template_{similarity_str}.match'
        if match_file not in self.template_match_files.keys():
            self.__create_cv_template_matcher(match_file, similarity)
        return match_file

    def __get_textfinder_matcher(self, similarity: float):
        similarity_100 = int(similarity*100)
        similarity_str = str(similarity_100).replace('.', '')
        match_file = self.img_folder/f'cv_template_{similarity_str}.match'
        if match_file not in self.template_match_files.keys():
            self.__create_textfinder_matcher(match_file, similarity)
        return match_file

    def __create_cv_template_matcher(self, match_file: Path, similarity: float):
        finder = TemplateFinder()
        finder.params["find"]["similarity"].value = similarity
        TemplateFinder.to_match_file(finder, match_file.as_posix())
        self.template_match_files[similarity] = match_file

    def __create_textfinder_matcher(self, match_file: Path, similarity: float):
        finder = TextFinder()
        finder.params["text"]["datapath"].value = f'{self.tessdata_folder.parent.as_posix()}/'
        finder.params["ocr"]["extra_configs"].value = None
        finder.params["find"]["similarity"].value = similarity
        TextFinder.to_match_file(finder, match_file.as_posix())

    def __create_steps_file_icon(self, image_path: Path, minimal_similarity: float = 0.6, step: float = 0.1, start_similarity: float = 0.9) -> Path:
        steps_file_name = f'steps_{image_path.stem}.steps'
        steps_file_path = self.img_folder/steps_file_name
        match_files = []
        if start_similarity-minimal_similarity > 0 and (start_similarity-minimal_similarity)/step < 100:
            similarity = start_similarity
            while similarity >= minimal_similarity:
                line = f'{image_path.name}\t{self.__get_cv_template_matcher(similarity).name}'
                match_files.append(line)
                similarity -= step
        with open(steps_file_path.as_posix(), mode='w') as f:
            f.write('\n'.join(match_files))
        return steps_file_path

    def __create_steps_file_text(self, textfile_path: Path, minimal_similarity: float = 0.6, step: float = 0.1, start_similarity: float = 0.9) -> Path:
        steps_file_name = f'steps_{textfile_path.stem}.steps'
        steps_file_path = self.img_folder / steps_file_name
        match_files = []
        if start_similarity - minimal_similarity > 0 and (start_similarity - minimal_similarity) / step < 100:
            similarity = start_similarity
            while similarity >= minimal_similarity:
                line = f'{textfile_path.name}\t{self.__get_textfinder_matcher(similarity).name}'
                match_files.append(line)
                similarity -= step
        with open(steps_file_path.as_posix(), mode='w') as f:
            f.write('\n'.join(match_files))
        return steps_file_path

    def __create_textfile(self, string: str) -> Path:
        filename = f'{slugify(string)}.txt'
        filepath = self.img_folder/filename
        with open(filepath.as_posix(), mode='w') as f:
            f.write(string)
        return filepath

    def find(self, name: str, alternative_images: list = None) -> list[guibot.match.Match] or None:
        match_objects = []
        file_path = (self.img_folder/name)
        if file_path.is_file():
            if file_path.suffix == 'steps':
                match_objects = self.guibot.find(name)
            elif file_path.suffix in ['.png', '.jpeg', 'jpg']:
                steps_filepath = self.__create_steps_file_icon(file_path)
                try:
                    match_objects = self.guibot.find_all(steps_filepath.name)
                except guibot.errors.FindError:
                    pass
        else:
            log.error(f'provided file {file_path} does not exits')

        if not match_objects and alternative_images:
            for alternative_image in alternative_images:
                match_objects = self.find(alternative_image)
                if match_objects:
                    break
        return match_objects

    def find_text(self, string: str) -> list[guibot.match.Match] or None:
        textfile = self.__create_textfile(string)
        stepsfile = self.__create_steps_file_text(textfile)
        try:
            return self.guibot.find_all(stepsfile.name)
        except guibot.errors.FindError:
            return None

    def exists(self, name: str) -> bool:
        match_obj = self.find(name)
        if match_obj:
            return True
        else:
            return False

    def log(self, content: str, quiet: bool = False):
        if not self.scenario_log_file:
            log.warning(f'log message can not be written to the scenario log because no log file is specified')
            return
        with open(self.scenario_log_file.as_posix(), mode='a') as f:
            timestamp = datetime.now().strftime('%Y%m%d %H:%M:%S')
            message = f'[{timestamp}]: {content}'
            if not quiet:
                print(message)
            f.write(f'[{timestamp}]: {content}')

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

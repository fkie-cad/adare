# external imports
import contextlib
from subprocess import Popen, PIPE
from datetime import datetime, timezone
from guibot.guibot import GuiBot
import guibot.match
import guibot.errors
from guibot.finder import Finder, TemplateFinder, TextFinder
from pathlib import Path
from adarelib.helperfunctions.text import slugify

# internal imports
from adarelib.helperfunctions.yaml import dict_to_yaml, yaml_to_dict
import adarevm.config as config
from adarevm.testset.testset import Testset
from adarevm.event import EventSystem
from adarelib.types import GuiClickEvent, GuiFindEvent, GuiKeypressEvent, GuiIdleEvent, GuiClickEventStart

# logging
import logging
log = logging.getLogger(__name__)


class Experiment:

    description = None
    vars_tmp_file: Path = config.VARIABLES_FILE
    img_folder: Path = None
    variables: dict
    status: str = 'success'
    template_match_files: dict
    text_match_file: Path
    tessdata_path: Path
    testset: Testset
    eventsystem: EventSystem

    def __init__(self, img_folder: Path, tessdata_folder: Path, testset: Testset, eventsystem: EventSystem):
        self.img_folder = img_folder
        self.guibot = GuiBot()
        log.info(f'GuiBot Object created with display controller(dc) backend {str(type(self.guibot.dc_backend).__name__)} and  computer vision (cv) backend  {str(type(self.guibot.cv_backend).__name__)}')
        self.guibot.add_path(self.img_folder.as_posix())
        # self.guibot.cv_backend.synchronize_backend("tesserocr", "ocr")
        self.template_match_files = {}
        self.text_match_files = None
        self.tessdata_folder = tessdata_folder
        self.testset = testset
        self.eventsystem = eventsystem

    def prepare(self):
        """
        This method can be used in child classes to do stuff before running the gui automation experiment.
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
        match_file = self.__get_match_file_name(similarity)
        if match_file not in self.template_match_files.keys():
            self.__create_cv_template_matcher(match_file, similarity)
        return match_file

    def __get_textfinder_matcher(self, similarity: float):
        match_file = self.__get_match_file_name(similarity)
        if match_file not in self.template_match_files.keys():
            self.__create_textfinder_matcher(match_file, similarity)
        return match_file


    def __get_match_file_name(self, similarity):
        similarity_100 = int(similarity * 100)
        similarity_str = str(similarity_100).replace('.', '')
        return self.img_folder / f'cv_template_{similarity_str}.match'

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

    def find(self, image_name: str, minimal_similarity: float = 0.6, similarity_steps:float = 0.1) -> list[guibot.match.Match] or None:
        """
        Finds the image in the current screen and returns a list of matches or None if no match was found.
        Therefore, creates a chain of searches starting with a 90% similarity and decreasing the similarity by 10% until the image is found.
        If the image is not found with a similarity of the minimal similarity parameter the search is aborted and None is returned.
        :param image_name: name of the image
        :param minimal_similarity: the minimal similarity to find the image with
        :param similarity_steps: the steps to decrease the similarity by
        :return:
        """
        match_objects = []
        image = (self.img_folder/image_name)
        if image.is_file():
            # check if steps file does already exist
            if image.suffix == 'steps':
                match_objects = self.guibot.find(image_name)
            elif image.suffix in ['.png', '.jpeg', 'jpg']:
                steps_filepath = self.__create_steps_file_icon(image, minimal_similarity=minimal_similarity, step=similarity_steps)
                with contextlib.suppress(guibot.errors.FindError):
                    match_objects = self.guibot.find_all(steps_filepath.name)
        else:
            log.error(f'provided image {image} does not exits')

        self.eventsystem.log(
            GuiFindEvent(
                objective=image_name, success=bool(match_objects), text=False
            )
        )

        return match_objects

    def find_text(self, text: str) -> list[guibot.match.Match] or None:
        """
        Finds the text in the current screen and returns a list of matches or None if no match was found.
        :param text: string to be found
        :return:
        """
        textfile = self.__create_textfile(text)
        stepsfile = self.__create_steps_file_text(textfile)
        try:
            elements = self.guibot.find_all(stepsfile.name)
            self.eventsystem.log(
                GuiFindEvent(
                    objective=text, success=bool(elements), text=True
                )
            )
            return elements
        except guibot.errors.FindError:
            return None

    def save_time(self, timestamp_var_name: str):
        """
        saves the current time to the variables file
        :param timestamp_var_name: name of the variable
        :return:
        """
        key = f'TIMESTAMP.{timestamp_var_name}'
        if key in self.variables.keys():
            log.error(f'time can\'t be saved because key {key} is already existing in the variables file')
            return
        self.variables[key] = datetime.now(timezone.utc).astimezone().strftime(config.TIMESTAMP_FORMAT)

    def save_variable(self, name: str, value: str):
        """
        Saves the given value under the given name in the variables file.
        :param name: name of the variable
        :param value: value of the variable as string
        :return:
        """
        key = f'{name}'
        forbidden_keys = [f'TIMESTAMP.{key}']
        for k in forbidden_keys:
            if k in self.variables.keys():
                log.error(f'key {k} does exist in variable file and therefore key {name} can NOT be added to the storage')
                return
        if key in self.variables.keys():
            log.error(f'value {value} can\'t be saved because key {key} is already existing in the variables file')
            return
        self.variables[key] = value

    def run_test(self, name: str):
        """
        runs a test
        :param name: name of the test
        :return:
        """
        self.testset.test(name, self.variables)

    def run_tests(self, names: list[str]):
        """
        runs a list of tests
        :param names: list of test names
        :return:
        """
        for name in names:
            self.run_test(name)

    def run_all_tests(self):
        """
        runs all tests
        :return:
        """
        self.testset.testall(self.variables)

    def click(self, target_or_location: str, modifiers = None):
        match = self.guibot.click(target_or_location, modifiers=modifiers)
        self.eventsystem.log(
            GuiClickEvent(
                clicktype='left', modifiers=modifiers, success=bool(match)
            )
        )
        return match

    def right_click(self, target_or_location: str, modifiers = None):
        match = self.guibot.right_click(target_or_location, modifiers=modifiers)
        self.eventsystem.log(
            GuiClickEvent(
                clicktype='right', modifiers=modifiers, success=bool(match)
            )
        )
        return match

    def double_click(self, target_or_location, modifiers = None):
        match = self.guibot.double_click(target_or_location, modifiers=modifiers)
        self.eventsystem.log(
            GuiClickEvent(
                clicktype='double', modifiers=modifiers, success=bool(match)
            )
        )
        return match

    def press_keys(self, keys):
        self.guibot.press_keys(keys)
        if type(keys) is str:
            keys = [keys]
        self.eventsystem.log(
            GuiKeypressEvent(
                keys=keys
            )
        )

    def idle(self, timeout: int):
        self.guibot.idle(timeout)
        self.eventsystem.log(
            GuiIdleEvent(
                seconds=timeout
            )
        )

    def exec_shellcommand(self, command: list, cwd=None):
        """
        executes a shell command
        :param command: list of command and arguments
        :param cwd: current working directory where the command should be executed
        :return:
        """

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

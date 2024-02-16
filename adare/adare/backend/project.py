# external imports
from pathlib import Path
import shutil

# internal imports
from adare.config.configdirectory import TEMPLATES_DIR, PROGRAMS_DIR
from adare.helperFunctions.web.download import download
from adare.database.api.project import ProjectManagementApi
from adare.backend.environment import Environment
from adare.backend.setupfile import load_setupfile

# configure logging
import logging
log = logging.getLogger(__name__)


class Project:
    """
    this class is used to represent a project and to perform actions on this project such as creating an environment
    it is also used to access the environments stored inside the project
    """
    name: str
    base_directory: Path

    def __init__(self, path: str, create: bool = False):
        self.base_directory = Path(path).absolute()
        self.name = self.base_directory.name
        if create:
            log.info(f'project in path {self.base_directory} will be created')
            if self.base_directory.exists():
                log.error(f'project in path {self.base_directory} already exists')
                exit(-1)
            elif not self.base_directory.parent.exists():
                log.error(f'parent directory of project in path {self.base_directory} does not exist')
                exit(-1)
            self.__create()
        else:
            log.info(f'project in path {self.base_directory} will be loaded')
            if not Path(path).exists():
                log.error(f'project in path {self.base_directory} does not exist')
                exit(-1)
            self.__repair_if_broken()


    def __create(self):
        """
            create a new project
        """

        if not PROGRAMS_DIR.is_dir():
            log.error(f'programs directory ({PROGRAMS_DIR.as_posix()}) does not exist')
            exit(-1)

        try:
            self.base_directory.mkdir()
        except FileNotFoundError or OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)

        try:
            shutil.copytree(PROGRAMS_DIR.as_posix(), self.base_directory / 'programs', ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)

        try:
            shutil.copytree(TEMPLATES_DIR.as_posix(), self.base_directory / 'programs' / 'templates', ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
        except OSError as e:
            log.error(e, exc_info=True)
            self.__cleanup()
            log.error(f'project ({self.base_directory}) creation failed')
            exit(-1)

        self.__get_tessdata()

        for directoryname in ['setup', 'environments', 'additional_tools']:
            try:
                (self.base_directory / directoryname).mkdir()
            except OSError as e:
                log.error(e, exc_info=True)
                self.__cleanup()
                log.error(f'project ({self.base_directory}) creation failed')
                exit(-1)

        # add project to database
        with ProjectManagementApi() as api:
            api.add_project(self.name, self.base_directory, description='')

        log.info(f'project ({self.base_directory}) creation was successful')

    def __get_tessdata(self, tessdata_directory: Path = None):
        """
            copy tessdata needed for text recognition in the gui automation to the project
        """
        if not tessdata_directory:
            log.info('download tessdata training data for text recognition in gui automation')
            tessdata_directory = self.base_directory/'tessdata'
            tessdata_directory.mkdir()
            tessdata_github_link = r'https://github.com/tesseract-ocr/tessdata/blob/main/eng.traineddata?raw=true'
            tessdata_file = tessdata_directory/'eng.traineddata'
            download(tessdata_github_link, tessdata_file, quiet=True)
            log.info('download of tessdata training data for text recognition in gui automation was successful')
        else:
            log.info('copy tessdata training data for text recognition in gui automation')
            shutil.copytree(tessdata_directory, self.base_directory / 'tessdata')
            log.info('copy of tessdata training data for text recognition in gui automation was successful')


    def __repair_if_broken(self):
        project_children = [f.name for f in self.base_directory.iterdir()]
        broken_element_found = False
        for mandatory_children in ['setup', 'environments', 'programs']:
            if mandatory_children not in project_children:
                broken_element_found = True
                log.warning(f'needed directory/file {mandatory_children} is not a child of the project folder -> '
                            f'try to recreate the missing directory/file if possible')
                exit(-1)
        if broken_element_found:
            log.info(f'project ({self.base_directory}) repair was successful')
        else:
            log.debug(f'project ({self.base_directory}) contains all necessary elements')

    def __cleanup(self):
        """
            clean up / delete the project directory
        """
        try:
            shutil.rmtree(self.base_directory.as_posix())
        except OSError as e:
            log.error(e, exc_info=True)
            log.error(f'project ({self.base_directory}) cleanup failed')
            exit(-1)
        log.info(f'project ({self.base_directory}) cleanup was successful')

    def remove(self):
        """
            remove the project
        """
        self.__cleanup()

        # remove project from database
        with ProjectManagementApi() as api:
            api.remove_project(self.name)

        log.info(f'project ({self.base_directory}) remove was successful')

    def add_environment(self, setupfile: Path, name: str = None):
        """
            add a new environment to the project
        """
        # if no name is provided -> use the name from the setup file
        if not name:
            setup = load_setupfile(setupfile)
            name = setup.name

        # create environment
        env = Environment(name, self.base_directory, create=True, setupfile=setupfile)

        log.info(f'environment ({env.name}) creation was successful')
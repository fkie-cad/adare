# internal imports
from adare.exception_baseclasses import LoggedException

# configure logging
import logging
log = logging.getLogger(__name__)


class ProjectNotFound(LoggedException):
    def __init__(self, path):
        self.message = f'path of the project ({path}) doesn\'t exist'
        super().__init__(self.message)


class ProjectNotRepairable(LoggedException):
    def __init__(self, projectname):
        self.message = f'project ({projectname}) is not repairable - please create a new one and manually copy needed data'
        super().__init__(self.message)


class ProjectDirectoryAlreadyExists(LoggedException):
    def __init__(self, projectpath):
        self.message = f'the chosen project path {projectpath} is already in use - please choose another one or delete the old project'
        super().__init__(self.message)


class ProjectDirectoryParentDirectoryMissing(LoggedException):
    def __init__(self, projectpath):
        self.message = f'the parent directory of the chosen project path {projectpath} is missing'
        super().__init__(self.message)


class ProjectCreationFailied(LoggedException):
    def __init__(self, projectpath):
        self.message = f'the project with path {projectpath} could not be created successfully'
        super().__init__(self.message)


class ProjectLoadFailed(LoggedException):
    def __init__(self, projectpath):
        self.message = f'the project with path {projectpath} could not be loaded successfully'
        super().__init__(self.message, critical=True)


class ProjectDeletionError(LoggedException):
    def __init__(self, projectpath):
        self.message = f'the project with path {projectpath} can not be removed'
        super().__init__(self.message, critical=True)


class ProjectCleanupFailed(LoggedException):
    def __init__(self, projectpath):
        self.message = f'the project with path {projectpath} could not be cleaned up after errors occured during the creation -> manual deletion needed'
        super().__init__(self.message, critical=True)


class ProgramFolderMissingInInstallation(LoggedException):
    def __init__(self, programspath):
        self.message = f'program folder is missing in installed package (location: {programspath})'
        super().__init__(self.message, critical=True)


class ProjectInformationMissing(LoggedException):
    def __init__(self):
        self.message = 'project class is missing the project information'
        super().__init__(self.message)


class EnvironmentSetupFileMissing(LoggedException):
    def __init__(self, environment_name):
        self.message = f'no setup file for environment with name {environment_name} could be found'
        super().__init__(self.message)


class EnvironmentCreationError(LoggedException):
    def __init__(self, environment_name):
        self.message = f'environment with name {environment_name} could not be created'
        super().__init__(self.message)


class ProjectInformationCouldNotBeRead(LoggedException):
    def __init__(self, project_information_file):
        self.message = f'project information file with path {project_information_file} could not be read'
        super().__init__(self.message)


class EnvironmentInitializationFailed(LoggedException):
    def __init__(self, environment_name, create=False):
        if create:
            self.message = f'environment {environment_name} could not be created'
        else:
            self.message = f'environment {environment_name} could not be loaded'
        super().__init__(self.message)


class EnvironmentDoesNotExist(LoggedException):
    def __init__(self, environment_name):
        self.message = f'the chosen environment {environment_name} does not exist'
        super().__init__(self.message)


class ScenarioDoesNotExistInEnvironment(LoggedException):
    def __init__(self, environment_name, scenario):
        self.message = f'the chosen environment {environment_name} does not contain the scenario {scenario}'
        super().__init__(self.message)


class EnvironmentAlreadyExists(LoggedException):
    def __init__(self, environment_name):
        self.message = f'the environment {environment_name} could not be created, because it already exists'
        super().__init__(self.message)


class NoProjectFoundException(LoggedException):
    def __init__(self, provided_project_paths):
        self.message = f'none of the provided or default project paths ({provided_project_paths}) are a valid projects'
        super().__init__(self.message)


class ProjectEnvironmentCantBeCreated(LoggedException):
    def __init__(self, project):
        self.message = f'in project {project} the environment cant be created because neither setupfile or name are provided'
        super().__init__(self.message)


class PackageTemplateFolderMissing(LoggedException):
    def __init__(self, location):
        self.message = f'in the package the template folder ({location}) can\'t be found '
        super().__init__(self.message, critical=True)


class ScenarioAlreadyExists(LoggedException):
    def __init__(self, scenario):
        self.message = f'a scenario with name {scenario} already exists'
        super().__init__(self.message)


class EnvironmentConfigurationMissing(LoggedException):
    def __init__(self):
        self.message = 'environment could not be initialized because the environment configuration file is missing'
        super().__init__(self.message)


class EnvironmentSetupSyntaxError(LoggedException):
    def __init__(self):
        self.message = 'environment setup has a syntax error (make sure that no necessary keys are missing)'
        super().__init__(self.message)


class SafeDeletionError(LoggedException):
    def __init__(self, obj: str):
        self.message = f'deletion of {obj} was not successful caused to a safety feature preventing deletion of other files'
        super().__init__(self.message)


class DatabaseWrongSuffix(LoggedException):
    def __init__(self, suffix: str):
        self.message = f'provided database has wrong suffix {suffix}'
        super().__init__(self.message)


class PlatformNotSupported(LoggedException):
    def __init__(self, platform: str):
        self.message = f'platform {platform} is not supported by the prorgam'
        super().__init__(self.message)

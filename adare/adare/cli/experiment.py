# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.experiment.commands import experiment_create, experiment_load
# configure logging
import logging
log = logging.getLogger(__name__)


def exec_experiment_load(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        log.error('no project directory found')
        exit(1)
    experiment_load(project_directory, arguments.experiment, force=arguments.force)


def exec_experiment_create(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        log.error('no project directory found')
        exit(1)
    experiment_create(project_directory, arguments.experiment)


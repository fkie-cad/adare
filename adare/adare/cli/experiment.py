# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.experiment.commands import experiment_create, experiment_load, experiment_run
from adarelib.exceptions import NoProjectFoundError
# configure logging
import logging
log = logging.getLogger(__name__)


def exec_experiment_load(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_load(project_directory, arguments.experiment, force=arguments.force)
    else:
        raise NoProjectFoundError(log)


def exec_experiment_create(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_create(project_directory, arguments.experiment)
    else:
        raise NoProjectFoundError(log)



def exec_experiment_run(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_run(project_directory, arguments.experiment, arguments.environment, arguments.breakpoints, arguments.break_all)
    else:
        raise NoProjectFoundError(log)


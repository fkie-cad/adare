# external imports
from pathlib import Path

# internal imports
from adare.backend.script_creation.Script import Script
from adare.backend.script_creation.scripts import PostsetupInstallationsScript, SaveInstalledPackagesScript, \
    RunExperimentScript
import adare.backend.experiment.database as experiment_database
from adarelib.types import PostsetupInstallations
from adare.config import SCRIPTS_SUFFIX
from adare.backend.experiment.directory import ExperimentRunDirectory

# configure logging
import logging

log = logging.getLogger(__name__)


def create_installations_script(experiment_run_directory: ExperimentRunDirectory, environment_uuid: str, template_directory: Path) -> PostsetupInstallationsScript:
    installations: list[PostsetupInstallations] = experiment_database.get_environment_installations(environment_uuid)
    return PostsetupInstallationsScript(
        name=experiment_run_directory.install_script.name,
        postsetup_installations=installations,
        source_directory=template_directory,
        render_wrapper=True,
    )


def create_packagedump_script(experiment_run_directory: ExperimentRunDirectory, template_directory: Path) -> SaveInstalledPackagesScript:
    return SaveInstalledPackagesScript(
        name=experiment_run_directory.packagedump_script.name,
        source_directory=template_directory,
        render_wrapper=True,
    )


def create_run_script(run_config_file: Path, experimentrun_directory: ExperimentRunDirectory, adarevm_directory: Path,
                      path_directories: list[Path], template_directory: Path, script_suffix: str) -> Script:
    return RunExperimentScript(
        name=f'run{script_suffix}',
        source_directory=template_directory,
        script_directory=experimentrun_directory.path,
        log_directory=experimentrun_directory.log_directory,
        path_directories=path_directories,
        adarevm_path=adarevm_directory,
        experiment_config_file=run_config_file,
        render_wrapper=True,
    )

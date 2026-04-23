# external imports
# configure logging
import logging
from pathlib import Path

import adare.backend.experiment.database as experiment_database
from adare.backend.experiment.directory import ExperimentRunDirectory
from adare.backend.project.directory import ProjectDirectory

# internal imports
from adare.backend.script_creation.scripts import (
    PostsetupInstallationsScript,
    RunExperimentScript,
    SaveInstalledPackagesScript,
    ShutdownScript,
)
from adare.types.environment import PostsetupInstallations

log = logging.getLogger(__name__)


def create_installations_script(experiment_run_directory: ExperimentRunDirectory, environment_ulid: str, template_directory: Path, shared_root_directory_host: Path, shared_root_directory_vm: Path) -> PostsetupInstallationsScript:
    installations: list[PostsetupInstallations] = experiment_database.get_environment_installations(environment_ulid)
    return PostsetupInstallationsScript(
        name=experiment_run_directory.install_script.name,
        postsetup_installations=installations,
        log_directory=experiment_run_directory.get_path_relative_to_shared_directory('log_directory', shared_root_directory_host, shared_root_directory_vm),
        source_directory=template_directory,
        render_wrapper=True,
    )


def create_packagedump_script(experiment_run_directory: ExperimentRunDirectory, template_directory: Path, shared_root_directory_host: Path, shared_root_directory_vm: Path) -> SaveInstalledPackagesScript:
    return SaveInstalledPackagesScript(
        name=experiment_run_directory.packagedump_script.name,
        source_directory=template_directory,
        log_directory=experiment_run_directory.get_path_relative_to_shared_directory('log_directory', shared_root_directory_host, shared_root_directory_vm),
        render_wrapper=True,
    )


def create_run_script(experimentrun_directory: ExperimentRunDirectory, project_directory: ProjectDirectory,
                      path_directories: list[Path], template_directory: Path, script_suffix: str, shared_root_directory_host: Path, shared_root_directory_vm: Path) -> RunExperimentScript:
    return RunExperimentScript(
        name=f'run{script_suffix}',
        source_directory=template_directory,
        log_directory=experimentrun_directory.get_path_relative_to_shared_directory('log_directory', shared_root_directory_host, shared_root_directory_vm),
        path_directories=path_directories,
        adarevm_path=project_directory.get_path_relative_to_shared_directory('adarevm', shared_root_directory_host, shared_root_directory_vm),
        experiment_config_file=experimentrun_directory.get_path_relative_to_shared_directory('run_config_file', shared_root_directory_host, shared_root_directory_vm),
        render_wrapper=True,
    )


def create_shutdown_script(experimentrun_directory: ExperimentRunDirectory, template_directory: Path, shared_root_directory_host: Path, shared_root_directory_vm: Path) -> ShutdownScript:
    return ShutdownScript(
        name=experimentrun_directory.shutdown_script.name,
        source_directory=template_directory,
        log_directory=experimentrun_directory.get_path_relative_to_shared_directory('log_directory', shared_root_directory_host, shared_root_directory_vm),
        render_wrapper=True,
    )

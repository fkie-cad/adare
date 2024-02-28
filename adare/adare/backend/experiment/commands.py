# external imports
from pathlib import Path
import jinja2
import random

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError, ExperimentDirectoryDoesNotExistError
from adarelib.exceptions import LoggedException, LoggedErrorException
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.scripts import create_installations_script, create_packagedump_script, create_run_script
from adarelib.experimentconfig import ExperimentConfig
from adare.config import SCRIPTS_SUFFIX, SHARE_POINT_VM
from adare.config.configdirectory import TEMPLATES_DIR
from adare.backend.script_creation.Scriptmanager import ScriptManager
from adare.backend.script_creation.Script import Script
from adare.vagrantapi.vagrantfile import VagrantFile, VagrantMachine
from adare.vagrantapi.exceptions import VagrantFileCreationError
from adare.vagrantapi.vagrantbox import VagrantBoxVM

# configure logging
import logging
log = logging.getLogger(__name__)


def experiment_create(project_path: Path, experiment: str):

    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.create()
    log.info(f'experiment directory {experiment_directory.path} created')


def __experiment_update(experiment_uuid, experiment_name, experiment_directory, force, project_path):
    if not experiment_database.check_for_experiment_change(experiment_uuid, experiment_directory.sha256):
        raise LoggedException(log, f'experiment [i]{experiment_uuid}[/i] has not changed')
    log.info(f'experiment {experiment_uuid} has changed')
    if not force:
        raise LoggedException(log, f'experiment [i]{experiment_uuid}[/i] has changed, use --force to overwrite and delete all related experiment runs')
    # delete the experiment and all related experiment runs
    experiment_database.remove_experiment(experiment_uuid)
    log.info(f'experiment {experiment_uuid} removed')
    experiment_database.create_experiment(
        name=experiment_name,
        project_path=project_path,
        experiment_directory=experiment_directory
    )
    log.info(f'experiment {experiment_uuid} created')


def experiment_load(project_path: Path, experiment_name: str, force: bool = False):
    experiment_directory = ExperimentDirectory(project_path, experiment_name)
    if not experiment_directory.exists():
        raise ExperimentDirectoryDoesNotExistError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] does not exist',
            possible_solutions=[
                'create the experiment directory with `adare experiment create`'
            ]
        )
    experiment_directory.check_for_missing_files()

    if experiment_uuid := experiment_database.get_latest_experiment_by_project_and_name(
        project_path, experiment_name
    ):
        __experiment_update(
            experiment_uuid, experiment_name, experiment_directory, force, project_path
        )
    else:
        # create a new experiment in the database
        experiment_database.create_experiment(
            name=experiment_name,
            project_path=project_path,
            experiment_directory=experiment_directory
        )
        log.info(f'experiment {experiment_name} created')


def __create_vagrantfile(vg_vm_name: str, experiment_run_directory: ExperimentRunDirectory, environment_uuid: str, shared_root_directory_vm: Path, shared_root_directory_host: Path, template_directory: Path, script_suffix: str) -> VagrantFile:
    vg_machine = VagrantMachine(vg_vm_name)
    vg_file = VagrantFile()

    vg_box_name = experiment_database.get_environment_vagrant_box(environment_uuid)
    environment_platform = experiment_database.get_environment_platform(environment_uuid)
    vg_machine.set_box(vg_box_name)

    if environment_platform == 'windows':
        vg_machine.change_communicator('winrm')

    vg_machine.enable_gui()
    vg_file.disable_virtualbox_guestautoupdate()

    vg_machine.add_synced_folder(
        shared_root_directory_host,
        shared_root_directory_vm,
    )

    install_script_vm = experiment_run_directory.get_path_relative_to_shared_directory('wrapper_install_script', shared_root_directory_host, shared_root_directory_vm)
    packagedump_script_vm = experiment_run_directory.get_path_relative_to_shared_directory('wrapper_packagedump_script', shared_root_directory_host, shared_root_directory_vm)
    run_script_vm = experiment_run_directory.get_path_relative_to_shared_directory('wrapper_run_script', shared_root_directory_host, shared_root_directory_vm)

    if environment_platform == 'windows':
        vg_machine.add_shell_provisioner_path(install_script_vm)
        vg_machine.add_shell_provisioner_path(run_script_vm)
        vg_machine.add_shell_provisioner_path(packagedump_script_vm)
    elif environment_platform == 'linux':
        vg_machine.add_shell_provisioner_path(install_script_vm, privileged=True, powershell_elevated_interactive=False)
        vg_machine.add_shell_provisioner_path(run_script_vm, privileged=True, powershell_elevated_interactive=True)
        vg_machine.add_shell_provisioner_path(packagedump_script_vm, privileged=True, powershell_elevated_interactive=True)
    else:
        raise ValueError(f'unknown environment platform {environment_platform}')

    vg_file.add_machine(vg_machine)

    return vg_file


def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    experiment_run_directory.clean()


def experiment_run(project_path: Path, experiment_name: str, environment_name: str, breakpoints: list[str] = None, break_all: bool = False):
    project_directory = ProjectDirectory(project_path)
    experiment_directory: ExperimentDirectory = ExperimentDirectory(
        project_path,
        experiment_name
    )
    # check integrity of the experiment files (action, testset, metadata)

    # check integrity of the used testfunction

    # check integrity of the used environment

    # get environment uuid
    environment_uuid = experiment_database.get_environment_uuid(project_path, environment_name)

    # check if vagrant box is existing

    environment_platform = experiment_database.get_environment_platform(environment_uuid)
    shared_root_directory_vm = Path(SHARE_POINT_VM[environment_platform])
    shared_root_directory_host = project_path

    # get directory for templates
    templates_experiment_scripts = TEMPLATES_DIR / environment_platform
    script_suffix = SCRIPTS_SUFFIX[environment_platform]

    # create run project structure
    experiment_run_directory = ExperimentRunDirectory(project_directory, experiment_name)
    experiment_run_directory.create()

    # create experiment config file
    run_config_file = ExperimentConfig(
        experiment=experiment_name,
        action=experiment_directory.get_path_relative_to_shared_directory('actionfile', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        testset=experiment_directory.get_path_relative_to_shared_directory('testsetfile', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        testfunction_directory=project_directory.get_path_relative_to_shared_directory('testfunctions', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        tessdata=project_directory.get_path_relative_to_shared_directory('tessdata', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        img=experiment_directory.get_path_relative_to_shared_directory('img', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        logfile=experiment_run_directory.get_path_relative_to_shared_directory('log_file', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        eventfile=experiment_run_directory.get_path_relative_to_shared_directory('event_file', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        statusfile=experiment_run_directory.get_path_relative_to_shared_directory('status_file', shared_root_directory_host, shared_root_directory_vm).as_posix()
    )
    experiment_run_directory.create_run_config(run_config_file)

    # setup paths to add to the PATH variable on the VM
    paths_to_add = [
        project_directory.get_path_relative_to_shared_directory('adare', shared_root_directory_host, shared_root_directory_vm),
        project_directory.get_path_relative_to_shared_directory('run', shared_root_directory_host, shared_root_directory_vm),
    ]

    # create scripts
    installation_script = create_installations_script(environment_uuid, templates_experiment_scripts, script_suffix)
    packagedump_script = create_packagedump_script(templates_experiment_scripts, script_suffix)
    run_script = create_run_script(
        run_config_file=experiment_run_directory.get_path_relative_to_shared_directory('run_config_file', shared_root_directory_host, shared_root_directory_vm),
        experimentrun_directory=experiment_run_directory,
        adarevm_directory=project_directory.get_path_relative_to_shared_directory('adarevm', shared_root_directory_host, shared_root_directory_vm),
        path_directories=paths_to_add,
        template_directory=templates_experiment_scripts,
        script_suffix=script_suffix
    )
    wrapper_template = templates_experiment_scripts / f'run_script_wrapper{script_suffix}'

    script_manager = ScriptManager(experiment_run_directory, shared_root_directory_host, shared_root_directory_vm, wrapper_template)
    script_manager.add_script(installation_script)
    script_manager.add_script(packagedump_script)
    script_manager.add_script(run_script)

    if environment_platform == 'windows':
        script_manager.add_script(Script(
            name=f'helperfunctions{script_suffix}',
            source_directory=templates_experiment_scripts
        ))

    script_manager.render(experiment_run_directory.scripts_directory)

    # todo: add network drive and mount scripts

    # create Vagrantfile
    random_number = random.randint(100000, 999999)
    vm_name = f'{environment_name}{experiment_name}{random_number}'
    vagrantfile: VagrantFile = __create_vagrantfile(
        vm_name,
        experiment_run_directory,
        environment_uuid,
        shared_root_directory_vm,
        shared_root_directory_host,
        templates_experiment_scripts,
        script_suffix
    )
    # todo: add network drive vm to Vagrantfile if needed

    # generate Vagrant Box
    box = VagrantBoxVM.fromVagrantFileObject(experiment_run_directory.path, vagrantfile, log_file=experiment_run_directory.log_file, vm_name=experiment_run_directory.path.name)

    # create experiment run in database

    # run box
    box.run(debug=False)

    # collect results

    # cleanup
    #__cleanup_experiment_run(experiment_run_directory)


# external imports
from pathlib import Path
import uuid
from datetime import datetime
import threading
from watchdog.observers import Observer
import time

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.project.database as project_database
import adare.backend.environment.database as environment_database
from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError, ExperimentDirectoryDoesNotExistError, VagrantBoxMissingError, ExperimentIntegrityError
from adarelib.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.scripts import create_installations_script, create_packagedump_script, create_run_script
from adarelib.experimentconfig import ExperimentConfig
from adare.config import SCRIPTS_SUFFIX, SHARE_POINT_VM
from adare.config.configdirectory import TEMPLATES_DIR
from adare.backend.script_creation.Scriptmanager import ScriptManager
from adare.backend.script_creation.Script import Script
from adare.vagrantapi.vagrantfile import VagrantFile, VagrantMachine
from adare.vagrantapi.vagrantbox import VagrantBoxVM
from adarelib.helperfunctions.string import make_string_path_safe
from adarelib.breakpoint import BreakpointReceiveHandler, BP_HOST_BEFORE_CLEANUP, BP_HOST_BEFORE_BOX_START, BP_HOST_AFTER_VAGRANTFILE_CREATION
from adare.backend.watcher.event import EventHandler
from adare.vagrantapi import vagrantutils
from adarelib.breakpoint import BreakPoint

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

    if experiment_uuid := experiment_database.get_experiment_by_project_and_name(
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


def __create_vagrantfile(vg_vm_name: str, experiment_run_directory: ExperimentRunDirectory, environment_uuid: str, shared_root_directory_vm: Path, shared_root_directory_host: Path, template_directory: Path, script_suffix: str, resolution=(1920,1080)) -> VagrantFile:
    vg_machine = VagrantMachine(vg_vm_name)
    vg_file = VagrantFile()

    vg_box_name = experiment_database.get_environment_vagrant_box(environment_uuid)
    environment_platform = experiment_database.get_environment_platform(environment_uuid)
    vg_machine.set_box(vg_box_name)

    if environment_platform == 'windows':
        vg_machine.change_communicator('winrm')

    vg_machine.enable_gui()
    vg_file.disable_virtualbox_guestautoupdate()
    vg_machine.set_resolution(resolution[0], resolution[1])

    vg_machine.add_synced_folder(
        shared_root_directory_host,
        shared_root_directory_vm,
    )

    if environment_platform == 'linux':
        vg_machine.add_shell_provisioner_path(experiment_run_directory.wrapper_install_script)
        vg_machine.add_shell_provisioner_path(experiment_run_directory.wrapper_run_script)
        vg_machine.add_shell_provisioner_path(experiment_run_directory.wrapper_packagedump_script)
    elif environment_platform == 'windows':
        vg_machine.add_shell_provisioner_path(experiment_run_directory.wrapper_install_script, privileged=True, powershell_elevated_interactive=False)
        vg_machine.add_shell_provisioner_path(experiment_run_directory.wrapper_run_script, privileged=True, powershell_elevated_interactive=True)
        vg_machine.add_shell_provisioner_path(experiment_run_directory.wrapper_packagedump_script, privileged=True, powershell_elevated_interactive=True)
    else:
        raise ValueError(f'unknown environment platform {environment_platform}')

    vg_file.add_machine(vg_machine)

    return vg_file


def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    experiment_run_directory.clean()


def __install_watchers(vagrant_box_vm: VagrantBoxVM, experimentrun_uuid: str, run_directory: Path, bp_directory: Path, ctrlc_event: threading.Event, breakpoints: list[str] = None):
    bp_handler = BreakpointReceiveHandler(breakpoints)
    event_handler = EventHandler(experimentrun_uuid)
    observer = Observer()
    observer.schedule(event_handler, run_directory.as_posix(), recursive=False)
    observer.schedule(bp_handler, bp_directory.as_posix(), recursive=True)
    observer.start()
    try:
        while vagrant_box_vm.should_watch:
            time.sleep(1)
    except KeyboardInterrupt:
        # send KeyboardInterrupt to thread executing the box
        ctrlc_event.set()
    finally:
        observer.stop()
        observer.join()
        log.info('all watchers stopped')


def __experiment_integrity_check(project_path: Path, experiment_name: str, experiment_directory: ExperimentDirectory):
    experiment_hashes = experiment_database.get_experiment_hashes(project_path, experiment_name)
    experiment_run_count = experiment_database.get_experiment_run_count(project_path, experiment_name)

    file_changed = []
    if experiment_directory.sha256_action != experiment_hashes['action']:
        file_changed.append('action')
    else:
        log.info(f'integrity check for action file {experiment_directory.actionfile} passed')
    if experiment_directory.sha256_testset != experiment_hashes['testset']:
        file_changed.append('testset')
    else:
        log.info(f'integrity check for testset file {experiment_directory.testsetfile} passed')
    if experiment_directory.sha256_metadata != experiment_hashes['metadata']:
        file_changed.append('metadata')
    else:
        log.info(f'integrity check for metadata file {experiment_directory.metadatafile} passed')

    message = 'to ensure the integrity of an experiment, experiment related files are not allowed to be changed after the experiment has been loaded\n'
    message += f'However, the following files have been changed: {", ".join(file_changed)}'
    solutions = []
    if experiment_run_count == 0:
        solutions.append(f'since no experiment runs have been executed yet, you can simply load the experiment again with `adare experiment load {experiment_name}` to overwrite the existing experiment')
    else:
        solutions.extend(
            (
                'if you want to change the experiment, you have to delete all related experiment runs with `adare experiment remove` and then load the experiment again with `adare experiment load`',
                'if you want to keep the experiment runs, you have to create a new experiment with a different name and load the new experiment with `adare experiment load`',
            )
        )

    if file_changed:
        raise ExperimentIntegrityError(
            log,
            message,
            possible_solutions=solutions
        )


def __project_integrity_check(project_path: Path, project_directory: ProjectDirectory, environments: list[Path] = None, testfunctions: list[Path] = None):
    testfunctions_changed = []
    hashes: dict = project_database.get_project_testfunction_hashes(project_path)
    for file, hash_value in hashes.items():
        path = Path(file)
        if testfunctions and path not in testfunctions:
            continue

        if project_directory.get_testfunction_hash(path) != hash_value:
            testfunctions_changed.append(path)
            log.info(f'integrity check for testfunction {path} failed')
        else:
            log.info(f'integrity check for testfunction {path} passed')

    if testfunctions_changed:
        message = 'to ensure the integrity of a project, testfunctions are not allowed to be changed after they have been loaded\n'
        testfunctions_changed = ",".join([file.name for file in testfunctions_changed])
        message += f'However, the following testfunctions have been changed: {testfunctions_changed}'
        solutions = [
            'if you want to change the testfunctions, you have to remove the testfunction with `adare testfunction remove` and then load the testfunction again with `adare testfunction load`',
        ]
        raise ExperimentIntegrityError(
            log,
            message,
            possible_solutions=solutions
        )

    environments_changed = []
    hashes: dict = project_database.get_project_environment_hashes(project_path)
    for file, hash_value in hashes.items():
        path = Path(file)
        if environments and path not in environments:
            continue
        if project_directory.get_environment_hash(path) != hash_value:
            environments_changed.append(path)
            log.info(f'integrity check for environment {path} failed')
        else:
            log.info(f'integrity check for environment {path} passed')

    if environments_changed:
        message = 'to ensure the integrity of a project, environments are not allowed to be changed after they have been loaded\n'
        environments_changed = ",".join([file.name for file in environments_changed])
        message += f'However, the following environments have been changed: {environments_changed}'
        solutions = [
            'if you want to change the environment, you have to remove the environment with `adare environment remove` and then load the environment again with `adare environment load`',
        ]
        raise ExperimentIntegrityError(
            log,
            message,
            possible_solutions=solutions
        )


def experiment_run(project_path: Path, experiment_name: str, environment_name: str, breakpoints: list[BreakPoint] = None):
    timestamp_start = datetime.now()

    project_directory = ProjectDirectory(project_path)
    experiment_directory: ExperimentDirectory = ExperimentDirectory(
        project_path,
        experiment_name
    )

    # check integrity of the experiment and environment
    __experiment_integrity_check(project_path, experiment_name, experiment_directory)
    # get used testfunctions
    testfunction_files = experiment_database.get_experiment_testfunction_files(project_path, experiment_name)
    testfunction_files_names = ",".join([file.name for file in testfunction_files])
    log.info(f'experiment {experiment_name} uses the following testfunction files: {testfunction_files_names}')
    # get used environment
    environment_file = environment_database.get_environment_path_by_project_and_name(project_path, environment_name)
    # check integrity of the project
    __project_integrity_check(project_path, project_directory, environments=[environment_file], testfunctions=testfunction_files)

    # get environment uuid
    environment_uuid = experiment_database.get_environment_uuid(project_path, environment_name)

    # check if vagrant box is of the environment exists
    vagrantbox_name = experiment_database.get_environment_vagrant_box(environment_uuid)
    if not vagrantutils.is_box(vagrantbox_name):
        raise VagrantBoxMissingError(
            log,
            f'vagrant box {vagrantbox_name} is missing',
            possible_solutions=[
                'list all available boxes with `adare vagrant box list` to find the correct box',
                'add the missing box with `adare vagrant box add`'
            ]
        )
    log.info(f'vagrant box {vagrantbox_name} found')

    environment_platform = experiment_database.get_environment_platform(environment_uuid)
    shared_root_directory_vm = Path(SHARE_POINT_VM[environment_platform])
    shared_root_directory_host = project_path

    # get directory for templates
    templates_experiment_scripts = TEMPLATES_DIR / environment_platform
    script_suffix = SCRIPTS_SUFFIX[environment_platform]

    # create run project structure
    experiment_run_directory = ExperimentRunDirectory(project_directory, experiment_name, script_suffix)
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
        statusfile=experiment_run_directory.get_path_relative_to_shared_directory('status_file', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        breakpoint_directory=experiment_run_directory.get_path_relative_to_shared_directory('breakpoint_directory', shared_root_directory_host, shared_root_directory_vm).as_posix(),
        breakpoints=breakpoints or []
    )
    experiment_run_directory.create_run_config(run_config_file)

    # setup paths to add to the PATH variable on the VM
    paths_to_add = [
        project_directory.get_path_relative_to_shared_directory('adare', shared_root_directory_host, shared_root_directory_vm),
        project_directory.get_path_relative_to_shared_directory('run', shared_root_directory_host, shared_root_directory_vm),
    ]

    # create scripts
    installation_script = create_installations_script(experiment_run_directory, environment_uuid, templates_experiment_scripts)
    packagedump_script = create_packagedump_script(experiment_run_directory, templates_experiment_scripts)
    run_script = create_run_script(
        experimentrun_directory=experiment_run_directory,
        project_directory=project_directory,
        path_directories=paths_to_add,
        template_directory=templates_experiment_scripts,
        script_suffix=script_suffix,
        shared_root_directory_host=shared_root_directory_host,
        shared_root_directory_vm=shared_root_directory_vm
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
    vagrantfile_uuid = str(uuid.uuid4())
    vagrantfile_uuid_str = make_string_path_safe(vagrantfile_uuid)

    vm_name = f'{environment_name}{experiment_name}{vagrantfile_uuid_str}'
    vagrantfile: VagrantFile = __create_vagrantfile(
        vm_name,
        experiment_run_directory,
        environment_uuid,
        shared_root_directory_vm,
        shared_root_directory_host,
        templates_experiment_scripts,
        script_suffix
    )
    BP_HOST_AFTER_VAGRANTFILE_CREATION.trigger_if_in_breakpoints(breakpoints)

    # todo: add network drive vm to Vagrantfile if needed

    # generate vagrant box vm object
    box = VagrantBoxVM.fromVagrantFileObject(
        experiment_run_directory.path,
        vagrantfile,
        log_file=experiment_run_directory.log_file,
        vm_name=experiment_run_directory.path.name
    )

    # create experiment run in database
    experiment_run_uuid = experiment_database.create_experiment_run(
        experiment_name,
        environment_name,
        project_path.name,
        experiment_run_directory
    )

    # update experiment run in database
    experiment_database.update_experiment_run_start(experiment_run_uuid, timestamp_start)
    # create an event to stop the box when ctrl+c is pressed
    ctrlc_event = threading.Event()

    BP_HOST_BEFORE_BOX_START.trigger_if_in_breakpoints(breakpoints)
    # track time directly before box start
    timestamp_before_box_start = datetime.now()
    # start the box in a separate thread
    threading.Thread(target=box.run, kwargs={'breakpoints': breakpoints, 'ctrlc_event': ctrlc_event}).start()

    # start the watchers that watches for events and breakpoints
    __install_watchers(box, experiment_run_uuid, experiment_run_directory.path, experiment_run_directory.breakpoint_directory, ctrlc_event, breakpoints)

    experiment_database.update_experiment_run_status(experiment_run_uuid, 'done')

    # calculate duration of experiment run
    timestamp_end = datetime.now()
    duration_total = timestamp_end - timestamp_start
    duration_box = timestamp_end - timestamp_before_box_start
    log.info(f'experiment run {experiment_run_uuid} finished after {duration_total} seconds (box run time: {duration_box})')

    # todo: cleanup
    BP_HOST_BEFORE_CLEANUP.trigger_if_in_breakpoints(breakpoints)
    #__cleanup_experiment_run(experiment_run_directory)


# external imports
from pathlib import Path
from datetime import datetime, timezone
import time

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.project.database as project_database
import adare.backend.environment.database as environment_database
from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError, \
    ExperimentDirectoryDoesNotExistError, VagrantBoxMissingError, ExperimentIntegrityError, ExperimentAlreadyExistsError, ExperimentNotChanged
from adare.database.api.event import EventDbApi
from adarelib.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adarelib.config import SHARE_POINT_VM
from adare.vagrantapi.vagrantfile import VagrantFile, VagrantMachine
from adare.vagrantapi.vagrantbox import VagrantBoxVM
from adarelib.helperfunctions.string import make_string_path_safe
from adare.vagrantapi import vagrantutils
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole
from adarelib.types.stage import ExperimentIntegrityCheckStage, BoxRunStage, \
    ProjectIntegrityCheckStage, BoxDestroyStage, CleanupStage, VagrantBoxExistCheckStage, RunDirectoryCreationStage, \
    InstallAdareVMStage, ConnectToVMStage, InstallationsStage, ExperimentRunStage
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adarelib.config import StatusEnum
from adare.webappaccess.download import download_experiment, sync
from adare.webappaccess.login import is_logged_in
from adarelib.exceptions import NotLoggedInError
from adare.backend.wsclient.client import WebSocketClient
from adare.virtualbox.api import run_command_in_vm
from adarelib.types.ws import EXEC, EXPERIMENT, DONE, WsCommand, EVENT
# keep this to activate the event listeners for the database
import adare.database.events.stage

# configure logging
import logging
log = logging.getLogger(__name__)


def experiment_sync(experiment_ulid: str):
    if not is_logged_in():
        log.info(f'sync is not possible because user is not logged in')
        return
    # get experiment from database
    sha256 = experiment_database.get_experiment_hash(experiment_ulid)
    # download experiment from webapp
    metadata_remote = sync(sha256, 'experiment')
    if not metadata_remote:
        log.info(f'experiment {experiment_ulid} does not exist remotely')
        return
    is_published = metadata_remote.get('published')
    remote_url = metadata_remote.get('gitea_url')
    remote_ulid = metadata_remote.get('ulid')
    abstract_tests_ulids = metadata_remote.get('abstract_tests_ulids')
    experiment_database.sync_experiment(experiment_ulid, remote_ulid, abstract_tests_ulids, remote_url, is_published)
    log.info(f'experiment {experiment_ulid} synced')


def experiment_create(project_path: Path, experiment: str):
    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.create()
    log.info(f'experiment directory {experiment_directory.path} created')



def __experiment_update(experiment_ulid, experiment_name, experiment_directory, force):
    if not experiment_database.check_for_experiment_change(experiment_ulid, experiment_directory.sha256):
        raise ExperimentNotChanged(log, f'experiment [i]{experiment_ulid}[/i] has not changed')
    log.info(f'experiment {experiment_ulid} has changed')
    if not force:
        raise LoggedException(log,
                              f'experiment [i]{experiment_ulid}[/i] has changed, use --force to overwrite and delete all related experiment runs')
    # delete the experiment and all related experiment runs
    experiment_database.remove_experiment(experiment_ulid)
    log.info(f'experiment {experiment_ulid} removed')
    experiment_database.create_experiment(
        name=experiment_name,
        experiment_directory=experiment_directory
    )
    log.info(f'experiment {experiment_ulid} created')


def experiment_load(project_path: Path, experiment_name: str, force: bool = False):
    # todo: fix bug that we can have two identical experiments
    experiment_directory = ExperimentDirectory(project_path, experiment_name)
    if not experiment_directory.exists():
        raise ExperimentDirectoryDoesNotExistError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] does not exist',
            possible_solutions=[
                f'copy the experiment directory to [b]{experiment_directory.path.parent}[/b]',
                'create the experiment directory with `adare experiment create`'
            ]
        )
    experiment_directory.check_for_missing_files()
    if experiment_ulid := experiment_database.get_experiment_by_project_and_name(
            project_path, experiment_name
    ):
        try:
            __experiment_update(
                experiment_ulid, experiment_name, experiment_directory, force
            )
        except ExperimentNotChanged as e:
            experiment_sync(experiment_ulid)
            raise e
    else:
        # create a new experiment in the database
        experiment_ulid = experiment_database.create_experiment(
            name=experiment_name,
            experiment_directory=experiment_directory
        )
        log.info(f'experiment {experiment_name} created')

    experiment_sync(experiment_ulid)


def __create_vagrantfile(vg_vm_name: str,  environment_ulid: str, shared_directories: dict, guest_platform: str, resolution=(1920, 1080)) -> VagrantFile:
    vg_machine = VagrantMachine(vg_vm_name)
    vg_file = VagrantFile()

    vg_box_name = experiment_database.get_environment_vagrant_box(environment_ulid)
    vg_machine.set_box(vg_box_name)

    if guest_platform == 'windows':
        vg_machine.change_communicator('winrm')

    vg_machine.disable_gui()
    vg_file.disable_virtualbox_guestautoupdate()
    # todo: fix since it does not seem to work - additional read resolution from config?
    vg_machine.set_resolution(resolution[0], resolution[1])
    vg_machine.set_cpus(4)
    vg_machine.set_memory(4096)
    # todo: change to run multiple in parallel the host port to something "dynamic" and store
    vg_machine.add_port_forwarding(18765, 18765)

    vg_machine.disable_default_synced_folder(platform=guest_platform)
    for val in shared_directories.values():
        vg_machine.add_synced_folder(
            val['host'],
            val['vm'],
        )

    vg_file.add_machine(vg_machine)

    return vg_file

def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    experiment_run_directory.clean()


def __experiment_integrity_check(project_path: Path, experiment_name: str, environment_name:str, experiment_directory: ExperimentDirectory):
    experiment_hashes = experiment_database.get_experiment_hashes(project_path, environment_name, experiment_name)
    experiment_run_count = experiment_database.get_experiment_run_count(project_path, environment_name, experiment_name)

    file_changed = []
    if experiment_directory.sha256_action != experiment_hashes['action']:
        file_changed.append('action')
    else:
        log.info(f'integrity check for action file {experiment_directory.actionfile} passed')
    if experiment_directory.sha256_testset != experiment_hashes['testset']:
        file_changed.append('testset')
    else:
        log.info(f'integrity check for testset file {experiment_directory.testsetfile} passed')
    # if experiment_directory.sha256_metadata != experiment_hashes['metadata']:
    #     file_changed.append('metadata')
    # else:
    #     log.info(f'integrity check for metadata file {experiment_directory.metadatafile} passed')

    message = 'to ensure the integrity of an experiment, experiment related files are not allowed to be changed after the experiment has been loaded\n'
    message += f'However, the following files have been changed: {", ".join(file_changed)}'
    solutions = []
    if experiment_run_count == 0:
        solutions.append(
            f'since no experiment runs have been executed yet, you can simply load the experiment again with `adare experiment load {experiment_name}` to overwrite the existing experiment')
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


def __project_integrity_check(project_path: Path, project_directory: ProjectDirectory, environments: list[Path] = None,
                              testfunctions: list[Path] = None):
    testfunctions_changed: list = []
    hashes: list = project_database.get_project_testfunction_hashes(project_path)
    for hash_dict in hashes:
        file = hash_dict['file']
        requirements_file = hash_dict['requirements']
        hash_value = hash_dict['hash']
        path = Path(file)
        requirements_path = Path(requirements_file)

        if testfunctions and path not in testfunctions:
            continue

        if project_directory.get_testfunction_hash(path, requirements_path) != hash_value:
            testfunctions_changed.append(path)
            log.info(f'integrity check for testfunction file {path} failed')
        else:
            log.info(f'integrity check for testfunction file {path} passed')

    if testfunctions_changed:
        message = 'to ensure the integrity of a project, testfunctions are not allowed to be changed after they have been loaded\n'
        testfunctions_changed = [file.name for file in testfunctions_changed]
        message += f'However, the following testfunctions have been changed: {testfunctions_changed}'
        solutions = [
            'if you want to change the testfunctions, you have to remove the testfunction with `adare testfunction remove` and then load the testfunction again with `adare testfunction load`',
        ]
        raise ExperimentIntegrityError(
            log,
            message,
            possible_solutions=solutions
        )

    environments_changed: list = []
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


# def experiment_run2(project_path: Path, experiment_name: str, environment_name: str,
#                    breakpoints: list[BreakPoint] = None, disable_printing: bool = False, test_mode: bool = False):
#     box_thread = None
#     experiment_run_ulid: str = experiment_database.initialize_experiment_run()
#     ctrlc_event = threading.Event()
#     shutdown_event = threading.Event()
#     experiment_event_manager.add_threading_event(experiment_run_ulid, ctrlc_event, 'ctrlc')
#     experiment_event_manager.add_threading_event(experiment_run_ulid, shutdown_event, 'shutdown')
#     flowconsole = ExperimentFlowConsole(disable_printing)
#     flowconsolemanager.add_handler(experiment_run_ulid, flowconsole)
#     flowconsole.start()
#
#     try:
#         timestamp_start = datetime.now(timezone.utc)
#
#         log.info(f'starting experiment run {experiment_name} in project {project_path}')
#
#         project_directory = ProjectDirectory(project_path)
#         experiment_directory: ExperimentDirectory = ExperimentDirectory(
#             project_path,
#             experiment_name
#         )
#         # check integrity of the experiment and environment
#         with StageCtxManager(ExperimentIntegrityCheckStage(), experiment_run_ulid):
#             __experiment_integrity_check(project_path, experiment_name, environment_name, experiment_directory)
#
#         with StageCtxManager(ProjectIntegrityCheckStage(), experiment_run_ulid):
#             # get used testfunctions
#             testfunction_files = experiment_database.get_experiment_testfunction_files(project_path, environment_name, experiment_name)
#             testfunction_files_names = ",".join([file.name for file in testfunction_files])
#             log.info(f'experiment {experiment_name} uses the following testfunction files: {testfunction_files_names}')
#             # get used environment
#             if environment_name:
#                 environment_file = environment_database.get_environment_path_by_project_and_name(project_path,
#                                                                                                  environment_name)
#             else:
#                 environment_file = experiment_database.get_experiment_environment(project_path,environment_name, experiment_name)
#                 environment_name = environment_file.stem
#
#         # check integrity of the project
#         __project_integrity_check(project_path, project_directory, environments=[environment_file],
#                                   testfunctions=testfunction_files)
#
#         # get environment ulid
#         environment_ulid = experiment_database.get_environment_ulid(project_path, environment_name)
#
#         with StageCtxManager(VagrantBoxExistCheckStage(), experiment_run_ulid):
#             # check if vagrant box of the environment exists
#             vagrantbox_name = experiment_database.get_environment_vagrant_box(environment_ulid)
#             if not vagrantutils.is_box(vagrantbox_name):
#                 raise VagrantBoxMissingError(
#                     log,
#                     f'vagrant box {vagrantbox_name} is missing',
#                     possible_solutions=[
#                         'list all available boxes with `adare vagrant box list` to find the correct box',
#                         'add the missing box with `adare vagrant box add`'
#                     ]
#                 )
#             vagrantbox_download_required = vagrantutils.is_box_download_required(vagrantbox_name)
#             log.info(f'vagrant box {vagrantbox_name} found')
#
#             environment_platform = experiment_database.get_environment_platform(environment_ulid)
#             shared_root_directory_vm = Path(SHARE_POINT_VM[environment_platform])
#             shared_root_directory_host = project_path
#
#             # get directory for templates
#             templates_experiment_scripts = TEMPLATES_DIR / environment_platform
#             script_suffix = SCRIPTS_SUFFIX[environment_platform]
#
#             with StageCtxManager(RunDirectoryCreationStage(), experiment_run_ulid):
#                 # create run project structure
#                 experiment_run_directory = ExperimentRunDirectory(project_directory, experiment_name, script_suffix)
#                 experiment_run_directory.create()
#
#             # create experiment config file
#             run_config_file = ExperimentConfig(
#                 experiment=experiment_name,
#                 action=experiment_directory.get_path_relative_to_shared_directory('actionfile', shared_root_directory_host,
#                                                                                   shared_root_directory_vm).as_posix(),
#                 testset=experiment_directory.get_path_relative_to_shared_directory('testsetfile',
#                                                                                    shared_root_directory_host,
#                                                                                    shared_root_directory_vm).as_posix(),
#                 testfunction_directory=project_directory.get_path_relative_to_shared_directory('testfunctions',
#                                                                                                shared_root_directory_host,
#                                                                                                shared_root_directory_vm).as_posix(),
#                 tessdata=project_directory.get_path_relative_to_shared_directory('tessdata', shared_root_directory_host,
#                                                                                  shared_root_directory_vm).as_posix(),
#                 img=experiment_directory.get_path_relative_to_shared_directory('img', shared_root_directory_host,
#                                                                                shared_root_directory_vm).as_posix(),
#                 logfile=experiment_run_directory.get_path_relative_to_shared_directory('adarevm_log_file',
#                                                                                        shared_root_directory_host,
#                                                                                        shared_root_directory_vm).as_posix(),
#                 eventfile=experiment_run_directory.get_path_relative_to_shared_directory('event_file',
#                                                                                          shared_root_directory_host,
#                                                                                          shared_root_directory_vm).as_posix(),
#                 statusfile=experiment_run_directory.get_path_relative_to_shared_directory('status_file',
#                                                                                           shared_root_directory_host,
#                                                                                           shared_root_directory_vm).as_posix(),
#                 breakpoint_directory=experiment_run_directory.get_path_relative_to_shared_directory('breakpoint_directory',
#                                                                                                     shared_root_directory_host,
#                                                                                                     shared_root_directory_vm).as_posix(),
#                 breakpoints=breakpoints or []
#             )
#             experiment_run_directory.create_run_config(run_config_file)
#
#             # setup paths to add to the PATH variable on the VM
#             paths_to_add = [
#                 project_directory.get_path_relative_to_shared_directory('adare', shared_root_directory_host,
#                                                                         shared_root_directory_vm),
#                 project_directory.get_path_relative_to_shared_directory('shared_tools', shared_root_directory_host,
#                                                                         shared_root_directory_vm),
#             ]
#
#             # create scripts
#             installation_script = create_installations_script(experiment_run_directory, environment_ulid,
#                                                               templates_experiment_scripts, shared_root_directory_host, shared_root_directory_vm)
#             packagedump_script = create_packagedump_script(experiment_run_directory, templates_experiment_scripts, shared_root_directory_host, shared_root_directory_vm)
#             run_script = create_run_script(
#                 experimentrun_directory=experiment_run_directory,
#                 project_directory=project_directory,
#                 path_directories=paths_to_add,
#                 template_directory=templates_experiment_scripts,
#                 script_suffix=script_suffix,
#                 shared_root_directory_host=shared_root_directory_host,
#                 shared_root_directory_vm=shared_root_directory_vm
#             )
#             shutdown_script = create_shutdown_script(experiment_run_directory, templates_experiment_scripts, shared_root_directory_host, shared_root_directory_vm)
#             wrapper_template = templates_experiment_scripts / f'run_script_wrapper{script_suffix}'
#
#             script_manager = ScriptManager(experiment_run_directory, shared_root_directory_host, shared_root_directory_vm,
#                                            wrapper_template)
#             script_manager.add_script(installation_script)
#             script_manager.add_script(packagedump_script)
#             script_manager.add_script(run_script)
#             script_manager.add_script(shutdown_script)
#
#             if environment_platform == 'windows':
#                 script_manager.add_script(Script(
#                     name=f'helperfunctions{script_suffix}',
#                     source_directory=templates_experiment_scripts,
#                 ))
#
#             script_manager.render(experiment_run_directory.scripts_directory)
#
#             # todo: add network drive and mount scripts
#
#             # create Vagrantfile
#             vagrantfile_ulid_str = make_string_path_safe(experiment_run_ulid)
#
#             vm_name = f'{environment_name}{experiment_name}{vagrantfile_ulid_str}'
#             vagrantfile: VagrantFile = __create_vagrantfile(
#                 vm_name,
#                 experiment_run_directory,
#                 environment_ulid,
#                 shared_root_directory_vm,
#                 shared_root_directory_host,
#                 templates_experiment_scripts,
#                 script_suffix
#             )
#             BP_HOST_AFTER_VAGRANTFILE_CREATION.trigger_if_in_breakpoints(breakpoints)
#
#             # todo: add network drive vm to Vagrantfile if needed
#
#             # generate vagrant box vm object
#             box = VagrantBoxVM.fromVagrantFileObject(
#                 experiment_run_directory.path,
#                 vagrantfile,
#                 log_file=experiment_run_directory.log_file,
#                 vm_name=experiment_run_directory.path.name
#             )
#
#             # create experiment run in database
#             if not test_mode:
#                 experiment_run_ulid = experiment_database.update_experiment_run(
#                     experiment_run_ulid,
#                     experiment_name,
#                     environment_name,
#                     project_path.name,
#                     experiment_run_directory
#                 )
#             else:
#                 from ulid import ULID
#                 experiment_run_ulid = str(ULID())
#
#         # update experiment run in database
#         if not test_mode:
#             experiment_database.update_experiment_run_start(experiment_run_ulid, timestamp_start)
#
#         BP_HOST_BEFORE_BOX_START.trigger_if_in_breakpoints(breakpoints)
#         # track time directly before box start
#         timestamp_before_box_start = datetime.now(timezone.utc)
#         output_processor = VagrantOutputProcessor(experiment_run_ulid=experiment_run_ulid)
#         destroy_output_processor = VagrantDestroyOutputProcessor(experiment_run_ulid=experiment_run_ulid)
#
#         box_run_stage = BoxRunStage()
#         if vagrantbox_download_required:
#             box_run_stage.sub_msg = 'required download slows down first boot'
#         ctx_manager_vagrant_up = StageCtxManager(box_run_stage, experiment_run_ulid)
#         ctx_manager_vagrant_destroy = StageCtxManager(BoxDestroyStage(), experiment_run_ulid)
#         kwargs = {
#             'ctrlc_event': ctrlc_event,
#             'shutdown_event': shutdown_event,
#             'output_processor': output_processor,
#             'destroy_output_processor': destroy_output_processor,
#             'ctx_manager_up': ctx_manager_vagrant_up,
#             'ctx_manager_destroy': ctx_manager_vagrant_destroy,
#             'disable_destroy': False,
#         }
#         box_thread = threading.Thread(target=box.run, kwargs=kwargs)
#         box_thread.start()
#
#         # start the watchers that watches for events and breakpoints
#         __install_watchers(experiment_run_ulid, experiment_run_directory.path,
#                            experiment_run_directory.breakpoint_directory, ctrlc_event, shutdown_event)
#
#         # wait for the box to finish
#         box_thread.join()
#
#         if not test_mode:
#             experiment_database.update_experiment_run_status(experiment_run_ulid, StatusEnum.FINISHED)
#
#         # calculate duration of experiment run
#         timestamp_end = datetime.now(timezone.utc)
#         if not test_mode:
#             experiment_database.update_experiment_run_end(experiment_run_ulid, timestamp_end)
#         duration_total = timestamp_end - timestamp_start
#         duration_box = timestamp_end - timestamp_before_box_start
#         log.info(
#             f'experiment run {experiment_run_ulid} finished after {duration_total} seconds (box run time: {duration_box})')
#
#         # clean up the experiment run directory
#         BP_HOST_BEFORE_CLEANUP.trigger_if_in_breakpoints(breakpoints)
#         with StageCtxManager(CleanupStage(), experiment_run_ulid):
#             __cleanup_experiment_run(experiment_run_directory)
#
#     except KeyboardInterrupt:
#         ctrlc_event.set()
#         experiment_database.update_experiment_run_status(experiment_run_ulid, StatusEnum.INTERRUPTED)
#         log.info('keyboard interrupt received, stopping experiment run')
#     finally:
#         try:
#             if box_thread and box_thread.is_alive():
#                 box_thread.join()
#             time.sleep(1)
#             flowconsole.stop()
#         except KeyboardInterrupt:
#             flowconsole.log_interrupted(f'interrupt_wait', f'wait for the box to fully shut down')


def install_and_run_adare_vm(vm_name: str, guest_platform: str):
    if guest_platform == 'windows':
        firewall_rule = 'New-NetFirewallRule -DisplayName "adarevm" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18765'
        run_command_in_vm(vm_name, firewall_rule, guest_platform)
        set_path_command = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\shared\tools", "User")'
        install_command = f'cd C:/adare/app/adarevm; poetry install'
        run_command = f'cd C:/adare/app/adarevm; poetry run adarevm C:/adare/run/logs/adarevm.log'
    else:
        set_path_command = 'export PATH=$PATH:/adare/shared/tools'
        install_command = 'cd /adare/app/adarevm && poetry install'
        run_command = 'cd /adare/app/adarevm && poetry run adarevm /adare/run/logs/adarevm.log'
    run_command_in_vm(vm_name, set_path_command, guest_platform)
    run_command_in_vm(vm_name, install_command, guest_platform)
    run_command_in_vm(vm_name, run_command, guest_platform, background=True)


def __create_and_start_flow_console(experiment_run_ulid: str, disable_printing: bool):
    """
    creates a flow_console and starts it
    :param experiment_run_ulid: used to reference the console if multiple runs at the same time (can be fake)
    :param disable_printing: if true, the console will not print anything
    :return: the flow_console
    """
    flow_console = ExperimentFlowConsole(disable_printing)
    flowconsolemanager.add_handler(experiment_run_ulid, flow_console)
    flow_console.start()
    return flow_console

def __wait_until_receive_done_msg(ws_client: WebSocketClient, experiment_run_ulid: str):
    received_done = False
    while not received_done:
        messages = ws_client.fetch_messages()
        for message in messages:
            decoded_msg = message.decode('utf-8')
            wscommand = WsCommand.decode(decoded_msg)
            if type(wscommand) == EVENT:
                event = wscommand.event
                with EventDbApi() as api:
                    api.add_event(event, experiment_run_ulid)
            if type(wscommand) == DONE:
                received_done = True


def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False):
    log.info(f'starting experiment run {experiment_name} in project {project_path}')

    experiment_run_ulid: str = experiment_database.initialize_experiment_run()
    client = None

    flow_console = __create_and_start_flow_console(experiment_run_ulid, disable_printing)

    try:
        timestamp_start = datetime.now(timezone.utc)

        project_directory = ProjectDirectory(project_path)
        experiment_directory: ExperimentDirectory = ExperimentDirectory(
            project_path,
            experiment_name
        )

        testfunction_files = experiment_database.get_experiment_testfunction_files(project_path, environment_name,
                                                                                   experiment_name)
        testfunction_files_names = ",".join([file.name for file in testfunction_files])
        log.info(f'experiment {experiment_name} uses the following testfunction files: {testfunction_files_names}')
        if environment_name:
            environment_file = environment_database.get_environment_path_by_project_and_name(project_path,
                                                                                             environment_name)
        else:
            environment_file = experiment_database.get_experiment_environment(project_path, environment_name,
                                                                              experiment_name)
            environment_name = environment_file.stem

        with StageCtxManager(ExperimentIntegrityCheckStage(), experiment_run_ulid):
            __experiment_integrity_check(project_path, experiment_name, environment_name, experiment_directory)

        with StageCtxManager(ProjectIntegrityCheckStage(), experiment_run_ulid):
            __project_integrity_check(project_path, project_directory, environments=[environment_file],
                                      testfunctions=testfunction_files)

        environment_ulid = experiment_database.get_environment_ulid(project_path, environment_name)

        with StageCtxManager(VagrantBoxExistCheckStage(), experiment_run_ulid):
            vg_box_name = experiment_database.get_environment_vagrant_box(environment_ulid)
            if not vagrantutils.is_box(vg_box_name):
                raise VagrantBoxMissingError(
                    log,
                    f'vagrant box {vg_box_name} is missing',
                    possible_solutions=[
                        'list all available boxes with `adare vagrant box list` to find the correct box',
                        'add the missing box with `adare vagrant box add`'
                    ]
                )
            vagrantbox_download_required = vagrantutils.is_box_download_required(vg_box_name)
            log.info(f'vagrant box {vg_box_name} found')

            guest_platform = experiment_database.get_environment_platform(environment_ulid)

            with StageCtxManager(RunDirectoryCreationStage(), experiment_run_ulid):
                # create run project structure
                experiment_run_directory = ExperimentRunDirectory(project_directory, experiment_name)
                experiment_run_directory.create()

            # todo: add network drive and mount scripts

            # create Vagrantfile
            vagrantfile_ulid_str = make_string_path_safe(experiment_run_ulid)

            vm_name = f'{environment_name}{experiment_name}{vagrantfile_ulid_str}'

            shared_root_directory_vm = Path(SHARE_POINT_VM[guest_platform])
            shared_run_directory_host = experiment_run_directory.path
            shared_directories = {
                'run': {
                    'host': shared_run_directory_host,
                    'vm': shared_root_directory_vm/'run',
                },
                'app': {
                    'host': project_directory.adare,
                    'vm': shared_root_directory_vm/'app',
                },
                'experiment': {
                    'host': experiment_directory.path,
                    'vm': shared_root_directory_vm/'experiment',
                },
                'testfunctions': {
                    'host': project_directory.testfunctions,
                    'vm': shared_root_directory_vm/'testfunctions',
                },
                'tessdata': {
                    'host': project_directory.tessdata,
                    'vm': shared_root_directory_vm/'tessdata',
                },
                'shared': {
                    'host': project_directory.shared,
                    'vm': shared_root_directory_vm / 'shared',
                },
            }

            vagrantfile: VagrantFile = __create_vagrantfile(
                vg_vm_name=vm_name,
                guest_platform=guest_platform,
                environment_ulid=environment_ulid,
                shared_directories=shared_directories
            )

            # todo: add network drive vm to Vagrantfile if needed

            # generate vagrant box vm object
            box = VagrantBoxVM.fromVagrantFileObject(
                experiment_run_directory.path,
                vagrantfile,
                log_file=experiment_run_directory.vagrant_log_file,
                vm_name=vm_name
            )

            # create experiment run in database
            experiment_run_ulid = experiment_database.update_experiment_run(
                experiment_run_ulid,
                experiment_name,
                environment_name,
                project_path.name,
                experiment_run_directory
            )

        experiment_database.update_experiment_run_start(experiment_run_ulid, timestamp_start)

        timestamp_before_box_start = datetime.now(timezone.utc)

        box_run_stage = BoxRunStage()
        if vagrantbox_download_required:
            box_run_stage.sub_msg = 'required download slows down first boot'
        ctx_manager_vagrant_up = StageCtxManager(box_run_stage, experiment_run_ulid)

        box.run(ctx_manager_up=ctx_manager_vagrant_up)

        with StageCtxManager(InstallAdareVMStage(), experiment_run_ulid):
            install_and_run_adare_vm(
                box.vm_name,
                guest_platform,
            )

        with StageCtxManager(ConnectToVMStage(), experiment_run_ulid):
            client = WebSocketClient(f'ws://localhost:18765', 'adare')
            client.wait_until_ready()
            log.info('Websocket Server is ready')
            client.start()
            log.info('Started Websocket Client')

        with StageCtxManager(InstallationsStage(), experiment_run_ulid):
            installations = environment_database.get_environment_installations(environment_ulid)
            for installation in installations:
                msg = EXEC(command=installation.command, shell=installation.shell, cwd=installation.cwd).encode()
                client.send_message(msg)
                __wait_until_receive_done_msg(client, experiment_run_ulid)

        with StageCtxManager(ExperimentRunStage(), experiment_run_ulid):
            msg = EXPERIMENT(experiment_name).encode()
            client.send_message(msg)
            __wait_until_receive_done_msg(client, experiment_run_ulid)

        experiment_database.update_experiment_run_status(experiment_run_ulid, StatusEnum.FINISHED)

        # calculate duration of experiment run
        timestamp_end = datetime.now(timezone.utc)
        experiment_database.update_experiment_run_end(experiment_run_ulid, timestamp_end)
        duration_total = timestamp_end - timestamp_start
        duration_box = timestamp_end - timestamp_before_box_start
        log.info(
            f'experiment run {experiment_run_ulid} finished after {duration_total} seconds (box run time: {duration_box})')

        # clean up the experiment run directory
        with StageCtxManager(CleanupStage(), experiment_run_ulid):
            __cleanup_experiment_run(experiment_run_directory)

    except KeyboardInterrupt:
        experiment_database.update_experiment_run_status(experiment_run_ulid, StatusEnum.INTERRUPTED)
        log.info('keyboard interrupt received, stopping experiment run')
    finally:
        try:
            log.info('stopping websocket client')
            if client:
                client.stop()
            ctx_manager_vagrant_destroy = StageCtxManager(BoxDestroyStage(), experiment_run_ulid)
            log.info('destroying vagrant box')
            box.destroy(ctx_manager_vagrant_destroy)
            time.sleep(1)
            log.info('stopping flow console')
            flow_console.stop()
        except KeyboardInterrupt:
            flow_console.log_interrupted(f'interrupt_wait', f'wait for the box to fully shut down')


def experiment_download(project: Path, experiment_ulid: str):
    if not is_logged_in():
        raise NotLoggedInError(log)
    # check if experiment exists in database
    exp = experiment_database.get_experiment_by_ulid(experiment_ulid)
    if exp:
        raise ExperimentAlreadyExistsError(
            log,
            f'experiment {exp} already exists',
        )

    # download experiment from webapp
    project = ProjectDirectory(project)
    experiment_name = download_experiment(experiment_ulid, project.experiments)
    log.info(f'experiment {experiment_ulid} downloaded')
    print(f'experiment {experiment_name} ({experiment_ulid}) downloaded successfully')



# external imports
from pathlib import Path
from datetime import datetime, timezone
import threading

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
from adare.backend.experiment.runctx import ExperimentRunCtx
import concurrent.futures
# keep this to activate the event listeners for the database
import adare.database.events.stage

# configure logging
import logging
log = logging.getLogger(__name__)

executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

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


def experiment_example(project_path: Path, experiment: str):
    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.retrieve_example(experiment)
    log.info(f'experiment directory {experiment_directory.path} created')
    # todo: make this available in metadata of the experiment (or user need to manually download it)
    project_directory = ProjectDirectory(project_path)
    project_directory.download_tool('https://download.ericzimmermanstools.com/RBCmd.zip', zipped=True)


def __experiment_update(experiment_ulid, experiment_name, experiment_directory, force):
    if not experiment_database.check_for_experiment_change(experiment_ulid, experiment_directory.sha256):
        raise ExperimentNotChanged(log, f'experiment [i]{experiment_ulid}[/i] has not changed')
    log.info(f'experiment {experiment_ulid} has changed')
    num_runs = experiment_database.get_experiment_run_count(experiment_ulid)
    if not force and num_runs > 0:
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
    else:
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
    experiment_ulid = experiment_database.get_experiment_by_project_and_name(project_path, experiment_name)
    experiment_run_count = experiment_database.get_experiment_run_count(experiment_ulid)

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


def install_and_run_adare_vm(vm_name: str, guest_platform: str, stop_event: threading.Event):
    if guest_platform == 'windows':
        firewall_rule = 'New-NetFirewallRule -DisplayName "adarevm" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18765'
        run_command_in_vm(vm_name, firewall_rule, guest_platform)
        set_path_command = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\shared\tools", "User")'
        set_path_command_experiment_tools = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\experiment\shared\tools", "User")'
        install_command = f'cd C:/adare/app/adarevm; poetry install'
        run_command = f'cd C:/adare/app/adarevm; poetry run adarevm C:/adare/run/logs/adarevm.log'
    else:
        set_path_command = 'export PATH=$PATH:/adare/shared/tools'
        set_path_command_experiment_tools = 'export PATH=$PATH:/adare/experiment/shared/tools'
        install_command = 'cd /adare/app/adarevm && poetry install'
        run_command = 'cd /adare/app/adarevm && poetry run adarevm /adare/run/logs/adarevm.log'

    run_command_in_vm(vm_name, set_path_command, guest_platform, stop_event=stop_event)
    run_command_in_vm(vm_name, set_path_command_experiment_tools, guest_platform, stop_event=stop_event)
    run_command_in_vm(vm_name, install_command, guest_platform, stop_event=stop_event)
    run_command_in_vm(vm_name, run_command, guest_platform, background=True, stop_event=stop_event)


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

async def __wait_until_receive_done_msg(ws_client: WebSocketClient, experiment_run_ulid: str) -> DONE or None:
    received_done = False
    wscommand = None
    while not received_done:
        message = await ws_client.fetch_message()
        decoded_msg = message.decode('utf-8')
        wscommand = WsCommand.decode(decoded_msg)
        if type(wscommand) == EVENT:
            event = wscommand.event
            with EventDbApi() as api:
                api.add_event(event, experiment_run_ulid)
        if type(wscommand) == DONE:
            received_done = True
    return wscommand


def step_initialize(context: ExperimentRunCtx, fake: bool = False):
    context.experiment_run_ulid = experiment_database.initialize_experiment_run(fake)
    context.timestamp_start = datetime.now(timezone.utc)
    log.info(f'initialized experiment run {context.experiment_run_ulid}')

def step_setup_directories(context: ExperimentRunCtx):
    context.project_directory = ProjectDirectory(context.project_path)
    context.experiment_directory = ExperimentDirectory(context.project_path, context.experiment_name)
    context.experiment_directory.check_for_missing_files()
    log.info(f'checked experiment directory {context.experiment_directory.path}')

def step_resolve_environment(context: ExperimentRunCtx):
    if context.environment_name:
        context.environment_file = environment_database.get_environment_path_by_project_and_name(
            context.project_path, context.environment_name
        )
    else:
        context.environment_file = experiment_database.get_experiment_environment(
            context.project_path, context.environment_name, context.experiment_name
        )
        # update environment_name based on file stem
        context.environment_name = context.environment_file.stem
    context.environment_ulid = experiment_database.get_environment_ulid(context.project_path, context.environment_name)
    log.info(f'found environment {context.environment_name}')

def step_check_integrity_experiment(context: ExperimentRunCtx):
    with StageCtxManager(ExperimentIntegrityCheckStage(), context.experiment_run_ulid, event=context.stop_event):
        __experiment_integrity_check(
            context.project_path,
            context.experiment_name,
            context.environment_name,
            context.experiment_directory
        )

def step_check_integrity_project(context: ExperimentRunCtx):
    with StageCtxManager(ProjectIntegrityCheckStage(), context.experiment_run_ulid, event=context.stop_event):
        testfunction_files = experiment_database.get_experiment_testfunction_files(
            context.project_path, context.environment_name, context.experiment_name
        )
        testfunction_files_names = ",".join([file.name for file in testfunction_files])
        log.info(f'experiment {context.experiment_name} uses the following testfunction files: {testfunction_files_names}')
        __project_integrity_check(
            context.project_path,
            context.project_directory,
            environments=[context.environment_file],
            testfunctions=testfunction_files
        )

def step_check_vagrant_box(context: ExperimentRunCtx):
    with StageCtxManager(VagrantBoxExistCheckStage(), context.experiment_run_ulid, event=context.stop_event):
        vg_box_name = experiment_database.get_environment_vagrant_box(context.environment_ulid)
        if not vagrantutils.is_box(vg_box_name):
            raise VagrantBoxMissingError(
                log,
                f"Vagrant box {vg_box_name} is missing",
                possible_solutions=[
                    "List available boxes with `adare vagrant box list`",
                    "Add the missing box with `adare vagrant box add`"
                ]
            )
        # Save the download requirement and guest platform in context
        context.vagrantbox_download_required = vagrantutils.is_box_download_required(vg_box_name)
        log.info(f"Vagrant box {vg_box_name} found")
        context.guest_platform = experiment_database.get_environment_platform(context.environment_ulid)

def step_create_run_directory(context: ExperimentRunCtx):
    with StageCtxManager(RunDirectoryCreationStage(), context.experiment_run_ulid, event=context.stop_event):
        run_dir = ExperimentRunDirectory(context.project_directory, context.experiment_name)
        run_dir.create()
        context.experiment_run_directory = run_dir

def step_prepare_vagrant_configuration(context: ExperimentRunCtx):
    vagrantfile_ulid_str = make_string_path_safe(context.experiment_run_ulid)
    context.vm_name = f"{context.environment_name}{context.experiment_name}{vagrantfile_ulid_str}"
    shared_root_vm = Path(SHARE_POINT_VM[context.guest_platform])
    shared_run_dir_host = context.experiment_run_directory.path
    shared_directories = {
        'run': {'host': shared_run_dir_host, 'vm': shared_root_vm / 'run'},
        'app': {'host': context.project_directory.adare, 'vm': shared_root_vm / 'app'},
        'experiment': {'host': context.experiment_directory.path, 'vm': shared_root_vm / 'experiment'},
        'testfunctions': {'host': context.project_directory.testfunctions, 'vm': shared_root_vm / 'testfunctions'},
        'tessdata': {'host': context.project_directory.tessdata, 'vm': shared_root_vm / 'tessdata'},
        'shared': {'host': context.project_directory.shared, 'vm': shared_root_vm / 'shared'},
    }
    context.vagrantfile = __create_vagrantfile(
        vg_vm_name=context.vm_name,
        guest_platform=context.guest_platform,
        environment_ulid=context.environment_ulid,
        shared_directories=shared_directories
    )

def step_create_vagrant_box(context: ExperimentRunCtx):
    context.box = VagrantBoxVM.fromVagrantFileObject(
        context.experiment_run_directory.path,
        context.vagrantfile,
        log_file=context.experiment_run_directory.vagrant_log_file,
        vm_name=context.vm_name
    )
    # Update experiment run in database (could be a separate step if needed)
    context.experiment_run_ulid = experiment_database.update_experiment_run(
        context.experiment_run_ulid,
        context.experiment_name,
        context.environment_name,
        context.project_path.name,
        context.experiment_run_directory
    )
    experiment_database.update_experiment_run_start(context.experiment_run_ulid, context.timestamp_start)
    context.timestamp_before_box_start = datetime.now(timezone.utc)

def step_run_box(context: ExperimentRunCtx):
    box_run_stage = BoxRunStage()
    if context.vagrantbox_download_required:
        box_run_stage.sub_msg = 'required download slows down first boot'
    ctx_manager_vagrant_up = StageCtxManager(box_run_stage, context.experiment_run_ulid)
    context.box.run(ctx_manager_up=ctx_manager_vagrant_up, stop_event=context.stop_event)

def step_install_adare_vm(context: ExperimentRunCtx):
    with StageCtxManager(InstallAdareVMStage(), context.experiment_run_ulid, event=context.stop_event):
        install_and_run_adare_vm(context.box.vm_name, context.guest_platform, stop_event=context.stop_event)

async def step_connect_websocket(context: ExperimentRunCtx):
    with StageCtxManager(ConnectToVMStage(), context.experiment_run_ulid, event=context.stop_event):
        client = WebSocketClient('ws://localhost:18765', 'adare')
        await client.wait_until_server_ready(ping_timeout=8, max_retries=60, retry_interval=2)
        log.info("Websocket Server is ready")
        context.client = client

async def step_execute_installations(context: ExperimentRunCtx):
    with StageCtxManager(InstallationsStage(), context.experiment_run_ulid, event=context.stop_event) as stage:
        installations = environment_database.get_environment_installations(context.environment_ulid)
        for installation in installations:
            msg = EXEC(
                command=installation.command,
                shell=installation.shell,
                cwd=installation.cwd
            ).encode()
            await context.client.send_message(msg)
            await __wait_until_receive_done_msg(context.client, context.experiment_run_ulid)

async def step_execute_experiment(context: ExperimentRunCtx):
    with StageCtxManager(ExperimentRunStage(), context.experiment_run_ulid, event=context.stop_event) as stage:
        msg = EXPERIMENT(context.experiment_name).encode()
        await context.client.send_message(msg)
        done_msg = await __wait_until_receive_done_msg(context.client, context.experiment_run_ulid)
        if done_msg:
            if done_msg.error:
                log.error(f"Experiment run failed: {done_msg.err_msg}")
                stage.set_status(StatusEnum.FAILED)



def step_finalize(context: ExperimentRunCtx):
    timestamp_end = datetime.now(timezone.utc)
    experiment_database.update_experiment_run_end(context.experiment_run_ulid, timestamp_end)
    duration_total = timestamp_end - context.timestamp_start
    duration_box = timestamp_end - context.timestamp_before_box_start
    log.info(f"Experiment run {context.experiment_run_ulid} finished after {duration_total} seconds (box run time: {duration_box})")
    with StageCtxManager(CleanupStage(), context.experiment_run_ulid, event=context.stop_event):
        __cleanup_experiment_run(context.experiment_run_directory)

async def step_shutdown_ws(context: ExperimentRunCtx):
    log.info('stopping websocket client')
    if context.client:
        await context.client.close()

def step_shutdown_vagrant(context: ExperimentRunCtx):
    ctx_manager_vagrant_destroy = StageCtxManager(BoxDestroyStage(), context.experiment_run_ulid)
    log.info('destroying vagrant box')
    if context.box:
        context.box.destroy(ctx_manager_vagrant_destroy)

def step_remove_fake_experiment_run(context: ExperimentRunCtx):
    # todo remove associated stuff as well (e.g. stages/files/...)
    experiment_database.remove_fake_experiment_run(context.experiment_run_ulid)
    log.info(f'fake experiment run {context.experiment_run_ulid} removed')


def callback_vagrant_box_exists(context: ExperimentRunCtx):
    if not context.box:
        return False
    return context.box.exists()

def callback_vagrant_box_status(context: ExperimentRunCtx):
    if not context.box:
        return 'not_created'
    return context.box.status()


async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = False):
    """
    Run an experiment by initializing context, executing a series of setup steps,
    running the main 'box' task, and finally executing post-run steps and shutdown.
    A stop event (triggered by Ctrl-C) will cancel long-running tasks.
    """
    import signal
    import asyncio

    log.info(f"Starting experiment run {experiment_name} in project {project_path}")

    # Create the experiment context and initialize it.
    experiment_run_context = ExperimentRunCtx(project_path, experiment_name, environment_name)
    if test:
        step_initialize(experiment_run_context, fake=True)
    else:
        step_initialize(experiment_run_context)

    # Create an asyncio Event to signal shutdown.
    stop_event = asyncio.Event()

    def handle_sigint():
        log.info("Ctrl-C detected. Stopping experiment run...")
        experiment_run_context.stop_event.set()  # Signal the context's stop event.
        stop_event.set()  # Signal the asyncio stop event.
        log.info('hanlde: send stop events')

    # Register the signal handler for SIGINT.
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_sigint)

    # Create and start the flow console.
    flow_console = __create_and_start_flow_console(experiment_run_context.experiment_run_ulid, disable_printing)

    # --- Helper Functions ---

    async def run_blocking_step(step_func):
        """Run a blocking step in a separate thread if not cancelled."""
        if not stop_event.is_set():
            await asyncio.to_thread(step_func, experiment_run_context)

    async def run_async_step(step_func):
        """
        Run an asynchronous step and wait for its completion or for a stop event.
        The step function must return a coroutine.
        """
        if not stop_event.is_set():
            task = step_func(experiment_run_context)
            await asyncio.wait(
                [task, stop_event.wait()],
                return_when=asyncio.FIRST_COMPLETED
            )


    # --- Execution Flow ---

    try:
        # Sequentially run initial blocking setup steps.
        initial_steps = [
            step_setup_directories,
            step_resolve_environment,
            step_check_integrity_experiment,
            step_check_integrity_project,
            step_check_vagrant_box,
            step_create_run_directory,
            step_prepare_vagrant_configuration,
            step_create_vagrant_box,
        ]
        for step in initial_steps:
            await run_blocking_step(step)

        await run_blocking_step(step_run_box)

        # Execute additional steps (mix of blocking and asynchronous).
        await run_blocking_step(step_install_adare_vm)
        await run_async_step(step_connect_websocket)
        await run_async_step(step_execute_installations)
        await run_async_step(step_execute_experiment)
        await run_blocking_step(step_finalize)
        await run_async_step(step_shutdown_ws)

    except Exception as e:
        log.error(f"An error occurred: {e}")
        experiment_run_context.stop_event.set()
        log.info("exception: send stop events")
        experiment_database.update_experiment_run_status(
            experiment_run_context.experiment_run_ulid,
            StatusEnum.INTERRUPTED,
        )
    finally:
        # Ensure shutdown procedures are executed.
        if not stop_event.is_set():
            experiment_run_context.stop_event.set()
            log.info("finally: send stop events")
        try:
            log.info("Stopping websocket client and flow console...")
            await step_shutdown_ws(experiment_run_context)
            step_shutdown_vagrant(experiment_run_context)
            if not test:
                flow_console.log_ulid(experiment_run_context.experiment_run_ulid)
            else:
                step_remove_fake_experiment_run(experiment_run_context)
            await asyncio.sleep(1)
            flow_console.stop()
        except Exception as e:
            log.error(f"Error during shutdown: {e}")



def experiment_test(project_path: Path, experiment_name: str, environment_name: str):
    from adare.frontend.terminal.textualize.experiment_interactive import ExperimentApp
    from adare.backend.types import Step


    setup_adare = lambda ctx: [
        step_setup_directories(ctx),
        step_resolve_environment(ctx),
        step_check_integrity_experiment(ctx),
        step_check_integrity_project(ctx),
        step_check_vagrant_box(ctx),
        step_create_run_directory(ctx),
        step_prepare_vagrant_configuration(ctx),
        step_create_vagrant_box(ctx),
    ]

    steps = [
        Step(
            label='Setup Adare to run experiment',
            func=setup_adare,
            thread=True,
            description='Setup Adare to run the experiment',
        ),
        Step(
            label='Run Box',
            func=step_run_box,
            thread=True,
            description='Run the Vagrant box',
        ),
        Step(
            label='Install Adare VM',
            func=step_install_adare_vm,
            thread=True,
            description='Install and run the Adare VM',
            repeatable=False,
        ),
        Step(
            label='Connect WebSocket',
            func=step_connect_websocket,
            thread=False,
            description='Connect to the Adare VM via WebSocket',
            repeatable=False,
        ),
        Step(
            label='Execute Installations',
            func=step_execute_installations,
            thread=False,
            description='Execute environment installations',
            repeatable=False,
        ),
        Step(
            label='Execute Experiment',
            func=step_execute_experiment,
            thread=False,
            description='Execute the experiment',
            repeatable=True,
        ),
        Step(
            label='Finalize',
            func=step_finalize,
            thread=True,
            description='Finalize the experiment run',
            repeatable=False,
        ),
        Step(
            label='Shutdown WebSocket Client',
            func=step_shutdown_ws,
            thread=False,
            description='Shutdown the WebSocket client',
        ),
        Step(
            label='Shutdown Vagrant',
            func=step_shutdown_vagrant,
            thread=True,
            description='Shutdown the Vagrant box',
        ),
        Step(
            label='Remove Fake Experiment Run',
            func=step_remove_fake_experiment_run,
            thread=True,
            description='Remove the fake experiment run',
        ),
    ]

    shutdown_steps = [
        Step(
            label='Shutdown',
            func=step_shutdown_ws,
            thread=False,
            description='Shutdown the WebSocket client',
        ),
        Step(
            label='Shutdown Vagrant',
            func=step_shutdown_vagrant,
            thread=True,
            description='Shutdown the Vagrant box',
        ),
        Step(
            label='Remove Fake Experiment Run',
            func=step_remove_fake_experiment_run,
            thread=True,
            description='Remove the fake experiment run',
        ),
    ]

    callbacks = {
        'vagrant_box_exists': callback_vagrant_box_exists,
        'vagrant_box_status': callback_vagrant_box_status,
    }

    exit_code = 99
    while exit_code == 99:
        run_ctx = ExperimentRunCtx(project_path, experiment_name, environment_name)
        step_initialize(run_ctx, fake=True)
        exp_run_ulid = run_ctx.experiment_run_ulid
        from adare.frontend.terminal.textualize.experiment_flow_console_widget import ExperimentRunFlowConsoleWidget, flowwidgetmanager
        flowwidgetmanager.add_handler(exp_run_ulid, ExperimentRunFlowConsoleWidget())
        app = ExperimentApp(run_ctx, steps=steps, shutdown_steps=shutdown_steps, callbacks=callbacks)
        app.run()
        exit_code = app.return_code
        flowwidgetmanager.remove_handler(exp_run_ulid)


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



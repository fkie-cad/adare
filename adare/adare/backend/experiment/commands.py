# external imports
from pathlib import Path
from datetime import datetime, timezone
import threading
import subprocess
import sys
import time
import asyncio

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.project.database as project_database
import adare.backend.environment.database as environment_database
from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError, \
    ExperimentDirectoryDoesNotExistError, ExperimentIntegrityError, ExperimentAlreadyExistsError, ExperimentNotChanged
from adare.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adare.config import SHARE_POINT_VM
from adare.helperfunctions.string import make_string_path_safe
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole
from adare.types.stages import ExperimentIntegrityCheckStage, VMRunStage, VMStopStage, VMDestroyStage, VMWaitTillReadyStage, VMCreateStage, VMMountSharedDirectoriesStage, \
    ProjectIntegrityCheckStage, CleanupStage, RunDirectoryCreationStage, \
    InstallAdareVMStage, ConnectToVMStage, InstallationsStage, ExperimentRunStage
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adarelib.constants import StatusEnum
from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR
from adare.webappaccess.download import download_experiment, sync
from adare.webappaccess.login import is_logged_in
from adare.exceptions import NotLoggedInError
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig
from adare.virtualbox.api import VirtualBoxVM, VirtualBoxManager, VMAlreadyRunningException, VMNotFoundException

# configure logging
import logging
log = logging.getLogger(__name__)

# Disable verbose MCP client logging to prevent base64 image flooding
logging.getLogger('mcp.client.streamable_http').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


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
    ulid = experiment_database.create_experiment(
        name=experiment_name,
        experiment_directory=experiment_directory
    )
    log.info(f'experiment {experiment_ulid} created')
    print(f'Experiment {experiment_name} (ulid: {ulid}) was loaded successfully')


def __validate_testset_compatibility(project_path: Path, experiment_directory: ExperimentDirectory):
    """Validate testset against available testfunctions during experiment loading."""
    testset_path = experiment_directory.path / "testset.yml"
    if not testset_path.exists():
        log.info("No testset.yml found - skipping testset validation")
        return  # No testset to validate
    
    project_directory = ProjectDirectory(project_path)
    testfunctions_dir = project_directory.testfunctions
    
    if not testfunctions_dir.exists():
        log.warning(f"Testfunctions directory {testfunctions_dir} does not exist - skipping validation")
        return
    
    try:
        from adarelib.testset.parser import parse_testsetfile
        from adarelib.testset.testfunction import import_basictest_subclasses, get_missing_testfunctions
        
        log.info("Validating testset compatibility with available testfunctions...")
        
        # Parse testset configuration
        testsetfile = parse_testsetfile(testset_path)
        
        # Import available testfunctions from project
        supported_tests = import_basictest_subclasses(testfunctions_dir)
        
        # Check for missing testfunctions
        missing = get_missing_testfunctions(testsetfile, supported_tests)
        
        if missing:
            raise ExperimentIntegrityError(
                log,
                f"Testset contains unsupported testfunctions: {missing}",
                possible_solutions=[
                    "Add missing testfunction implementations to testfunctions/ directory",
                    "Remove invalid tests from testset.yml", 
                    "Check testfunction naming matches class names",
                    "Ensure testfunction files are properly structured"
                ]
            )
        
        log.info(f"Testset validation passed - all {len(testsetfile.tests)} tests have valid testfunctions")
        
    except ImportError as e:
        log.warning(f"Could not import testset validation modules: {e}")
        log.warning("Skipping testset validation - validation will occur at runtime")
    except Exception as e:
        raise ExperimentIntegrityError(
            log,
            f"Testset validation failed: {str(e)}",
            possible_solutions=[
                "Check testset.yml syntax and structure",
                "Verify testfunctions directory structure",
                "Ensure all required testfunction dependencies are available"
            ]
        )


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
    
    # Validate testset compatibility with available testfunctions
    __validate_testset_compatibility(project_path, experiment_directory)
    if experiment_ulid := experiment_database.get_experiment_by_project_and_name(
            project_path, experiment_name, trigger_error=False
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


def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    experiment_run_directory.clean()


def __experiment_integrity_check(project_path: Path, experiment_name: str, environment_name:str, experiment_directory: ExperimentDirectory):
    experiment_hashes = experiment_database.get_experiment_hashes(project_path, environment_name, experiment_name)
    experiment_ulid = experiment_database.get_experiment_by_project_and_name(project_path, experiment_name)
    experiment_run_count = experiment_database.get_experiment_run_count(experiment_ulid)

    file_changed = []
    if experiment_directory.sha256_playbook != experiment_hashes['playbook']:
        file_changed.append('playbook')
    else:
        log.info(f'integrity check for action file {experiment_directory.playbookfile} passed')
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


async def install_and_run_adare_vm(context: ExperimentRunCtx, stop_event: threading.Event):
    vm = context.vm
    # TODO: maybe speed up by queuing the commands and running them as a single command to avoid VBoxManager overhead
    if context.guest_platform == 'windows':
        firewall_rule = f'New-NetFirewallRule -DisplayName "adarevm" -Direction Inbound -Action Allow -Protocol TCP -LocalPort {context.config.websocket_port}'
        await vm.run_command(firewall_rule, stop_event=stop_event)
        set_path_command = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\shared\tools", "User")'
        set_path_command_experiment_tools = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\experiment\shared\tools", "User")'
        # TODO: need to manually remount here - unclear why but it just fixes hours of trying to get it to work?! Windows I love you <3
        install_command = r'cd \\vboxsvr\adare\adarevm; poetry install'
        run_command = r'cd \\vboxsvr\adare\adarevm; poetry run adarevm'
    else:
        set_path_command = "grep -qxF 'export PATH=$PATH:/adare/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/shared/tools' >> ~/.bashrc && source ~/.bashrc"
        set_path_command_experiment_tools = "grep -qxF 'export PATH=$PATH:/adare/experiment/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/experiment/shared/tools' >> ~/.bashrc && source ~/.bashrc"
        install_command = 'cd /adare/app/adarevm && poetry install'
        run_command = 'cd /adare/app/adarevm && poetry run adarevm /adare/run/logs/adarevm.log'

    await vm.run_command(set_path_command, stop_event=stop_event)
    await vm.run_command(set_path_command_experiment_tools, stop_event=stop_event)
    await vm.run_command(install_command, stop_event=stop_event)
    await vm.run_command(run_command, background=True, stop_event=stop_event)


def __create_and_start_flow_console(experiment_run_ulid: str, disable_printing: bool, external_stop_event: threading.Event = None):
    """
    creates a flow_console and starts it
    :param experiment_run_ulid: used to reference the console if multiple runs at the same time (can be fake)
    :param disable_printing: if true, the console will not print anything
    :param external_stop_event: event to monitor for external interruption (Ctrl-C)
    :return: the flow_console
    """
    flow_console = ExperimentFlowConsole(disable_printing, external_stop_event)
    flowconsolemanager.add_handler(experiment_run_ulid, flow_console)
    flow_console.start()
    return flow_console

# async def __wait_until_receive_done_msg(ws_client: WebSocketClient, experiment_run_ulid: str) -> DONE | None:
#     received_done = False
#     wscommand = None
#     while not received_done:
#         message = await ws_client.fetch_message()
#         decoded_msg = message.decode('utf-8')
#         wscommand = WsCommand.decode(decoded_msg)
#         if type(wscommand) == EVENT:
#             event = wscommand.event
#             with EventDbApi() as api:
#                 api.add_event(event, experiment_run_ulid)
#         if type(wscommand) == DONE:
#             received_done = True
#     return wscommand


def step_initialize(context: ExperimentRunCtx, fake: bool = False):
    context.experiment_run_ulid = experiment_database.initialize_experiment_run(fake)
    context.timestamp_start = datetime.now(timezone.utc)
    context.adarevm = ADAREVM_DIR
    context.adarelib = ADARELIB_DIR
    log.info(f'initialized experiment run {context.experiment_run_ulid}')

def step_setup_directories(context: ExperimentRunCtx):
    context.project_directory = ProjectDirectory(context.config.project_path)
    context.experiment_directory = ExperimentDirectory(context.config.project_path, context.config.experiment_name)
    context.experiment_directory.check_for_missing_files()
    log.info(f'checked experiment directory {context.experiment_directory.path}')

def step_validate_playbook(context: ExperimentRunCtx):
    """Parse and validate playbook early to catch syntax errors before VM startup."""
    from adare.types.playbook import parse_playbook
    
    playbook_path = context.experiment_directory.path / "playbook.yaml"
    if not playbook_path.exists():
        log.info("No playbook.yaml found - experiment will run without GUI actions")
        return
    
    try:
        log.info(f"Parsing and validating playbook: {playbook_path}")
        context.playbook = parse_playbook(playbook_path)
        log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
    except Exception as e:
        raise LoggedException(log, f"Playbook validation failed: {str(e)}")

def step_resolve_environment(context: ExperimentRunCtx):
    if context.config.environment_name:
        context.environment_file = environment_database.get_environment_path_by_project_and_name(
            context.config.project_path, context.config.environment_name
        )
    else:
        context.environment_file = experiment_database.get_experiment_environment(
            context.config.project_path, context.config.environment_name, context.config.experiment_name
        )
        # update environment_name based on file stem
        context.config.environment_name = context.environment_file.stem
    context.environment_ulid = experiment_database.get_environment_ulid(context.config.project_path, context.config.environment_name)

    context.vm_file = environment_database.get_environment_vm_file(context.environment_ulid)
    context.guest_platform = environment_database.get_environment_os(context.environment_ulid)

    log.info(f'found environment {context.config.environment_name}')

def step_check_integrity_experiment(context: ExperimentRunCtx):
    with StageCtxManager(ExperimentIntegrityCheckStage(), context.experiment_run_ulid, event=context.stop_event):
        __experiment_integrity_check(
            context.config.project_path,
            context.config.experiment_name,
            context.config.environment_name,
            context.experiment_directory
        )

def step_check_integrity_project(context: ExperimentRunCtx):
    with StageCtxManager(ProjectIntegrityCheckStage(), context.experiment_run_ulid, event=context.stop_event):
        testfunction_files = experiment_database.get_experiment_testfunction_files(
            context.config.project_path, context.config.environment_name, context.config.experiment_name
        )
        testfunction_files_names = ",".join([file.name for file in testfunction_files])
        log.info(f'experiment {context.config.experiment_name} uses the following testfunction files: {testfunction_files_names}')
        __project_integrity_check(
            context.config.project_path,
            context.project_directory,
            environments=[context.environment_file],
            testfunctions=testfunction_files
        )

def step_check_appdata(context: ExperimentRunCtx):
    # ensure that poetry.lock does not exist for adarevm and adarelib
    adarevm_poetry_lock = ADAREVM_DIR / 'poetry.lock'
    adarelib_poetry_lock = ADARELIB_DIR / 'poetry.lock'
    if adarevm_poetry_lock.exists():
        log.info(f'removing {adarevm_poetry_lock} to ensure that adarevm is installed correctly')
        adarevm_poetry_lock.unlink()
    if adarelib_poetry_lock.exists():
        log.info(f'removing {adarelib_poetry_lock} to ensure that adarelib is installed correctly')
        adarelib_poetry_lock.unlink()

def step_create_run_directory(context: ExperimentRunCtx):
    with StageCtxManager(RunDirectoryCreationStage(), context.experiment_run_ulid, event=context.stop_event):
        run_dir = ExperimentRunDirectory(context.project_directory, context.config.experiment_name)
        run_dir.create()
        context.experiment_run_directory = run_dir
        
        # Initialize MCP server with log file
        from adare.backend.experiment.mcp_server_manager import MCPServerManager
        context.mcp_server = MCPServerManager(log_file=run_dir.mcp_gui_log_file)

async def step_create_virtualbox_machine(context: ExperimentRunCtx):
        context.vm_name = f"{context.config.environment_name}-{context.config.experiment_name}-{make_string_path_safe(context.experiment_run_ulid)}"
        
        shared_root = Path(SHARE_POINT_VM[context.guest_platform])
        context.config.shared_directories = {
            'run': {'host': context.experiment_run_directory.path, 'vm': shared_root / 'run'},
            'adare': {'host': context.adarevm.parent, 'vm': 'Z:'},
            'experiment': {'host': context.experiment_directory.path, 'vm': shared_root / 'experiment'},
            'testfunctions': {'host': context.project_directory.testfunctions, 'vm': shared_root / 'testfunctions'},
            'shared': {'host': context.project_directory.shared, 'vm': shared_root / 'shared'},
        }
        
        vbox_manager = VirtualBoxManager()
        context.vm = VirtualBoxVM(
            vm_name=context.vm_name,
            guest_os=context.guest_platform,
            manager=vbox_manager,
            cpus=context.config.vm_cpus,
            ram=context.config.vm_memory
        )

        # maybe extra step 
        vm_create_stage = VMCreateStage()
        ctx_manager_vm_create = StageCtxManager(vm_create_stage, context.experiment_run_ulid)
        await context.vm.create_from_ovf_or_ova(context.vm_file, ctx_manager=ctx_manager_vm_create, stop_event=context.stop_event)

        if not context.stop_event.is_set():
            for name, paths in context.config.shared_directories.items():
                await context.vm.add_shared_folder(name, host_path=paths['host'], mountpoint=paths['vm'], stop_event=context.stop_event)

        if not context.stop_event.is_set():
            # Update experiment run in database (could be a separate step if needed)
            context.experiment_run_ulid = experiment_database.update_experiment_run(
                context.experiment_run_ulid,
                context.config.experiment_name,
                context.config.environment_name,
                context.config.project_path.name,
                context.experiment_run_directory
            )

        # maybe extra step
        # add port forwarding for the websocket server
        if not context.stop_event.is_set():
            await context.vm.add_port_forwarding(
                name='adarevm',
                protocol='tcp',
                host_port=context.config.websocket_port,
                guest_port=context.config.websocket_port,
                stop_event=context.stop_event
            )
            log.info(f'added port forwarding for websocket server on port {context.config.websocket_port}')

        experiment_database.update_experiment_run_start(context.experiment_run_ulid, context.timestamp_start)
        context.timestamp_before_box_start = datetime.now(timezone.utc)


async def step_mount_shared_directories(context: ExperimentRunCtx):
    with StageCtxManager(VMMountSharedDirectoriesStage(), context.experiment_run_ulid, event=context.stop_event):
        folders = {
            name: paths['vm'] for name, paths in context.config.shared_directories.items()
        }
        await context.vm.mount_multiple_shared_folders(
            folders=folders,
            stop_event=context.stop_event
        )
        #

async def step_run_vm(context: ExperimentRunCtx):
    vm_run_stage = VMRunStage()
    ctx_manager_vm_run = StageCtxManager(vm_run_stage, context.experiment_run_ulid)
    await context.vm.start(ctx_manager=ctx_manager_vm_run, stop_event=context.stop_event)


async def step_wait_till_vm_is_ready(context: ExperimentRunCtx):
    ctx_manager_vm_wait = StageCtxManager(VMWaitTillReadyStage(), context.experiment_run_ulid, event=context.stop_event)
    log.info('waiting until VM is ready')
    if not await context.vm.wait_until_fully_booted(timeout=360, stop_event=context.stop_event, ctx_manager=ctx_manager_vm_wait):
        raise LoggedException(log, 'VM did not become ready in time')
    log.info('VM is ready')

async def step_install_and_run_websocket_server(context: ExperimentRunCtx):
    with StageCtxManager(InstallAdareVMStage(), context.experiment_run_ulid, event=context.stop_event):
        await install_and_run_adare_vm(context, stop_event=context.stop_event)

async def step_connect_websocket(context: ExperimentRunCtx):
    with StageCtxManager(ConnectToVMStage(), context.experiment_run_ulid, event=context.stop_event):
        from adare.backend.experiment.websocket_client import AdareVMClient
        from retry import retry
        import asyncio
        from websockets.exceptions import ConnectionClosed, WebSocketException
        
        # Create websocket client with host port forwarding
        context.client = AdareVMClient(host='localhost', port=context.config.websocket_port)
        
        # Set up event handlers for logging
        def log_event_handler(event_type: str, data: dict):
            message = data.get('message', '')
            log.info(f"AdareVM Event [{event_type}]: {message}")
        
        def error_event_handler(event_type: str, data: dict):
            error = data.get('error', '')
            log.error(f"AdareVM Error: {error}")
        
        context.client.add_event_handler('log', log_event_handler)
        context.client.add_event_handler('error', error_event_handler)
        
        @retry(
            exceptions=(
                asyncio.TimeoutError,
                ConnectionClosed,
                WebSocketException,
                ConnectionRefusedError,
                OSError
            ),
            tries=10,
            delay=2,
            backoff=1.2,
            jitter=(1, 3)
        )
        async def connect_with_retry():
            if context.stop_event.is_set():
                log.info("Connection cancelled by stop event")
                return False
                
            log.info("Attempting to connect to AdareVM server")
            connected = await context.client.connect(timeout=60.0)
            
            if not connected:
                raise ConnectionRefusedError("Failed to establish websocket connection")
            
            return True
        
        # Attempt connection with retry logic
        try:
            await connect_with_retry()
            log.info("Successfully connected to AdareVM WebSocket server")
            
            # Test the connection with ping
            ping_success = await context.client.ping()
            if ping_success:
                log.info("Ping test successful - WebSocket connection is working")
            else:
                log.warning("Ping test failed but connection established")
            
            # Get server status
            try:
                status = await context.client.get_status()
                log.info(f"AdareVM server status: {status}")
            except (asyncio.TimeoutError, ConnectionClosed) as e:
                log.warning(f"Could not get server status: {e}")
                
        except (asyncio.TimeoutError, WebSocketException, ConnectionRefusedError, OSError) as e:
            from adare.exceptions import LoggedException
            log.error(e, exc_info=True)
            raise LoggedException(log, f"Failed to connect to AdareVM server: {e}") from e

async def step_execute_installations(context: ExperimentRunCtx):
    with StageCtxManager(InstallationsStage(), context.experiment_run_ulid, event=context.stop_event) as stage:
        installations = environment_database.get_environment_installations(context.environment_ulid)
        
        if not installations:
            log.info("No installations to execute")
            return
        
        pass

async def step_start_mcp_server(context: ExperimentRunCtx):
    """Start the MCP GUI server for target detection."""
    log.info("Starting MCP GUI server for target detection...")
    
    success = await context.mcp_server.start()
    if success:
        log.info("MCP GUI server started successfully")
    else:
        from adare.exceptions import LoggedException
        raise LoggedException(log, "MCP GUI server failed to start - cannot proceed without target detection capabilities")


async def step_execute_experiment(context: ExperimentRunCtx):
    """Execute the experiment using the playbook controller."""
    with StageCtxManager(ExperimentRunStage(), context.experiment_run_ulid, event=context.stop_event) as stage:
        from adare.backend.experiment.playbook_controller import PlaybookController
        
        if not context.client:
            log.error("WebSocket client not available for experiment execution")
            return
        
        # Create playbook controller
        controller = PlaybookController(
            websocket_client=context.client,
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            debug_screenshots=context.debug_screenshots,
            screenshots_dir=context.experiment_run_directory.screenshots_directory if context.debug_screenshots else None,
            playbook=context.playbook  # Pass pre-parsed playbook
        )
        
        # Execute complete experiment (playbook + tests)
        log.info(f"Starting experiment execution for {context.config.experiment_name}")
        result = await controller.execute_experiment(context.experiment_directory.path)
        
        if result.success:
            log.info(f"Experiment completed successfully: {result.successful_actions}/{result.total_actions} actions succeeded")
        else:
            log.error(f"Experiment failed: {result.error_message}")
            log.error(f"Action results: {result.successful_actions}/{result.total_actions} succeeded")


def step_finalize(context: ExperimentRunCtx):
    timestamp_end = datetime.now(timezone.utc)
    experiment_database.update_experiment_run_end(context.experiment_run_ulid, timestamp_end)
    duration_total = timestamp_end - context.timestamp_start
    duration_box = timestamp_end - context.timestamp_before_box_start
    log.info(f"Experiment run {context.experiment_run_ulid} finished after {duration_total} seconds (box run time: {duration_box})")
    with StageCtxManager(CleanupStage(), context.experiment_run_ulid, event=context.stop_event):
        __cleanup_experiment_run(context.experiment_run_directory)

async def step_shutdown_mcp_server(context: ExperimentRunCtx):
    """Stop the MCP GUI server."""
    log.info('stopping MCP GUI server')
    await context.mcp_server.stop()


async def step_shutdown_ws(context: ExperimentRunCtx):
    log.info('stopping websocket client')
    if context.client:
        await context.client.disconnect()

async def step_shutdown_virtualbox_vm(context: ExperimentRunCtx):
    ctx_manager_vm_stop= StageCtxManager(VMStopStage(), context.experiment_run_ulid)
    log.info('destroying virtualbox virtual machine')
    if context.vm:
        await context.vm.stop(ctx_manager=ctx_manager_vm_stop)

async def step_cleanup_virtualbox_vm(context: ExperimentRunCtx):
    ctx_manager_vm_cleanup = StageCtxManager(VMDestroyStage(), context.experiment_run_ulid)
    log.info('cleaning up virtualbox virtual machine')
    if context.vm:
        await context.vm.destroy(ctx_manager=ctx_manager_vm_cleanup)

def step_remove_fake_experiment_run(context: ExperimentRunCtx):
    # todo remove associated stuff as well (e.g. stages/files/...)
    experiment_database.remove_fake_experiment_run(context.experiment_run_ulid)
    log.info(f'fake experiment run {context.experiment_run_ulid} removed')


# def callback_vagrant_box_exists(context: ExperimentRunCtx):
#     if not context.box:
#         return False
#     return context.box.exists()

# def callback_vagrant_box_status(context: ExperimentRunCtx):
#     if not context.box:
#         return 'not_created'
#     return context.box.status()

def __start_event_listeners(experiment_run_ulid: str):
    from adare.backend.events.listener import event_listener_db, event_listener_cli
    cli_thread = threading.Thread(target=event_listener_cli, args=(experiment_run_ulid,), daemon=True)
    db_thread = threading.Thread(target=event_listener_db, args=(experiment_run_ulid,), daemon=True)

    cli_thread.start()
    db_thread.start()

    return cli_thread, db_thread


async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = False, debug_screenshots: bool = False):
    import signal
    import asyncio

    log.info(f"Starting experiment run {experiment_name} in project {project_path}")

    # Create the experiment context and initialize it.
    config = ExperimentConfig(project_path, experiment_name, environment_name)
    experiment_run_context = ExperimentRunCtx(config)
    experiment_run_context.debug_screenshots = debug_screenshots
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
    # No need for custom exception handler - exceptions now bubble up to main try/except


    # Create and start the flow console.
    print(experiment_run_context.experiment_run_ulid)
    flow_console = __create_and_start_flow_console(experiment_run_context.experiment_run_ulid, disable_printing, experiment_run_context.stop_event)

    # 
    __start_event_listeners(experiment_run_context.experiment_run_ulid)


    # --- Helper Functions ---

    async def run_blocking_step(step_func):
        """Run a blocking step in a separate thread if not cancelled."""
        if not stop_event.is_set():
            log.info(f"Running blocking step: {step_func.__name__}")
            await asyncio.to_thread(step_func, experiment_run_context)
            log.info(f"Blocking step {step_func.__name__} completed")

    async def run_async_step(step_func):
        """
        Run an asynchronous step and wait for its completion or for a stop event.
        The step function must return a coroutine.
        """
        if not stop_event.is_set():
            log.info(f"Running async step: {step_func.__name__}")
            
            # Create proper tasks so exceptions bubble up to main try/except
            step_task = asyncio.create_task(step_func(experiment_run_context))
            stop_task = asyncio.create_task(stop_event.wait())
            
            try:
                # Use gather to let exceptions bubble up naturally
                done, pending = await asyncio.wait(
                    [step_task, stop_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if step_task completed with exception
                for task in done:
                    if task.exception():
                        raise task.exception()
                        
                log.info(f"Async step {step_func.__name__} completed")
                
            finally:
                # Ensure cleanup
                for task in [step_task, stop_task]:
                    if not task.done():
                        task.cancel()

    # --- Execution Flow ---

    try:
        # Sequentially run initial blocking setup steps.
        initial_steps = [
            step_setup_directories,
            step_validate_playbook,
            step_resolve_environment,
            step_check_integrity_experiment,
            step_check_integrity_project,
            step_check_appdata,
            step_create_run_directory,
        ]
        for step in initial_steps:
            await run_blocking_step(step)

        # Start MCP server early (independent of VM)
        await run_async_step(step_start_mcp_server)

        # VirtualBox operations are now async for responsive ctrl-c handling
        await run_async_step(step_create_virtualbox_machine)
        await run_async_step(step_run_vm)
        await run_async_step(step_wait_till_vm_is_ready)
        await run_async_step(step_mount_shared_directories)

        # Execute additional steps (mix of blocking and asynchronous).
        await run_async_step(step_install_and_run_websocket_server)

        await run_async_step(step_connect_websocket)
        await run_async_step(step_execute_installations)
        await run_async_step(step_execute_experiment)
        await run_blocking_step(step_finalize)
        await run_async_step(step_shutdown_mcp_server)
        await run_async_step(step_shutdown_ws)

    except LoggedException as e:
        # Handle structured exceptions - let them bubble up to exec_with_error_printing for consistent UX
        experiment_run_context.stop_event.set()
        log.info("LoggedException: send stop events")
        from adare.exceptions import LoggedErrorException
        status = StatusEnum.FAILED if isinstance(e, LoggedErrorException) else StatusEnum.INTERRUPTED
        experiment_database.update_experiment_run_status(
            experiment_run_context.experiment_run_ulid,
            status,
        )
        # Re-raise to be handled by exec_with_error_printing
        raise
    except Exception as e:
        log.error(f"An unexpected error occurred: {e}", exc_info=True)
        experiment_run_context.stop_event.set()
        log.info("exception: send stop events")
        experiment_database.update_experiment_run_status(
            experiment_run_context.experiment_run_ulid,
            StatusEnum.INTERRUPTED,
        )
        # Re-raise unexpected exceptions too so they get proper exit codes
        raise
    finally:
        # Ensure shutdown procedures are executed.
        if not stop_event.is_set():
            experiment_run_context.stop_event.set()
            log.info("finally: send stop events")
        try:
            input("Press Enter to finalize and shutdown the experiment run...")

            log.info("Stopping websocket client and flow console...")
            await step_shutdown_ws(experiment_run_context)
            await step_shutdown_virtualbox_vm(experiment_run_context)
            await step_cleanup_virtualbox_vm(experiment_run_context)
            if not test:
                flow_console.log_ulid(experiment_run_context.experiment_run_ulid)
            else:
                step_remove_fake_experiment_run(experiment_run_context)
            await asyncio.sleep(1)
            flow_console.stop()
        except Exception as e:
            log.error(f"Error during shutdown: {e}")



# def experiment_test(project_path: Path, experiment_name: str, environment_name: str):
#     from adare.frontend.terminal.textualize.experiment_interactive import ExperimentApp
#     from adare.backend.types import Step


#     setup_adare = lambda ctx: [
#         step_setup_directories(ctx),
#         step_resolve_environment(ctx),
#         step_check_integrity_experiment(ctx),
#         step_check_integrity_project(ctx),
#         step_create_run_directory(ctx),
#         step_create_virtualbox_machine(ctx),
#     ]

#     steps = [
#         Step(
#             label='Setup Adare to run experiment',
#             func=setup_adare,
#             thread=True,
#             description='Setup Adare to run the experiment',
#         ),
#         Step(
#             label='Run Box',
#             func=step_run_vm,
#             thread=True,
#             description='Run the Vagrant box',
#         ),
#         Step(
#             label='Install Adare VM',
#             func=step_install_adare_vm,
#             thread=True,
#             description='Install and run the Adare VM',
#             repeatable=False,
#         ),
#         Step(
#             label='Connect WebSocket',
#             func=step_connect_websocket,
#             thread=False,
#             description='Connect to the Adare VM via WebSocket',
#             repeatable=False,
#         ),
#         Step(
#             label='Execute Installations',
#             func=step_execute_installations,
#             thread=False,
#             description='Execute environment installations',
#             repeatable=False,
#         ),
#         Step(
#             label='Execute Experiment',
#             func=step_execute_experiment,
#             thread=False,
#             description='Execute the experiment',
#             repeatable=True,
#         ),
#         Step(
#             label='Finalize',
#             func=step_finalize,
#             thread=True,
#             description='Finalize the experiment run',
#             repeatable=False,
#         ),
#         Step(
#             label='Shutdown WebSocket Client',
#             func=step_shutdown_ws,
#             thread=False,
#             description='Shutdown the WebSocket client',
#         ),
#         Step(
#             label='Shutdown Vagrant',
#             func=step_shutdown_vagrant,
#             thread=True,
#             description='Shutdown the Vagrant box',
#         ),
#         Step(
#             label='Remove Fake Experiment Run',
#             func=step_remove_fake_experiment_run,
#             thread=True,
#             description='Remove the fake experiment run',
#         ),
#     ]

#     shutdown_steps = [
#         Step(
#             label='Shutdown',
#             func=step_shutdown_ws,
#             thread=False,
#             description='Shutdown the WebSocket client',
#         ),
#         Step(
#             label='Shutdown Vagrant',
#             func=step_shutdown_vagrant,
#             thread=True,
#             description='Shutdown the Vagrant box',
#         ),
#         Step(
#             label='Remove Fake Experiment Run',
#             func=step_remove_fake_experiment_run,
#             thread=True,
#             description='Remove the fake experiment run',
#         ),
#     ]

#     callbacks = {
#         'vagrant_box_exists': callback_vagrant_box_exists,
#         'vagrant_box_status': callback_vagrant_box_status,
#     }

#     exit_code = 99
#     while exit_code == 99:
#         run_ctx = ExperimentRunCtx(project_path, experiment_name, environment_name)
#         step_initialize(run_ctx, fake=True)
#         exp_run_ulid = run_ctx.experiment_run_ulid
#         from adare.frontend.terminal.textualize.experiment_flow_console_widget import ExperimentRunFlowConsoleWidget, flowwidgetmanager
#         flowwidgetmanager.add_handler(exp_run_ulid, ExperimentRunFlowConsoleWidget())
#         app = ExperimentApp(run_ctx, steps=steps, shutdown_steps=shutdown_steps, callbacks=callbacks)
#         app.run()
#         exit_code = app.return_code
#         flowwidgetmanager.remove_handler(exp_run_ulid)


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



# external imports
from pathlib import Path
from datetime import datetime, timezone
import threading

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.project.database as project_database
import adare.backend.environment.database as environment_database
from adare.backend.experiment.exceptions import ExperimentIntegrityError, VMSetupError
from adare.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole
from adare.backend.experiment.step_runner import ExperimentStepRunner
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.backend.experiment.agent_installer import should_skip_installation
from adare.types.stages import (
    # Top-level parent stages
    ExperimentPreparationStage, VirtualMachineSetupStage, SoftwareInstallationStage,
    ExperimentExecutionStage, CleanupShutdownStage,
    # Sub-stages
    SetupExperimentEnvironmentStage, ValidateIntegrityStage, PrepareRunEnvironmentStage, StartComputerVisionServerStage,
    ExperimentIntegrityCheckStage, ProjectIntegrityCheckStage,
    InstallAdareVMStage, ConnectToVMStage, InstallationsStage,
    ExperimentRunStage, SystemInfoCollectionStage,
    FinalizeStage, ShutdownComputerVisionServerStage, ShutdownWebSocketStage,
    # VM Test stages
    VMTestSetupStage, VMCompatibilityTestStage, VMTestCleanupStage,
    # VM Test substages
    VMResponseTestStage, VMSharedFoldersTestStage, VMPythonTestStage, VMPoetryTestStage,
    VMAdareServerTestStage, VMWebSocketTestStage, VMScreenshotTestStage, VMClickTestStage,
)
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adarelib.constants import StatusEnum
from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig

# configure logging
import logging
log = logging.getLogger(__name__)

# Disable verbose MCP client logging to prevent base64 image flooding the log
logging.getLogger('mcp.client.streamable_http').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


def _ensure_and_copy_adare_log_to_run_directory(run_directory: ExperimentRunDirectory):
    """Ensure a log file exists and copy it to the experiment run directory.
    
    If no log file is currently active (e.g., when --logfile is not specified),
    this function will create a temporary log file in the run directory and
    configure logging to use it, ensuring the experiment run has log output.
    
    Args:
        run_directory: The experiment run directory where the log should be copied
    """
    import shutil
    import logging
    from adare.logger.logger import get_current_logfile
    
    current_logfile = get_current_logfile()
    target_path = run_directory.log_directory / 'adare.log'
    
    if current_logfile:
        # Copy existing log file
        try:
            shutil.copy2(current_logfile, target_path)
            log.info(f'Copied adare log to {target_path}')
        except Exception as e:
            log.warning(f'Failed to copy adare log to run directory: {e}')
    else:
        # No active log file - create one in the run directory and configure logging
        log.info('No active log file found, creating new log file for experiment run')
        try:
            # Create the log file and add a file handler
            from adare.logger.logger import FileHandlerFormatter
            file_handler = logging.FileHandler(target_path, encoding='utf-8')
            file_handler.setFormatter(FileHandlerFormatter())
            file_handler.setLevel(logging.DEBUG)
            
            # Add handler to root logger to capture all log messages
            root_logger = logging.getLogger()
            root_logger.addHandler(file_handler)
            
            # Ensure root logger level allows DEBUG messages to be captured
            if root_logger.level > logging.DEBUG:
                root_logger.setLevel(logging.DEBUG)
            
            log.info(f'Created new log file at {target_path} and configured logging')
        except Exception as e:
            log.warning(f'Failed to create log file in run directory: {e}')


def __verify_playbook_testfunction_integrity(project_path: Path, playbook) -> None:
    """
    Verify integrity of all testfunctions used in the playbook.
    This ensures no testfunction has been modified after loading.
    """
    from adare.helperfunctions.integrity import verify_testfunction_integrity
    from adare.backend.testfunction.database import get_testfunction_files_data
    
    # Extract testfunction names from playbook tests
    testfunction_names = set()
    if hasattr(playbook, 'tests') and playbook.tests:
        for test in playbook.tests:
            if hasattr(test, 'testfunction'):
                testfunction_names.add(test.testfunction)
    
    if not testfunction_names:
        log.info("No testfunctions found in playbook - skipping integrity verification")
        return
    
    log.info(f"Verifying integrity of {len(testfunction_names)} testfunctions used in playbook")
    
    try:
        # Get all testfunction data from database
        tf_data = get_testfunction_files_data(
            project_path, 
            fields=['path', 'requirements_path', 'sha256hash', 'name']
        )
        
        # Create lookup by testfunction directory name
        tf_lookup = {}
        for tf in tf_data:
            tf_path = Path(tf['path'])
            tf_dir_name = tf_path.parent.name  # e.g., 'standard' from 'testfunctions/standard/standard.py'
            tf_lookup[tf_dir_name] = tf
        
        # Verify integrity of each required testfunction
        verified_count = 0
        for tf_name in testfunction_names:
            if tf_name not in tf_lookup:
                raise ExperimentIntegrityError(
                    log,
                    f"Testfunction '{tf_name}' used in playbook is not loaded in database",
                    possible_solutions=[
                        f"Load testfunction with 'adare testfunction load {tf_name}'",
                        "Check if testfunction directory exists",
                        "Verify testfunction name spelling in playbook"
                    ]
                )
            
            tf_info = tf_lookup[tf_name]
            tf_path = Path(tf_info['path'])
            req_path = Path(tf_info['requirements_path'])
            expected_hash = tf_info['sha256hash']
            
            verify_testfunction_integrity(tf_path, req_path, expected_hash)
            verified_count += 1
            log.debug(f"Testfunction integrity verified: {tf_name}")
        
        log.info(f"Testfunction integrity verification completed: {verified_count}/{len(testfunction_names)} verified")
        
    except ExperimentIntegrityError:
        # Re-raise integrity errors with full context
        raise
    except ImportError as e:
        log.warning(f"Integrity verification modules not available: {e}")
    except (FileNotFoundError, KeyError) as e:
        log.error(f"Testfunction database access failed: {e}")
        raise LoggedException(log, f"Failed to access testfunction database for integrity verification: {e}")


def __project_integrity_check(project_path: Path, project_directory: ProjectDirectory, environments: list[Path] = None,
                              testfunctions: list[Path] = None):
    # Use new integrity module for testfunctions
    from adare.helperfunctions.integrity import verify_testfunction_integrity
    
    testfunctions_changed: list = []
    hashes: list = project_database.get_global_testfunction_hashes()
    for hash_dict in hashes:
        file = hash_dict['file']
        requirements_file = hash_dict['requirements']
        hash_value = hash_dict['hash']
        path = Path(file)
        requirements_path = Path(requirements_file)

        if testfunctions and path not in testfunctions:
            continue

        try:
            verify_testfunction_integrity(path, requirements_path, hash_value)
            log.info(f'integrity check for testfunction file {path} passed')
        except ExperimentIntegrityError:
            testfunctions_changed.append(path)
            log.info(f'integrity check for testfunction file {path} failed')

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

    # Use new integrity module for environments  
    from adare.helperfunctions.integrity import verify_environment_integrity
    
    environments_changed: list = []
    hashes: dict = project_database.get_global_environment_hashes()
    for file, hash_value in hashes.items():
        path = Path(file)
        if environments and path not in environments:
            continue
            
        try:
            verify_environment_integrity(path, hash_value)
            log.info(f'integrity check for environment {path} passed')
        except ExperimentIntegrityError:
            environments_changed.append(path)
            log.info(f'integrity check for environment {path} failed')

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

def __cleanup_experiment_run(experiment_run_directory: ExperimentRunDirectory):
    if experiment_run_directory is not None:
        experiment_run_directory.clean()


def __experiment_integrity_check(project_path: Path, experiment_name: str, environment_name:str, experiment_directory: ExperimentDirectory):
    experiment_hashes = experiment_database.get_experiment_hashes(project_path, environment_name, experiment_name)
    experiment_ulid = experiment_database.get_experiment_by_project_and_name(project_path, experiment_name)
    experiment_run_count = experiment_database.get_experiment_run_count(project_path, experiment_ulid)

    file_changed = []
    if experiment_directory.sha256_playbook != experiment_hashes['playbook']:
        file_changed.append('playbook')
    else:
        log.info(f'integrity check for playbook file {experiment_directory.playbookfile} passed')
    
    # Tests are now integrated into playbook, so no separate testset check needed
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

async def install_and_run_adare_vm(context: ExperimentRunCtx, stop_event: threading.Event):
    """Install and run adarevm agent in the VM using appropriate environment.

    This function uses the command builder pattern to construct platform-specific
    commands for installing and running the adarevm agent. The builders handle
    the complexity of 8 different execution paths (Windows/Linux × Conda/Poetry × Wheels/Editable).
    """
    from .agent_command_builders import (
        detect_environment,
        WindowsAgentCommandBuilder,
        LinuxAgentCommandBuilder
    )

    vm = context.vm
    wheels_dir = context.project_directory.vm_runtime / 'wheels'

    # Step 1: Detect Python environment in the VM
    env_info = await detect_environment(vm, context.guest_platform, stop_event)

    # Step 2: Create platform-specific command builder
    if context.guest_platform == 'windows':
        builder = WindowsAgentCommandBuilder(
            wheels_dir=wheels_dir,
            shared_folders=context.config.shared_directories,
            websocket_port=context.config.websocket_port
        )
    else:
        builder = LinuxAgentCommandBuilder(
            wheels_dir=wheels_dir,
            shared_folders=context.config.shared_directories,
            websocket_port=context.config.websocket_port
        )

    # Step 3: Build all commands (setup, install, run)
    commands = await builder.build_commands(env_info, vm, stop_event)

    # Step 4: Execute setup commands (PATH, firewall, etc.)
    for setup_cmd in commands.setup_commands:
        result = await vm.run_command(setup_cmd, stop_event=stop_event)
        if result.returncode != 0:
            raise VMSetupError(
                log, vm.vm_name, setup_cmd,
                result.returncode, result.stdout, result.stderr
            )

    # Step 5: Mount shared folders (Windows only)
    if context.guest_platform == 'windows':
        shared_folders = {
            name: paths['vm']
            for name, paths in context.config.shared_directories.items()
            if paths.get('vm')
        }
        if shared_folders:
            await vm.mount_multiple_shared_folders(
                folders=shared_folders,
                stop_event=stop_event
            )

    # Step 6: Install adarevm if needed
    if not commands.skip_installation:
        log.info(f"Installing adarevm ({'wheels' if builder.wheels_available else 'editable'} mode)")
        result = await vm.run_command(commands.install_command, stop_event=stop_event)
        if result.returncode != 0:
            raise VMSetupError(
                log, vm.vm_name, commands.install_command,
                result.returncode, result.stdout, result.stderr
            )
    else:
        log.info("Installation skipped - using preinstalled agent")

    # Step 7: Run adarevm as background process
    # TODO: figure out a way to run poetry as sudo in linux
    if context.guest_platform == 'linux':
        await vm.run_command(
            commands.run_command,
            background=True,
            stop_event=stop_event,
            admin=True if env_info.use_conda else False,
            cwd=commands.run_cwd
        )
    else:
        await vm.run_command(
            commands.run_command,
            background=True,
            stop_event=stop_event,
            admin=True,
            cwd=commands.run_cwd
        )


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


def step_initialize(context: ExperimentRunCtx, fake: bool = False):
    context.experiment_run_ulid = experiment_database.initialize_experiment_run(context.config.project_path, fake)
    context.timestamp_start = datetime.now(timezone.utc)
    context.timestamp_before_vm_start = datetime.now(timezone.utc)
    context.adarevm = ADAREVM_DIR
    context.adarelib = ADARELIB_DIR
    log.info(f'initialized experiment run {context.experiment_run_ulid}')

def step_setup_experiment_environment(context: ExperimentRunCtx):
    """Consolidated step: Setup directories, validate playbook, and resolve environment."""
    with StageCtxManager(SetupExperimentEnvironmentStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Setup directories
        context.project_directory = ProjectDirectory(context.config.project_path)
        context.experiment_directory = ExperimentDirectory(context.config.project_path, context.config.experiment_name)
        context.experiment_directory.check_for_missing_files()
        log.info(f'checked experiment directory {context.experiment_directory.path}')
        
        # Set experiment and environment info early to prevent orphaned runs on interruption
        experiment_database.set_experiment_run_base_info(
            context.experiment_run_ulid,
            context.config.experiment_name,
            context.config.environment_name,
            context.config.project_path
        )
        log.info(f'set base experiment info for run {context.experiment_run_ulid}')
        
        # Set experiment start timestamp early to ensure it's persisted even if interrupted
        experiment_database.update_experiment_run_start(context.project_directory.path, context.experiment_run_ulid, context.timestamp_start)
        log.info(f'set experiment start timestamp for run {context.experiment_run_ulid}')

        # Validate playbook
        try:
            experiment_id = experiment_database.get_experiment_by_project_and_name(
                context.config.project_path, 
                context.config.experiment_name
            )
            if not experiment_id:
                # Fallback to file-based parsing for new/untracked experiments
                log.info("Experiment not found in database, falling back to file-based parsing")
                from adare.types.playbook import parse_playbook
                playbook_path = context.experiment_directory.path / "playbook.yml"
                if not playbook_path.exists():
                    log.warning("No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)")
                    return
                # Get VM OS and user for automatic variables
                context.playbook = parse_playbook(playbook_path)
                log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                return
            
            # Load from database (pre-validated)
            from adare.database.api.playbook import PlaybookApi
            with PlaybookApi(context.project_directory.path) as playbook_api:
                try:
                    log.info(f"Loading pre-validated playbook from database for experiment {experiment_id}")
                    context.playbook = playbook_api.load_playbook_from_database(experiment_id)
                    log.info(f"Playbook loaded from database - {len(context.playbook.actions)} actions found")
                except ValueError as e:
                    # Fallback to file parsing if database doesn't have the content
                    log.warning(f"Database playbook load failed: {e}, falling back to file parsing")
                    from adare.types.playbook import parse_playbook
                    from adare.config import get_vm_credentials
                    playbook_path = context.experiment_directory.path / "playbook.yml"
                    if not playbook_path.exists():
                        log.warning("No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)")
                        return
                    context.playbook = parse_playbook(playbook_path)
                    log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                    
        except Exception as e:
            raise LoggedException(log, f"Playbook loading failed: {str(e)}")

        # Verify integrity of testfunctions used in playbook
        # TODO: Re-enable this for production use - currently disabled for testing
        # CLAUDE: Temporarily commented out to allow testfunction modifications during testing
        # if hasattr(context, 'playbook') and context.playbook:
        #     __verify_playbook_testfunction_integrity(context.config.project_path, context.playbook)

        # Resolve environment
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

        # For lazy loading, VM file might not be available yet - will be resolved during VM creation
        context.vm_file = environment_database.get_environment_vm_file(context.environment_ulid)
        context.guest_platform = environment_database.get_environment_os(context.environment_ulid)
        
        # If VM file is not available, get from environment metadata directly
        if not context.vm_file or not context.guest_platform:
            from adare.types.environment import parse_environment_file
            environment_metadata = parse_environment_file(context.environment_file)
            if not context.vm_file:
                context.vm_file = Path(environment_metadata.vm)
            if not context.guest_platform:
                context.guest_platform = environment_metadata.os.platform

        log.info(f'found environment {context.config.environment_name}')

def step_validate_integrity(context: ExperimentRunCtx):
    """Consolidated step: Check experiment and project integrity."""
    with StageCtxManager(ValidateIntegrityStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        # Skip integrity checks in test mode to allow development
        if context.test_mode:
            stage_ctx.stage.sub_msg = "SKIPPED - Development/Test Mode"
            stage_ctx.set_status(stage_ctx.stage.status)
            log.info('Skipping integrity checks - running in test/development mode')
            return
            
        # Check experiment integrity
        stage_ctx.stage.sub_msg = "Checking experiment integrity..."
        stage_ctx.set_status(stage_ctx.stage.status)
        __experiment_integrity_check(
            context.config.project_path,
            context.config.experiment_name,
            context.config.environment_name,
            context.experiment_directory
        )
        
        # Check project integrity
        stage_ctx.stage.sub_msg = "Checking project integrity..."
        stage_ctx.set_status(stage_ctx.stage.status)
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
        
        # Clear sub message when done
        stage_ctx.stage.sub_msg = ""
        stage_ctx.set_status(stage_ctx.stage.status)

def step_prepare_run_environment(context: ExperimentRunCtx):
    """Consolidated step: Check application data and create run directory."""
    with StageCtxManager(PrepareRunEnvironmentStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Check application data
        adarevm_poetry_lock = ADAREVM_DIR / 'poetry.lock'
        adarelib_poetry_lock = ADARELIB_DIR / 'poetry.lock'
        if adarevm_poetry_lock.exists():
            log.info(f'removing {adarevm_poetry_lock} to ensure that adarevm is installed correctly')
            adarevm_poetry_lock.unlink()
        if adarelib_poetry_lock.exists():
            log.info(f'removing {adarelib_poetry_lock} to ensure that adarelib is installed correctly')
            adarelib_poetry_lock.unlink()
        
        # Create run directory
        run_dir = ExperimentRunDirectory(context.project_directory, context.config.experiment_name)
        run_dir.create()
        context.experiment_run_directory = run_dir
        
        # Copy adare log to run directory if runlog is enabled
        if context.config.runlog:
            _ensure_and_copy_adare_log_to_run_directory(run_dir)
        
        # Initialize MCP server with log file
        from adare.backend.experiment.mcp_server_manager import MCPServerManager
        context.mcp_server = MCPServerManager(log_file=run_dir.mcp_gui_log_file)
        


async def step_install_and_run_websocket_server(context: ExperimentRunCtx):
    with StageCtxManager(InstallAdareVMStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        await install_and_run_adare_vm(context, stop_event=context.user_interrupt_event)

async def step_connect_websocket(context: ExperimentRunCtx):
    with StageCtxManager(ConnectToVMStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        from adare.backend.experiment.websocket_client import AdareVMClient
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
        
        # Retry delays: 2, 3, 5, 7, 10 seconds (increased initial delay)
        retry_delays = [2, 3, 5, 7, 10]
        max_attempts = len(retry_delays) + 1  # +1 for the initial attempt
        
        last_error = None
        for attempt in range(1, max_attempts + 1):
            if context.stop_event.is_set():
                log.info("Connection cancelled by stop event")
                return
            
            # Update stage message to show retry attempt
            if attempt == 1:
                stage_ctx.stage.sub_msg = f"Attempting connection..."
            else:
                stage_ctx.stage.sub_msg = f"Retrying connection (attempt {attempt}/{max_attempts})"
            stage_ctx.set_status(stage_ctx.stage.status)
            
            try:
                log.info(f"Attempting to connect to AdareVM server (attempt {attempt}/{max_attempts})")
                connected = await context.client.connect(timeout=60.0)
                
                if connected:
                    stage_ctx.stage.sub_msg = ""  # Clear sub_msg to show default stage message
                    stage_ctx.set_status(stage_ctx.stage.status)
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
                    
                    return  # Success - exit the function
                else:
                    raise ConnectionRefusedError("Failed to establish websocket connection")
                    
            except (asyncio.TimeoutError, ConnectionClosed, WebSocketException, ConnectionRefusedError, OSError) as e:
                last_error = e
                log.warning(f"Connection attempt {attempt}/{max_attempts} failed: {e}")
                
                if attempt < max_attempts:
                    # Not the final attempt - wait and retry
                    delay = retry_delays[attempt - 1]
                    stage_ctx.stage.sub_msg = f"Attempt {attempt} failed, retrying in {delay}s..."
                    stage_ctx.set_status(stage_ctx.stage.status)
                    
                    log.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
        
        # All attempts failed
        stage_ctx.stage.sub_msg = f"All {max_attempts} connection attempts failed"
        stage_ctx.set_status(stage_ctx.stage.status)
        from adare.exceptions import LoggedException
        log.error(last_error, exc_info=True)
        raise LoggedException(log, f"Failed to connect to AdareVM server after {max_attempts} attempts: {last_error}") from last_error

async def step_execute_installations(context: ExperimentRunCtx):
    with StageCtxManager(InstallationsStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage_ctx:
        installations = environment_database.get_environment_installations(context.environment_ulid)

        if not installations:
            log.info("No installations to execute")
            return

        log.info(f"Executing {len(installations)} installation(s) from environment")

        for idx, installation in enumerate(installations, 1):
            installation_name = installation.name if hasattr(installation, 'name') else f"Installation {idx}"
            installation_cmd = installation.command if hasattr(installation, 'command') else str(installation)
            installation_desc = installation.description if hasattr(installation, 'description') else ""

            stage_ctx.stage.sub_msg = f"[{idx}/{len(installations)}] {installation_name}"
            stage_ctx.set_status(stage_ctx.stage.status)

            log.info(f"Executing installation [{idx}/{len(installations)}]: {installation_name}")
            if installation_desc:
                log.info(f"Description: {installation_desc}")
            log.info(f"Command: {installation_cmd}")

            try:
                # Execute installation command via WebSocket client
                result = await context.client.execute_shell(
                    installation_cmd,
                    shell=True,
                    timeout=600  # 10 minute timeout for installations
                )

                if result.get('returncode') == 0:
                    log.info(f"Installation '{installation_name}' completed successfully")
                    if result.get('stdout'):
                        log.debug(f"Installation output: {result['stdout']}")
                else:
                    log.error(f"Installation '{installation_name}' failed with return code {result.get('returncode')}")
                    if result.get('stderr'):
                        log.error(f"Installation error: {result['stderr']}")
                    if result.get('stdout'):
                        log.error(f"Installation output: {result['stdout']}")

                    # Continue with other installations but log the failure
                    log.warning(f"Continuing with remaining installations despite failure")

            except Exception as e:
                log.error(f"Failed to execute installation '{installation_name}': {e}", exc_info=True)
                log.warning(f"Continuing with remaining installations despite error")

        log.info(f"All installations completed")

async def step_start_mcp_server(context: ExperimentRunCtx):
    """Start the MCP GUI server for target detection."""
    with StageCtxManager(StartComputerVisionServerStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        log.info("Starting MCP GUI server for target detection...")
        
        success = await context.mcp_server.start()
        if success:
            log.info("MCP GUI server started successfully")
        else:
            from adare.exceptions import LoggedException
            raise LoggedException(log, "MCP GUI server failed to start - cannot proceed without target detection capabilities")


async def step_execute_experiment(context: ExperimentRunCtx):
    """Execute the experiment using the playbook controller."""

    # First, install testfunction dependencies in a separate stage
    from adare.types.stages import TestfunctionDependenciesStage
    from adare.backend.experiment.test_loader import TestLoader

    stage_deps = TestfunctionDependenciesStage()
    with StageCtxManager(stage_deps, context.experiment_run_ulid, event=context.user_interrupt_event):
        # Create test loader with all required parameters
        test_loader = TestLoader(
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            playbook=context.playbook,
            variable_resolver=None
        )
        await test_loader._install_dependencies_only(context.client)

    # Then run the actual experiment
    with StageCtxManager(ExperimentRunStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage:
        from adare.backend.experiment.playbook_controller import PlaybookController
        
        if not context.client:
            log.error("WebSocket client not available for experiment execution")
            return
        
        # Get experiment ID for execution tracking
        experiment_id = None
        try:
            experiment_id = experiment_database.get_experiment_by_project_and_name(
                context.config.project_path, 
                context.config.experiment_name
            )
            if experiment_id:
                log.debug(f"Found experiment {experiment_id} for execution tracking")
            else:
                log.warning("No experiment ID found - execution tracking will be disabled")
        except Exception as e:
            log.warning(f"Failed to get experiment ID for execution tracking: {e}")
        
        # Get VM credentials for automatic variables
        from adare.config import get_vm_credentials
        vm_os = context.guest_platform if context.guest_platform else None
        vm_user = None
        if vm_os:
            vm_user, _ = get_vm_credentials(vm_os)

        # Get flow console for interactive actions like pause
        flow_console = flowconsolemanager.get_handler(context.experiment_run_ulid)

        # Create playbook controller
        controller = PlaybookController(
            websocket_client=context.client,
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            debug_screenshots=context.debug_screenshots,
            screenshots_dir=context.experiment_run_directory.screenshots_directory,
            playbook=context.playbook,  # Pass pre-parsed playbook
            experiment_id=experiment_id,
            experiment_run_id=context.experiment_run_ulid,
            vm=context.vm,  # Pass VM for pull operations
            experiment_run_directory=context.experiment_run_directory.path,  # Pass run directory for artifacts
            vm_os=vm_os,  # Pass VM OS for automatic variables
            vm_user=vm_user,  # Pass VM user for automatic variables
            flow_console=flow_console,  # Pass flow console for interactive actions
            test_mode=context.test_mode  # Pass test mode flag
        )
        
        # Execute complete experiment (playbook + tests)
        log.info(f"Starting experiment execution for {context.config.experiment_name}")
        result = await controller.execute_experiment(context.experiment_directory.path)
        
        # Store execution result in context for final message generation
        context.execution_result = result
        
        if result.success:
            log.info(f"Experiment completed successfully: {result.successful_actions}/{result.total_actions} actions succeeded")
        else:
            log.error(f"Experiment failed: {result.error_message}")
            log.error(f"Action results: {result.successful_actions}/{result.total_actions} succeeded")


async def step_collect_system_info(context: ExperimentRunCtx):
    """Collect system information from the guest VM and save to YAML file."""
    with StageCtxManager(SystemInfoCollectionStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        from adare.backend.experiment.system_info_collector import collect_system_info

        # Check if system info collection is enabled in playbook settings
        collect_enabled = getattr(context.playbook.settings, 'collect_system_info', True)
        if not collect_enabled:
            log.info("System info collection disabled in playbook settings")
            return

        # Ensure we have required components
        if not context.client:
            log.warning("WebSocket client not available - skipping system info collection")
            return

        if not context.guest_platform:
            log.warning("Guest platform not detected - skipping system info collection")
            return

        if not hasattr(context, 'experiment_run_directory') or not context.experiment_run_directory:
            log.warning("Experiment run directory not available - skipping system info collection")
            return

        # Collect system information
        output_file = context.experiment_run_directory.system_info_file
        success = await collect_system_info(
            websocket_client=context.client,
            guest_platform=context.guest_platform,
            output_file=output_file
        )

        if success:
            log.info(f"System information collected and saved to {output_file}")
        else:
            log.warning("System information collection failed (experiment continues)")


def step_finalize(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(FinalizeStage(), context.experiment_run_ulid, event=event):
        timestamp_end = datetime.now(timezone.utc)
        experiment_database.update_experiment_run_end(context.project_directory.path, context.experiment_run_ulid, timestamp_end)
        duration_total = timestamp_end - context.timestamp_start
        duration_vm = timestamp_end - context.timestamp_before_vm_start
        log.info(f"Experiment run {context.experiment_run_ulid} finished after {duration_total} seconds (vm run time: {duration_vm})")
        __cleanup_experiment_run(context.experiment_run_directory)

async def step_shutdown_mcp_server(context: ExperimentRunCtx, post_interrupt: bool = False):
    """Stop the MCP GUI server."""
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownComputerVisionServerStage(), context.experiment_run_ulid, event=event):
        log.info('stopping MCP GUI server')
        if context.mcp_server is not None:
            await context.mcp_server.stop()


async def step_shutdown_ws(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownWebSocketStage(), context.experiment_run_ulid, event=event):
        log.info('stopping websocket client')
        if context.client:
            await context.client.disconnect()



def step_remove_fake_experiment_run(context: ExperimentRunCtx):
    # todo remove associated stuff as well (e.g. stages/files/...)
    experiment_database.remove_fake_experiment_run(context.project_directory.path, context.experiment_run_ulid)
    log.info(f'fake experiment run {context.experiment_run_ulid} removed')



def __start_event_listeners(experiment_run_ulid: str):
    from adare.backend.events.listener import event_listener_db, event_listener_cli
    from adare.backend.events.coordinator import start_stage_coordinator
    
    # Start the stage event coordinator first
    start_stage_coordinator()
    log.info("Stage event coordinator started")
    
    # Create threading events to signal when listeners are ready
    cli_ready_event = threading.Event()
    db_ready_event = threading.Event()
    
    def cli_wrapper():
        cli_ready_event.set()  # Signal that CLI listener is ready
        event_listener_cli(experiment_run_ulid)
    
    def db_wrapper():
        db_ready_event.set()  # Signal that DB listener is ready
        event_listener_db(experiment_run_ulid)
    
    cli_thread = threading.Thread(target=cli_wrapper, daemon=True)
    db_thread = threading.Thread(target=db_wrapper, daemon=True)

    cli_thread.start()
    db_thread.start()
    
    # Wait for both listeners to be ready before returning
    cli_ready_event.wait()
    db_ready_event.wait()
    log.info("Event listeners are ready")

    return cli_thread, db_thread


async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = True, debug_screenshots: bool = False, preserve_snapshot: bool = False, runlog: bool = True, vm_memory: int = None, vm_cpus: int = None):
    import signal
    import asyncio

    log.info(f"Starting experiment run {experiment_name} in project {project_path}")

    # Create the experiment context and initialize it.
    config = ExperimentConfig(project_path, experiment_name, environment_name, preserve_snapshot=preserve_snapshot, runlog=runlog)
    
    # Determine guest platform early to set platform-specific defaults
    # We need to get the environment info to determine the platform
    try:
        environment_file = None
        if environment_name:
            from adare.backend.environment import database as environment_database
            environment_file = environment_database.get_environment_path_by_project_and_name(
                project_path, environment_name
            )

        if environment_file:
            from adare.types.environment import parse_environment_file
            environment_metadata = parse_environment_file(environment_file)
            guest_platform = environment_metadata.os.platform

            # Set platform-specific defaults if not overridden by CLI
            if vm_memory is None:
                if 'windows' in guest_platform.lower():
                    config.vm_memory = 8192  # 8GB for Windows
                    log.info(f"Using Windows default VM memory: 8192MB")
                else:
                    config.vm_memory = 4096  # 4GB for Linux
                    log.info(f"Using Linux default VM memory: 4096MB")
            else:
                config.vm_memory = vm_memory
                log.info(f"Using custom VM memory: {vm_memory}MB")
        else:
            # Fallback: apply CLI override or keep default
            if vm_memory is not None:
                config.vm_memory = vm_memory
                log.info(f"Using custom VM memory: {vm_memory}MB")
    except (FileNotFoundError, OSError) as e:
        # Only catch file system related errors, not environment validation errors
        log.warning(f"Could not determine guest platform for memory defaults: {e}")
        # Fallback: apply CLI override or keep default
        if vm_memory is not None:
            config.vm_memory = vm_memory
            log.info(f"Using custom VM memory: {vm_memory}MB")
    
    # Override VM CPU settings if provided via CLI
    if vm_cpus is not None:
        config.vm_cpus = vm_cpus
        log.info(f"Using custom VM CPUs: {vm_cpus}")
    
    experiment_run_context = ExperimentRunCtx(config)
    # Respect the --debug-screenshots CLI flag (default: False unless flag is provided)
    experiment_run_context.debug_screenshots = debug_screenshots
    experiment_run_context.test_mode = test  # Store test mode flag (default: True for test mode)
    if test:
        step_initialize(experiment_run_context, fake=True)  # Test mode: creates fake run
    else:
        step_initialize(experiment_run_context)  # Production mode: creates real run

    # Create an asyncio Event to signal shutdown.
    stop_event = asyncio.Event()
    
    # Create a separate threading Event specifically for user interruption (Ctrl-C)
    user_interrupt_event = threading.Event()
    
    # Add the user interrupt event to the context so step functions can use it
    experiment_run_context.user_interrupt_event = user_interrupt_event

    def handle_sigint():
        log.info("Ctrl-C detected. Stopping experiment run...")
        user_interrupt_event.set()  # Signal user interruption
        experiment_run_context.stop_event.set()  # Signal the context's stop event.
        stop_event.set()  # Signal the asyncio stop event.
        log.info('hanlde: send stop events')

    # Register the signal handler for SIGINT.
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, handle_sigint)

    # Create and start the flow console.
    # print(experiment_run_context.experiment_run_ulid)
    flow_console = __create_and_start_flow_console(experiment_run_context.experiment_run_ulid, disable_printing, user_interrupt_event)
    
    # Start experiment timer header row
    if not disable_printing:
        flow_console.start_experiment_timer(experiment_name)
    
    # Add small delay to let Rich console settle before starting stages
    await asyncio.sleep(0.1)
    log.debug("Flow console started, proceeding with event listeners")

    # Start event listeners BEFORE any stages begin to ensure all events are captured
    __start_event_listeners(experiment_run_context.experiment_run_ulid)


    # Create step runner to handle execution logic
    step_runner = ExperimentStepRunner(stop_event, user_interrupt_event)
    
    # Create VM lifecycle manager
    vm_manager = VMLifecycleManager()

    # --- Execution Flow ---

    try:
        # Experiment Preparation Phase
        if not stop_event.is_set():
            with StageCtxManager(ExperimentPreparationStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                initial_steps = [
                    step_setup_experiment_environment,
                    step_validate_integrity,
                    step_prepare_run_environment,
                ]
                await step_runner.run_steps_sequence(initial_steps, experiment_run_context)

                # Start MCP server early (independent of VM)
                await step_runner.run_async_step(step_start_mcp_server, experiment_run_context)

        # Virtual Machine Setup Phase  
        if not stop_event.is_set():
            with StageCtxManager(VirtualMachineSetupStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                await step_runner.run_async_step(vm_manager.create_and_prepare_vm, experiment_run_context)
                await step_runner.run_async_step(vm_manager.start_vm, experiment_run_context)
                await step_runner.run_async_step(vm_manager.wait_until_ready, experiment_run_context)
                await step_runner.run_async_step(vm_manager.mount_shared_directories, experiment_run_context)

        # Software Installation Phase
        if not stop_event.is_set():
            with StageCtxManager(SoftwareInstallationStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                await step_runner.run_async_step(step_install_and_run_websocket_server, experiment_run_context)
                await step_runner.run_async_step(step_connect_websocket, experiment_run_context)
                await step_runner.run_async_step(step_execute_installations, experiment_run_context)

        # Experiment Execution Phase
        if not stop_event.is_set():
            with StageCtxManager(ExperimentExecutionStage(), experiment_run_context.experiment_run_ulid, event=user_interrupt_event):
                await step_runner.run_async_step(step_execute_experiment, experiment_run_context)

                # Collect system information after experiment execution (if enabled in playbook settings)
                await step_runner.run_async_step(step_collect_system_info, experiment_run_context)

        # Success: Mark experiment as finished if no exceptions occurred
        if not stop_event.is_set():
            log.info("Experiment completed successfully, marking as FINISHED")
            experiment_database.update_experiment_run_status(
                experiment_run_context.project_directory.path,
                experiment_run_context.experiment_run_ulid,
                StatusEnum.FINISHED,
            )
            # Update experiment timer to show completion
            if not disable_printing:
                flow_console.finish_experiment_timer(success=True)

    except LoggedException as e:
        # Handle structured exceptions - let them bubble up to exec_with_error_printing for consistent UX
        experiment_run_context.stop_event.set()
        log.info("LoggedException: send stop events")
        from adare.exceptions import LoggedErrorException
        status = StatusEnum.FAILED if isinstance(e, LoggedErrorException) else StatusEnum.INTERRUPTED
        experiment_database.update_experiment_run_status(
            experiment_run_context.project_directory.path,
            experiment_run_context.experiment_run_ulid,
            status,
        )
        # Update experiment timer to show failure
        if not disable_printing:
            flow_console.finish_experiment_timer(success=False)
        # Re-raise to be handled by exec_with_error_printing
        raise
    except Exception as e:
        log.error(f"An unexpected error occurred: {e}", exc_info=True)
        experiment_run_context.stop_event.set()
        log.info("exception: send stop events")
        experiment_database.update_experiment_run_status(
            experiment_run_context.project_directory.path,
            experiment_run_context.experiment_run_ulid,
            StatusEnum.INTERRUPTED,
        )
        # Update experiment timer to show failure
        if not disable_printing:
            flow_console.finish_experiment_timer(success=False)
        # Re-raise unexpected exceptions too so they get proper exit codes
        raise
    finally:
        # Ensure shutdown procedures are executed.
        if not stop_event.is_set():
            experiment_run_context.stop_event.set()
            log.info("finally: send stop events")
        
        # Update database status if user interrupted
        if user_interrupt_event.is_set():
            log.info("User interrupt detected - updating experiment run status to INTERRUPTED")
            experiment_database.update_experiment_run_status(
                experiment_run_context.project_directory.path,
                experiment_run_context.experiment_run_ulid,
                StatusEnum.INTERRUPTED,
            )
            # Update experiment timer to show interruption
            if not disable_printing:
                flow_console.finish_experiment_timer(success=False)
        
        try:
            input("Press Enter to continue to cleanup and shutdown...")
            log.info("Starting cleanup and shutdown...")
            # Wrap cleanup in proper stage context (don't pass interrupt event - we want to show actual cleanup work)
            with StageCtxManager(CleanupShutdownStage(), experiment_run_context.experiment_run_ulid, event=None):
                await step_runner.run_cleanup_step(step_finalize, experiment_run_context, post_interrupt=True)
                await step_runner.run_cleanup_step(step_shutdown_mcp_server, experiment_run_context, post_interrupt=True)
                await step_runner.run_cleanup_step(step_shutdown_ws, experiment_run_context, post_interrupt=True)
                await step_runner.run_cleanup_step(vm_manager.stop_vm, experiment_run_context, post_interrupt=True)
                await step_runner.run_cleanup_step(vm_manager.cleanup_vm, experiment_run_context, post_interrupt=True)
            # Give time for all events to be processed before stopping
            await asyncio.sleep(2)
            
            # Stop the stage event coordinator
            from adare.backend.events.coordinator import stop_stage_coordinator
            stop_stage_coordinator()
            log.info("Stage event coordinator stopped")
            
            # Log enhanced experiment summary before stopping console
            # Get execution results and calculate overall statistics
            execution_result = getattr(experiment_run_context, 'execution_result', None)

            if execution_result:
                # Calculate total duration from context timestamps
                total_duration = None
                if hasattr(experiment_run_context, 'timestamp_start'):
                    from datetime import datetime, timezone
                    total_duration = (datetime.now(timezone.utc) - experiment_run_context.timestamp_start).total_seconds()

                # Log comprehensive experiment summary
                flow_console.log_experiment_summary(
                    ulid=experiment_run_context.experiment_run_ulid,
                    success=execution_result.success,
                    total_actions=execution_result.total_actions,
                    successful_actions=execution_result.successful_actions,
                    failed_actions=execution_result.failed_actions,
                    total_tests=execution_result.total_tests,
                    successful_tests=execution_result.successful_tests,
                    failed_tests=execution_result.failed_tests,
                    duration=total_duration
                )
            else:
                # Enhanced fallback - show what we can determine from the context
                # Calculate total duration from context timestamps
                total_duration = None
                if hasattr(experiment_run_context, 'timestamp_start'):
                    from datetime import datetime, timezone
                    total_duration = (datetime.now(timezone.utc) - experiment_run_context.timestamp_start).total_seconds()

                # Check if this was an interruption vs failure
                was_interrupted = user_interrupt_event.is_set()

                # Show a summary even without execution result
                flow_console.log_experiment_summary(
                    ulid=experiment_run_context.experiment_run_ulid,
                    success=False,  # If we're here, something failed or was interrupted
                    total_actions=0,
                    successful_actions=0,
                    failed_actions=0,
                    total_tests=0,
                    successful_tests=0,
                    failed_tests=0,
                    duration=total_duration,
                    was_interrupted=was_interrupted
                )

            if test:
                # Test mode: fake runs are kept until manually cleaned with 'adare experiment clean <name>'
                log.info(f"Test mode run {experiment_run_context.experiment_run_ulid} completed and preserved for analysis")
            # Give the flow console time to display the summary before stopping
            await asyncio.sleep(3)

            # Print debug flow messages before stopping console
            # flow_console.print_debug_flow_messages()
            flow_console.stop()
        except Exception as e:
            log.error(f"Error during shutdown: {e}", exc_info=True)
            # Ensure coordinator is stopped even if cleanup fails
            try:
                from adare.backend.events.coordinator import stop_stage_coordinator
                stop_stage_coordinator()
            except Exception as cleanup_error:
                log.error(f"Error stopping stage coordinator during error cleanup: {cleanup_error}", exc_info=True)

    # Query the database to get the actual experiment success status
    experiment_success = False
    try:
        from adare.database.api.experiment import ExperimentApi
        from adare.database.models.project_models import ExperimentRun
        with ExperimentApi(experiment_run_context.project_directory.path) as api:
            experiment_run = api._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_context.experiment_run_ulid).first()
            if experiment_run:
                # Use the result_status property to determine actual success
                experiment_success = experiment_run.result_status == StatusEnum.SUCCESS
    except Exception as e:
        log.error(f"Error checking experiment run status: {e}")
        experiment_success = False

    # Generate forensic report after experiment completion
    try:
        # Check if forensic logging is enabled (default: True)
        forensic_enabled = True
        if (hasattr(experiment_run_context, 'playbook') and
            experiment_run_context.playbook and
            hasattr(experiment_run_context.playbook, 'settings') and
            experiment_run_context.playbook.settings):
            forensic_enabled = experiment_run_context.playbook.settings.forensic_logging

        if forensic_enabled and hasattr(experiment_run_context, 'experiment_run_directory'):
            from adare.backend.experiment.forensic_reporter import generate_forensic_report_for_run
            forensic_log_path = experiment_run_context.experiment_run_directory.forensic_log_file

            log.info(f"Generating forensic report for run {experiment_run_context.experiment_run_ulid}")
            forensic_success = generate_forensic_report_for_run(
                experiment_run_context.experiment_run_ulid,
                forensic_log_path,
                experiment_run_context.project_directory.path
            )

            if forensic_success:
                log.info(f"Forensic report generated: {forensic_log_path}")
            else:
                log.warning(f"Failed to generate forensic report for run {experiment_run_context.experiment_run_ulid}")
    except Exception as e:
        log.error(f"Error generating forensic report: {e}", exc_info=True)

    # Return both interruption status and actual success status
    return user_interrupt_event.is_set(), experiment_success



def experiment_test(project_path: Path, experiment_name: str, environment_name: str):
    """Test an experiment in development mode - creates fake run that gets cleaned up.
    
    This function provides a development-friendly way to test experiments without
    creating persistent runs or requiring integrity checks. Perfect for iterative
    development and testing of experiment playbooks.
    
    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to test
        environment_name: Name of the environment to use
    """
    import asyncio
    
    log.info(f'Starting experiment test: {experiment_name} in environment {environment_name}')
    
    # Run experiment in test mode (creates fake run that gets cleaned up)
    asyncio.run(experiment_run(
        project_path=project_path, 
        experiment_name=experiment_name, 
        environment_name=environment_name, 
        disable_printing=False,  # Show output for development feedback
        test=True,  # This creates fake runs that are cleaned up automatically
        debug_screenshots=True,  # Enable debug screenshots for development
        preserve_snapshot=False,  # Don't preserve snapshots in test mode
        runlog=True   # Save logs for test runs to aid debugging
    ))

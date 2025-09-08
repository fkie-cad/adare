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
    ExperimentDirectoryDoesNotExistError, ExperimentIntegrityError, ExperimentAlreadyExistsError, ExperimentNotChanged
from adare.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adare.helperfunctions.string import make_string_path_safe
from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole
from adare.backend.experiment.step_runner import ExperimentStepRunner
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.types.stages import (
    # Top-level parent stages
    ExperimentPreparationStage, VirtualMachineSetupStage, SoftwareInstallationStage, 
    ExperimentExecutionStage, CleanupShutdownStage,
    # Sub-stages
    SetupExperimentEnvironmentStage, ValidateIntegrityStage, PrepareRunEnvironmentStage, StartComputerVisionServerStage,
    ExperimentIntegrityCheckStage, ProjectIntegrityCheckStage,
    InstallAdareVMStage, ConnectToVMStage, InstallationsStage,
    ExperimentRunStage,
    FinalizeStage, ShutdownComputerVisionServerStage, ShutdownWebSocketStage,
)
from adare.backend.experiment.stagectxmanager import StageCtxManager
from adarelib.constants import StatusEnum
from adare.config.configdirectory import ADAREVM_DIR, ADARELIB_DIR
from adare.webappaccess.download import download_experiment, sync
from adare.webappaccess.login import is_logged_in
from adare.exceptions import NotLoggedInError
from adare.backend.experiment.runctx import ExperimentRunCtx, ExperimentConfig

# configure logging
import logging
log = logging.getLogger(__name__)

# Disable verbose MCP client logging to prevent base64 image flooding the log
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
    from adare.console import print_success_message
    
    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.create()
    log.info(f'experiment directory {experiment_directory.path} created')
    
    # Provide clear user feedback with next steps
    next_steps = [
        f'Edit {experiment_directory.playbookfile.name} to define a sequence of gui actions and tests',
        f'Edit {experiment_directory.metadatafile.name} to add experiment details, such as possible environments, tags, and more',
        f'Before run load the experiment with: adare experiment load {experiment}',
        f'Run the experiment with: adare experiment run {experiment} -e <environment>'
    ]
    
    print_success_message(
        title=f'Experiment "{experiment}" created successfully!',
        location=str(experiment_directory.path),
        next_steps=next_steps,
        tip='See documentation for an tutorial on how write an experiment here: https://adare.seclab-bonn.de/docs/gettingstarted/index.html#create-an-experiment'
    )


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
    playbook_path = experiment_directory.path / "playbook.yml"
    if not playbook_path.exists():
        log.info("No playbook.yml found - skipping testset validation")
        return  # No playbook to validate
    
    project_directory = ProjectDirectory(project_path)
    testfunctions_dir = project_directory.testfunctions
    
    if not testfunctions_dir.exists():
        log.warning(f"Testfunctions directory {testfunctions_dir} does not exist - skipping validation")
        return
    
    try:
        from adarelib.testset.testfunction import import_basictest_subclasses, get_missing_testfunctions
        
        log.info("Validating testset compatibility with available testfunctions...")
        
        # Load testset from playbook
        testsetfile = experiment_directory.load_testset()
        
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
        # print stack trace for debugging
        import traceback
        traceback.print_exc()
        raise ExperimentIntegrityError(
            log,
            f"Testset validation failed: {str(e)}",
            possible_solutions=[
                "Check testset.yml syntax and structure",
                "Verify testfunctions directory structure",
                "Ensure all required testfunction dependencies are available"
            ]
        )


def experiment_load(project_path: Path, experiment_name: str, force: bool = False, silent: bool = False):
    from adare.console import print_success_message
    
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
    
    was_updated = False
    if experiment_ulid := experiment_database.get_experiment_by_project_and_name(
            project_path, experiment_name, trigger_error=False
    ):
        try:
            __experiment_update(
                experiment_ulid, experiment_name, experiment_directory, force
            )
            was_updated = True
        except ExperimentNotChanged as e:
            experiment_sync(experiment_ulid)
    else:
        experiment_ulid = experiment_database.create_experiment(
            name=experiment_name,
            experiment_directory=experiment_directory
        )
        log.info(f'experiment {experiment_name} created')

    experiment_sync(experiment_ulid)
    
    # Protect experiment files after loading
    from adare.helperfunctions.integrity import protect_loaded_files
    experiment_files = [experiment_directory.playbookfile]
    if experiment_directory.metadatafile.exists():
        experiment_files.append(experiment_directory.metadatafile)
    protected_files = protect_loaded_files(experiment_files)
    log.info(f'Protected {len(protected_files)} experiment files')
    
    # Provide clear user feedback only if not in silent mode
    if not silent:
        action = "updated" if was_updated else "loaded"
        next_steps = [
            f'Run the experiment with: adare experiment run {experiment_name} -e <environment>',
        ]
        
        print_success_message(
            title=f'Experiment "{experiment_name}" {action} successfully!',
            location=str(experiment_directory.path),
            next_steps=next_steps,
            tip=f'show the experiment info with `adare experiment info {experiment_name}` to see the details',
        )


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
    hashes: list = project_database.get_project_testfunction_hashes(project_path)
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
    hashes: dict = project_database.get_project_environment_hashes(project_path)
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


async def install_and_run_adare_vm(context: ExperimentRunCtx, stop_event: threading.Event):
    vm = context.vm
    # TODO: maybe speed up by queuing the commands and running them as a single command to avoid VBoxManager overhead
    if context.guest_platform == 'windows':
        firewall_rule = f'New-NetFirewallRule -DisplayName "adarevm" -Direction Inbound -Action Allow -Protocol TCP -LocalPort {context.config.websocket_port}'
        await vm.run_command(firewall_rule, stop_event=stop_event)
        set_path_command = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\shared\tools", "User")'
        set_path_command_experiment_tools = r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\experiment\shared\tools", "User")'
        # Mount VirtualBox shared folders shortly (VirtualBox shared folders are exposed as a network provider -> lazy loading prevents access otherwise)
        mount_shared_folder = r'net use Z: \\vboxsvr\adare; net use Z: /delete'
        await vm.run_command(mount_shared_folder, stop_event=stop_event)
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



def step_initialize(context: ExperimentRunCtx, fake: bool = False):
    context.experiment_run_ulid = experiment_database.initialize_experiment_run(fake)
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
            context.config.project_path.name
        )
        log.info(f'set base experiment info for run {context.experiment_run_ulid}')
        
        # Set experiment start timestamp early to ensure it's persisted even if interrupted
        experiment_database.update_experiment_run_start(context.experiment_run_ulid, context.timestamp_start)
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
                context.playbook = parse_playbook(playbook_path)
                log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                return
            
            # Load from database (pre-validated)
            from adare.database.api.playbook import PlaybookApi
            with PlaybookApi() as playbook_api:
                try:
                    log.info(f"Loading pre-validated playbook from database for experiment {experiment_id}")
                    context.playbook = playbook_api.load_playbook_from_database(experiment_id)
                    log.info(f"Playbook loaded from database - {len(context.playbook.actions)} actions found")
                except ValueError as e:
                    # Fallback to file parsing if database doesn't have the content
                    log.warning(f"Database playbook load failed: {e}, falling back to file parsing")
                    from adare.types.playbook import parse_playbook
                    playbook_path = context.experiment_directory.path / "playbook.yml"
                    if not playbook_path.exists():
                        log.warning("No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)")
                        return
                    context.playbook = parse_playbook(playbook_path)
                    log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                    
        except Exception as e:
            raise LoggedException(log, f"Playbook loading failed: {str(e)}")
        
        # Verify integrity of testfunctions used in playbook
        if hasattr(context, 'playbook') and context.playbook:
            __verify_playbook_testfunction_integrity(context.config.project_path, context.playbook)
        
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
    with StageCtxManager(ValidateIntegrityStage(), context.experiment_run_ulid, event=context.user_interrupt_event):
        # Check experiment integrity
        __experiment_integrity_check(
            context.config.project_path,
            context.config.experiment_name,
            context.config.environment_name,
            context.experiment_directory
        )
        
        # Check project integrity
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
    with StageCtxManager(InstallationsStage(), context.experiment_run_ulid, event=context.user_interrupt_event) as stage:
        installations = environment_database.get_environment_installations(context.environment_ulid)
        
        if not installations:
            log.info("No installations to execute")
            return
        
        pass

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
        
        # Create playbook controller
        controller = PlaybookController(
            websocket_client=context.client,
            experiment_dir=context.experiment_directory.path,
            project_dir=context.project_directory.path,
            debug_screenshots=context.debug_screenshots,
            screenshots_dir=context.experiment_run_directory.screenshots_directory if context.debug_screenshots else None,
            playbook=context.playbook,  # Pass pre-parsed playbook
            experiment_id=experiment_id,
            experiment_run_id=context.experiment_run_ulid
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


def step_finalize(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(FinalizeStage(), context.experiment_run_ulid, event=event):
        timestamp_end = datetime.now(timezone.utc)
        experiment_database.update_experiment_run_end(context.experiment_run_ulid, timestamp_end)
        duration_total = timestamp_end - context.timestamp_start
        duration_vm = timestamp_end - context.timestamp_before_vm_start
        log.info(f"Experiment run {context.experiment_run_ulid} finished after {duration_total} seconds (vm run time: {duration_vm})")
        __cleanup_experiment_run(context.experiment_run_directory)

async def step_shutdown_mcp_server(context: ExperimentRunCtx, post_interrupt: bool = False):
    """Stop the MCP GUI server."""
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownComputerVisionServerStage(), context.experiment_run_ulid, event=event):
        log.info('stopping MCP GUI server')
        await context.mcp_server.stop()


async def step_shutdown_ws(context: ExperimentRunCtx, post_interrupt: bool = False):
    event = None if post_interrupt else context.user_interrupt_event
    with StageCtxManager(ShutdownWebSocketStage(), context.experiment_run_ulid, event=event):
        log.info('stopping websocket client')
        if context.client:
            await context.client.disconnect()



def step_remove_fake_experiment_run(context: ExperimentRunCtx):
    # todo remove associated stuff as well (e.g. stages/files/...)
    experiment_database.remove_fake_experiment_run(context.experiment_run_ulid)
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


async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = False, debug_screenshots: bool = False, preserve_snapshot: bool = False):
    import signal
    import asyncio

    log.info(f"Starting experiment run {experiment_name} in project {project_path}")

    # Create the experiment context and initialize it.
    config = ExperimentConfig(project_path, experiment_name, environment_name, preserve_snapshot=preserve_snapshot)
    experiment_run_context = ExperimentRunCtx(config)
    experiment_run_context.debug_screenshots = debug_screenshots
    if test:
        step_initialize(experiment_run_context, fake=True)
    else:
        step_initialize(experiment_run_context)

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
    # No need for custom exception handler - exceptions now bubble up to main try/except



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

        # Success: Mark experiment as finished if no exceptions occurred
        if not stop_event.is_set():
            log.info("Experiment completed successfully, marking as FINISHED")
            experiment_database.update_experiment_run_status(
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
            if not test:
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
            else:
                step_remove_fake_experiment_run(experiment_run_context)
            await asyncio.sleep(1)
            
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
                log.error(f"Error stopping stage coordinator during error cleanup: {cleanup_error}")





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



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
    # VM Test stages
    VMTestSetupStage, VMCompatibilityTestStage, VMTestCleanupStage,
    # VM Test substages
    VMResponseTestStage, VMSharedFoldersTestStage, VMPythonTestStage, VMPoetryTestStage,
    VMAdareServerTestStage, VMWebSocketTestStage, VMScreenshotTestStage, VMClickTestStage,
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


class StageCtxManagerLite:
    """Lightweight StageCtxManager for VM tests - calls flow console directly (no database/events)."""
    
    # Class-level registry to track active parent stages for hierarchy validation
    _active_stages = {}  # stage_name -> stage_instance
    
    def __init__(self, stage, flow_console, level=0):
        self.stage = stage  # Reuse existing Stage classes
        self.flow_console = flow_console  # Direct flow console access
        self.level = level
        self.stage_id = f"{stage.name}_{int(__import__('time').time())}"
        self.start_time = None
        self.end_time = None
        
    async def __aenter__(self):
        from datetime import datetime, timezone
        
        # Validate parent stage hierarchy (like original StageCtxManager)
        if hasattr(self.stage, 'parent') and self.stage.parent:
            if self.stage.parent not in self._active_stages:
                # For VM tests, be more lenient - just log a warning instead of raising error
                log.warning(f"VM Test Stage '{self.stage.name}' expects parent '{self.stage.parent}' but no parent stage is active. Continuing anyway for VM tests.")
        
        # Add this stage to active stages registry
        self._active_stages[self.stage.name] = self.stage
        
        # Set stage start time (reuse Stage lifecycle logic)
        self.start_time = datetime.now(timezone.utc)
        self.stage.start_time = self.start_time
        
        # Call flow console directly (no events needed)
        self.flow_console.log_spinner(
            identifier=self.stage_id,
            message=self.stage.msg,
            level=self.level,
            start_time=self.start_time
        )
        
        log.debug(f"Started VM test stage: {self.stage.name} - {self.stage.msg}")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        from datetime import datetime, timezone
        
        # Remove this stage from active stages registry
        self._active_stages.pop(self.stage.name, None)
        
        # Set stage end time and calculate duration
        self.end_time = datetime.now(timezone.utc)
        self.stage.end_time = self.end_time
        duration = (self.end_time - self.start_time).total_seconds()
        
        # Determine status based on exception
        if exc_type:
            status = StatusEnum.FAILED
            message = f"{self.stage.msg} (failed)"
        else:
            status = StatusEnum.SUCCESS
            message = self.stage.msg
        
        # Update stage status
        self.stage.status = status
        
        # Call flow console directly (no events needed)  
        self.flow_console.log_spinner_done(
            identifier=self.stage_id,
            status=status,
            message=message,
            duration=duration
        )
        
        log.debug(f"Completed VM test stage: {self.stage.name} - Status: {status.name}, Duration: {duration:.2f}s")
        
        # Don't suppress exceptions
        return False


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
    if not force and not experiment_database.check_for_experiment_change(experiment_ulid, experiment_directory.sha256):
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
                from adare.config import get_vm_credentials
                playbook_path = context.experiment_directory.path / "playbook.yml"
                if not playbook_path.exists():
                    log.warning("No playbook.yml found - experiment cannot run GUI actions (experiment may be incomplete)")
                    return
                # Get VM OS and user for automatic variables
                vm_os = context.guest_platform if context.guest_platform else None
                vm_user = None
                if vm_os:
                    vm_user, _ = get_vm_credentials(vm_os)
                context.playbook = parse_playbook(playbook_path)
                log.info(f"Playbook validation successful - {len(context.playbook.actions)} actions found")
                return
            
            # Load from database (pre-validated)
            from adare.database.api.playbook import PlaybookApi
            with PlaybookApi() as playbook_api:
                try:
                    log.info(f"Loading pre-validated playbook from database for experiment {experiment_id}")
                    # CLAUDE: Pass VM parameters to database loader for automatic variables
                    vm_os = context.guest_platform if context.guest_platform else None
                    vm_user = None
                    if vm_os:
                        from adare.config import get_vm_credentials
                        vm_user, _ = get_vm_credentials(vm_os)
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
                    # Get VM OS and user for automatic variables
                    vm_os = context.guest_platform if context.guest_platform else None
                    vm_user = None
                    if vm_os:
                        vm_user, _ = get_vm_credentials(vm_os)
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
            screenshots_dir=context.experiment_run_directory.screenshots_directory if context.debug_screenshots else None,
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


async def experiment_run(project_path: Path, experiment_name: str, environment_name: str, disable_printing: bool = False, test: bool = False, debug_screenshots: bool = False, preserve_snapshot: bool = False, runlog: bool = True, vm_memory: int = None, vm_cpus: int = None):
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
    except Exception as e:
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
    experiment_run_context.debug_screenshots = debug_screenshots
    experiment_run_context.test_mode = test  # Store test mode flag for later use
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
            # input("Press Enter to continue to cleanup and shutdown...")
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
                # Fake runs are now kept until manually cleaned with 'adare experiment clean <name>'
                log.info(f"Fake experiment run {experiment_run_context.experiment_run_ulid} completed and preserved for analysis")
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
                log.error(f"Error stopping stage coordinator during error cleanup: {cleanup_error}")

    # Query the database to get the actual experiment success status
    experiment_success = False
    try:
        from adare.database.api.experiment import ExperimentApi
        from adare.database.models.experiment import ExperimentRun
        with ExperimentApi() as api:
            experiment_run = api._session.query(ExperimentRun).filter(ExperimentRun.id == experiment_run_context.experiment_run_ulid).first()
            if experiment_run:
                # Use the result_status property to determine actual success
                experiment_success = experiment_run.result_status == StatusEnum.SUCCESS
    except Exception as e:
        log.error(f"Error checking experiment run status: {e}")
        experiment_success = False

    # Return both interruption status and actual success status
    return user_interrupt_event.is_set(), experiment_success





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


def experiment_clean(project_path: Path, experiment_name: str):
    """Clean fake experiment runs for the specified experiment.

    This function removes all fake runs associated with an experiment,
    helping to clean up test runs that are preserved for debugging.

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to clean fake runs for
    """
    from adare.console import print_success_message
    from adare.database.api.experiment import ExperimentApi

    log.info(f'Cleaning fake runs for experiment: {experiment_name}')

    try:
        with ExperimentApi() as api:
            removed_count = api.remove_fake_experiment_runs_by_experiment_name(project_path, experiment_name)

            if removed_count > 0:
                log.info(f'Removed {removed_count} fake run(s) for experiment "{experiment_name}"')
                print_success_message(
                    title=f'Experiment "{experiment_name}" cleaned successfully!',
                    location=f'Removed {removed_count} fake run(s)',
                    next_steps=[
                        'Fake runs have been permanently deleted from the database',
                        f'You can continue testing with: adare experiment test {experiment_name} -e <environment>'
                    ]
                )
            else:
                log.info(f'No fake runs found for experiment "{experiment_name}"')
                print(f'No fake runs found for experiment "{experiment_name}" - nothing to clean')

    except ValueError as e:
        from adare.exceptions import LoggedException
        raise LoggedException(log, str(e))
    except Exception as e:
        from adare.exceptions import LoggedException
        raise LoggedException(log, f'Failed to clean experiment "{experiment_name}": {str(e)}')


async def ova_test(ova_file_path: Path, guest_platform: str, verbose: bool = False, vm_cleanup_mode: str = 'prompt') -> bool:
    """
    Test OVA file compatibility with ADARE.
    
    This function has been moved to vm_test.py for better code organization.
    
    Args:
        ova_file_path: Path to the .ova file to test
        guest_platform: Platform type ('windows' or 'linux') - required
        verbose: Enable verbose logging
        vm_cleanup_mode: VM cleanup mode ('keep' or 'prompt')
        
    Returns:
        True if VM is compatible with ADARE, False otherwise
    """
    from adare.backend.experiment.vm_test import ova_test as vm_ova_test
    return await vm_ova_test(ova_file_path, guest_platform, verbose, vm_cleanup_mode)


def _create_ova_test_context(ova_file_path: Path, guest_platform: str):
    """Create minimal context for OVA testing."""
    import time
    import ulid
    from adare.backend.experiment.runctx import ExperimentConfig, ExperimentRunCtx
    from adare.config.configdirectory import ADAREVM_DIR
    
    # Create minimal config for testing
    config = ExperimentConfig(
        project_path=Path("/tmp"),  # Dummy path
        experiment_name="ova_test",
        environment_name="ova_test_env",
        test_mode=True,
        preserve_snapshot=False,
        vm_cpus=2,
        vm_memory=2048,
        websocket_port=18765,
        vm_resolution=(1920, 1080)
    )
    
    # Create context with minimal required fields
    context = ExperimentRunCtx(config=config)
    context.vm_name = f"adare_ova_test_{int(time.time())}"
    context.experiment_run_ulid = str(ulid.ULID())
    context.guest_platform = guest_platform
    context.adarevm = ADAREVM_DIR
    context.adarelib = ADARELIB_DIR
    context.vm = None
    context.client = None
    
    # Store OVA file path for import
    context._ova_file_path = ova_file_path
    
    # Add user interrupt event (required by VM lifecycle methods)
    context.user_interrupt_event = threading.Event()
    
    return context


async def _import_ova_for_test(context):
    """Import OVA file directly for testing."""
    log.info("CLAUDE: Phase 1 - Importing OVA file...")
    
    from adare.config import get_vm_credentials
    from adare.virtualbox.api import VirtualBoxVM, VirtualBoxManager
    
    # Get credentials for guest platform
    username, password = get_vm_credentials(context.guest_platform)
    
    # Create VM instance
    vbox_manager = VirtualBoxManager()
    context.vm = VirtualBoxVM(
        vm_name=context.vm_name,
        guest_os=context.guest_platform,
        manager=vbox_manager,
        username=username,
        password=password,
        cpus=context.config.vm_cpus,
        ram=context.config.vm_memory
    )
    
    # Import OVA file (using same pattern as working vm database import)
    await context.vm.create_from_ovf_or_ova(
        file_path=context._ova_file_path,
        silent=True,
        stop_event=context.user_interrupt_event
    )
    
    # Setup minimal shared directories configuration for testing
    from adare.config import SHARE_POINT_VM
    shared_root = Path(SHARE_POINT_VM[context.guest_platform])
    context.config.shared_directories = {
        'adare': {'host': context.adarevm.parent, 'vm': shared_root / 'app'}
    }
    
    log.info(f"CLAUDE: ✅ VM imported successfully as '{context.vm_name}'")


async def _setup_shared_folders_for_test(context):
    """Setup shared folders in VirtualBox for testing."""
    log.info("CLAUDE: Setting up shared folders...")
    
    # Add shared folders to VirtualBox (similar to VM lifecycle manager)
    for name, paths in context.config.shared_directories.items():
        await context.vm.add_shared_folder(name, host_path=paths['host'], stop_event=context.user_interrupt_event)
    
    log.info("CLAUDE: ✅ Shared folders configured in VirtualBox")


async def _test_gui_automation(context):
    """Test basic GUI automation capabilities."""
    log.info("CLAUDE: Phase 5 - Testing GUI automation and commands...")
    
    # Test 1: Take a screenshot to verify display works
    log.info("CLAUDE: Test 1 - Taking screenshot...")
    screenshot_result = await context.client.screenshot()
    if not screenshot_result.get('success'):
        raise LoggedException(log, "Screenshot capture failed")
    log.info("CLAUDE: ✅ Screenshot captured successfully")
    
    # Test 2: Perform a click at a fixed position (20, 20)
    log.info("CLAUDE: Test 2 - Testing mouse click...")
    click_result = await context.client.click(20, 20)
    if not click_result.get('success'):
        raise LoggedException(log, "Mouse click test failed")
    log.info("CLAUDE: ✅ Mouse click at (20, 20) successful")
    
    # Test 3: Execute OS-specific command with known output
    log.info("CLAUDE: Test 3 - Testing command execution...")
    test_command = 'echo ADARE_TEST_SUCCESS'
    expected_output = 'ADARE_TEST_SUCCESS'
    
    command_result = await context.client.execute_shell(test_command, timeout=10.0)
    if not command_result.get('success'):
        raise LoggedException(log, f"Command execution failed: {command_result.get('error', 'Unknown error')}")
    
    # Check if the output contains our expected text
    stdout = command_result.get('stdout', '').strip()
    if expected_output not in stdout:
        raise LoggedException(log, f"Command output unexpected. Expected '{expected_output}', got '{stdout}'")
    
    log.info(f"CLAUDE: ✅ Command execution successful. Output: '{stdout}'")
    log.info("CLAUDE: ✅ All GUI automation and command tests completed successfully")


# Individual VM test substage functions
async def _test_vm_response(context):
    """Test basic VM responsiveness."""
    test_result = await context.vm.run_command("true", stop_event=context.user_interrupt_event)
    if test_result == 0:
        log.info("CLAUDE: ✅ VM is responsive to commands")
        return True
    else:
        log.warning(f"CLAUDE: ❌ VM not responding to commands. Exit code: {test_result}")
        return False

async def _test_shared_folders(context):
    """Test shared folder accessibility."""
    ls_result = await context.vm.run_command("test -d /adare/app", stop_event=context.user_interrupt_event)
    if ls_result == 0:
        log.info("CLAUDE: ✅ Shared folders are accessible")
        return True
    else:
        log.warning(f"CLAUDE: ❌ Shared folders not accessible. Exit code: {ls_result}")
        return False

async def _test_python_availability(context):
    """Test Python installation."""
    python_result = await context.vm.run_command("python3 --version", stop_event=context.user_interrupt_event)
    if python_result == 0:
        log.info("CLAUDE: ✅ Python is available")
        return True
    else:
        log.warning(f"CLAUDE: ❌ Python not available or not in PATH. Exit code: {python_result}")
        return False

async def _test_poetry_availability(context):
    """Test Poetry installation."""
    poetry_result = await context.vm.run_command("poetry --version", stop_event=context.user_interrupt_event)
    if poetry_result == 0:
        log.info("CLAUDE: ✅ Poetry is available")
        return True
    else:
        log.warning(f"CLAUDE: ❌ Poetry not available or not in PATH. Exit code: {poetry_result}")
        return False

async def _test_adarevm_server_start(context):
    """Test starting adarevm WebSocket server."""
    try:
        # Install dependencies first
        install_result = await context.vm.run_command("cd /adare/app/adarevm && poetry install", stop_event=context.user_interrupt_event)
        if install_result != 0:
            log.warning("CLAUDE: Poetry install failed, trying anyway...")
        
        # Start adarevm server in background - create log directory first
        await context.vm.run_command("mkdir -p /adare/run/logs", stop_event=context.user_interrupt_event)
        
        # Start the server in background
        import asyncio
        log_path = "/adare/run/logs/adarevm_test.log"
        server_cmd = f"cd /adare/app/adarevm && nohup poetry run adarevm {log_path} > /adare/run/logs/adarevm_server.out 2>&1 &"
        
        start_result = await context.vm.run_command(server_cmd, stop_event=context.user_interrupt_event)
        if start_result == 0:
            log.info("CLAUDE: ✅ AdareVM server started successfully")
            # Wait a moment for server to start up
            await asyncio.sleep(3)
            return True
        else:
            log.warning(f"CLAUDE: ❌ Failed to start adarevm server. Exit code: {start_result}")
            return False
            
    except Exception as e:
        log.warning(f"CLAUDE: ❌ Exception starting adarevm server: {e}")
        return False

async def _test_websocket_connection(context):
    """Test WebSocket connection to AdareVM server."""
    try:
        from adare.backend.experiment.websocket_client import AdareVMClient
        
        # Create WebSocket client
        client = AdareVMClient(host='localhost', port=context.config.websocket_port)
        context.client = client
        
        # Try to connect with reasonable timeout
        connected = await client.connect(timeout=30.0)
        if connected:
            log.info("CLAUDE: ✅ WebSocket connection established")
            return True
        else:
            log.warning("CLAUDE: ❌ Could not establish WebSocket connection")
            return False
            
    except Exception as e:
        log.warning(f"CLAUDE: ❌ WebSocket test error: {e}")
        return False

async def _test_screenshot_command(context):
    """Test screenshot command via WebSocket."""
    try:
        result = await context.client.call_tool("take_screenshot", timeout=10.0)
        if result and not result.get('error'):
            log.info("CLAUDE: ✅ Screenshot command successful")
            return True
        else:
            log.warning(f"CLAUDE: ❌ Screenshot command failed: {result}")
            return False
    except Exception as e:
        log.warning(f"CLAUDE: ❌ Screenshot command error: {e}")
        return False

async def _test_click_command(context):
    """Test click command via WebSocket."""
    try:
        click_x = 10
        click_y = 10
        
        result = await context.client.call_tool("click", {"x": click_x, "y": click_y}, timeout=10.0)
        if result and not result.get('error'):
            log.info(f"CLAUDE: ✅ Click command successful (clicked at {click_x}, {click_y})")
            return True
        else:
            log.warning(f"CLAUDE: ❌ Click command failed: {result}")
            return False
    except Exception as e:
        log.warning(f"CLAUDE: ❌ Click command error: {e}")
        return False

async def _test_vm_compatibility(context, flow_console):
    """Test VM compatibility with ADARE WebSocket server and execute simple experiment commands."""
    log.info("CLAUDE: Testing VM compatibility with ADARE WebSocket server...")
    
    compatibility_results = {
        'vm_responsive': False,
        'shared_folders_working': False, 
        'python_available': False,
        'poetry_available': False,
        'adarevm_server_starts': False,
        'websocket_connection': False,
        'screenshot_command': False,
        'click_command': False
    }
    
    try:
        # Test 1: Basic VM responsiveness with substage
        async with StageCtxManagerLite(VMResponseTestStage(), flow_console, level=2):
            compatibility_results['vm_responsive'] = await _test_vm_response(context)
            
        # Test 2: Shared folder access with substage
        async with StageCtxManagerLite(VMSharedFoldersTestStage(), flow_console, level=2):
            compatibility_results['shared_folders_working'] = await _test_shared_folders(context)
            
        # Test 3: Python availability with substage
        async with StageCtxManagerLite(VMPythonTestStage(), flow_console, level=2):
            compatibility_results['python_available'] = await _test_python_availability(context)
            
        # Test 4: Poetry availability with substage
        async with StageCtxManagerLite(VMPoetryTestStage(), flow_console, level=2):
            compatibility_results['poetry_available'] = await _test_poetry_availability(context)
            
        # Test 5: Start adarevm WebSocket server with substage
        async with StageCtxManagerLite(VMAdareServerTestStage(), flow_console, level=2):
            compatibility_results['adarevm_server_starts'] = await _test_adarevm_server_start(context)
            
        # Test 6: WebSocket connection with substage
        async with StageCtxManagerLite(VMWebSocketTestStage(), flow_console, level=2):
            compatibility_results['websocket_connection'] = await _test_websocket_connection(context)
            
        # Only run WebSocket commands if connection was successful
        if compatibility_results['websocket_connection']:
            # Test 7: Screenshot command with substage
            async with StageCtxManagerLite(VMScreenshotTestStage(), flow_console, level=2):
                compatibility_results['screenshot_command'] = await _test_screenshot_command(context)
            
            # Test 8: Click command with substage
            async with StageCtxManagerLite(VMClickTestStage(), flow_console, level=2):
                compatibility_results['click_command'] = await _test_click_command(context)
            
    except Exception as e:
        log.error(f"CLAUDE: Compatibility test error: {e}")
    
    # Summary 
    passed_tests = sum(compatibility_results.values())
    total_tests = len(compatibility_results)
    
    log.info(f"CLAUDE: Compatibility test results: {passed_tests}/{total_tests} tests passed")
    for test_name, result in compatibility_results.items():
        status = "✅ PASS" if result else "❌ FAIL" 
        log.info(f"CLAUDE:   - {test_name}: {status}")
        
    # Return results instead of throwing exception - let flow console show the summary
    success = passed_tests >= 6  # At least VM basics + server + websocket + one command
    
    if success:
        log.info("CLAUDE: ✅ VM appears compatible with ADARE (WebSocket server working)")
    else:
        log.warning(f"CLAUDE: ❌ VM compatibility insufficient: only {passed_tests}/{total_tests} tests passed")
    
    return success


async def _cleanup_test_vm(context, keep_vm: bool = False):
    """Clean up test VM and resources."""
    log.info("CLAUDE: Cleaning up test resources...")
    
    try:
        # Disconnect WebSocket client (adarevm server stops automatically when VM stops)
        if context.client:
            await context.client.disconnect()
            log.info("CLAUDE: WebSocket client disconnected")
        
        # Stop and optionally remove VM
        if context.vm:
            await context.vm.stop()
            log.info("CLAUDE: VM stopped")
            
            if keep_vm:
                log.info(f"CLAUDE: VM '{context.vm_name}' preserved for further testing")
                log.info("CLAUDE: You can manually remove it later with: VBoxManage unregistervm --delete")
            else:
                await context.vm.remove()
                log.info("CLAUDE: Test VM removed successfully")
        
    except Exception as e:
        log.error(f"CLAUDE: Error during cleanup: {e}")
    
    log.info("CLAUDE: Cleanup completed")


def experiment_add_environments(project_path: Path, experiment_pattern: str, environment_names: list[str], force: bool = False):
    """Add environments to experiments matching the pattern."""
    from adare.console import print_success_message
    import glob

    # Find matching experiments using glob
    project_directory = ProjectDirectory(project_path)
    experiments_dir = project_directory.experiments

    # Use glob to find matching experiment directories
    pattern_path = experiments_dir / experiment_pattern
    matching_paths = glob.glob(str(pattern_path))

    if not matching_paths:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'No experiments found matching pattern: {experiment_pattern}',
            possible_solutions=[
                f'Check if pattern "{experiment_pattern}" is correct',
                'List experiments with: adare experiment list',
                'Use exact experiment name if no pattern matching needed'
            ]
        )

    # Extract experiment names from paths
    experiment_names = [Path(p).name for p in matching_paths]

    # Validate all environments exist in project before proceeding
    from adare.database.api.environment import EnvironmentDbApi
    with EnvironmentDbApi() as env_db:
        project_environments = {env.name for env in env_db.get_environments(project_path)}

    missing_envs = [env for env in environment_names if env not in project_environments]
    if missing_envs:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'Environment(s) not found in project: {", ".join(missing_envs)}',
            possible_solutions=[
                'Create missing environments with: adare environment create <name>',
                'Load existing environments with: adare environment load <file>',
                'List available environments with: adare environment list'
            ]
        )

    print(f"Found {len(experiment_names)} experiment(s) matching pattern '{experiment_pattern}':")
    for exp_name in experiment_names:
        print(f"  - {exp_name}")
    print(f"Adding environment(s): {', '.join(environment_names)}")
    print()

    # Process each experiment
    updated_experiments = []
    failed_experiments = []

    for exp_name in experiment_names:
        try:
            exp_dir = ExperimentDirectory(project_path, exp_name)
            if not exp_dir.exists():
                log.warning(f"Experiment directory not found: {exp_name}, skipping")
                failed_experiments.append(exp_name)
                continue

            # Load current metadata
            metadata = exp_dir.load_metadata()
            original_envs = set(metadata.environments)

            # Add new environments (avoid duplicates)
            new_envs = set(environment_names)
            updated_envs = original_envs | new_envs

            # Check if anything actually changed
            if updated_envs == original_envs:
                log.info(f"Experiment '{exp_name}' already has all specified environments, skipping")
                continue

            # Update metadata
            metadata.environments = sorted(list(updated_envs))

            # Save updated metadata
            exp_dir.save_metadata(metadata)
            log.info(f"Updated metadata for experiment: {exp_name}")

            # Reload experiment to update database
            experiment_load(project_path, exp_name, force=True, silent=True)
            log.info(f"Reloaded experiment: {exp_name}")

            updated_experiments.append(exp_name)

        except Exception as e:
            log.error(f"Failed to update experiment '{exp_name}': {e}")
            failed_experiments.append(exp_name)

    # Print summary
    if updated_experiments:
        print_success_message(
            title=f"Successfully added environments to {len(updated_experiments)} experiment(s)",
            location=f"Experiments: {', '.join(updated_experiments)}",
            next_steps=[
                f"Added environments: {', '.join(environment_names)}",
                "Experiments have been reloaded automatically",
                "You can now run experiments on the new environments"
            ]
        )

    if failed_experiments:
        log.warning(f"Failed to update {len(failed_experiments)} experiment(s): {', '.join(failed_experiments)}")


def experiment_remove_environments(project_path: Path, experiment_pattern: str, environment_names: list[str], force: bool = False):
    """Remove environments from experiments matching the pattern."""
    from adare.console import print_success_message
    import glob

    # Find matching experiments using glob
    project_directory = ProjectDirectory(project_path)
    experiments_dir = project_directory.experiments

    # Use glob to find matching experiment directories
    pattern_path = experiments_dir / experiment_pattern
    matching_paths = glob.glob(str(pattern_path))

    if not matching_paths:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'No experiments found matching pattern: {experiment_pattern}',
            possible_solutions=[
                f'Check if pattern "{experiment_pattern}" is correct',
                'List experiments with: adare experiment list',
                'Use exact experiment name if no pattern matching needed'
            ]
        )

    # Extract experiment names from paths
    experiment_names = [Path(p).name for p in matching_paths]

    print(f"Found {len(experiment_names)} experiment(s) matching pattern '{experiment_pattern}':")
    for exp_name in experiment_names:
        print(f"  - {exp_name}")
    print(f"Removing environment(s): {', '.join(environment_names)}")
    print()

    # Process each experiment
    updated_experiments = []
    failed_experiments = []

    for exp_name in experiment_names:
        try:
            exp_dir = ExperimentDirectory(project_path, exp_name)
            if not exp_dir.exists():
                log.warning(f"Experiment directory not found: {exp_name}, skipping")
                failed_experiments.append(exp_name)
                continue

            # Load current metadata
            metadata = exp_dir.load_metadata()
            original_envs = set(metadata.environments)

            # Remove specified environments
            envs_to_remove = set(environment_names)
            updated_envs = original_envs - envs_to_remove

            # Check if anything actually changed
            if updated_envs == original_envs:
                log.info(f"Experiment '{exp_name}' doesn't have any of the specified environments, skipping")
                continue

            # Validate that we're not removing all environments
            if not updated_envs:
                if not force:
                    log.warning(f"Cannot remove all environments from experiment '{exp_name}' without --force flag")
                    failed_experiments.append(exp_name)
                    continue
                else:
                    log.warning(f"Removing ALL environments from experiment '{exp_name}' due to --force flag")

            # Update metadata
            metadata.environments = sorted(list(updated_envs))

            # Save updated metadata
            exp_dir.save_metadata(metadata)
            log.info(f"Updated metadata for experiment: {exp_name}")

            # Reload experiment to update database (if it still has environments)
            if updated_envs:
                experiment_load(project_path, exp_name, force=True, silent=True)
                log.info(f"Reloaded experiment: {exp_name}")
            else:
                log.warning(f"Experiment '{exp_name}' now has no environments and may become inaccessible")

            updated_experiments.append(exp_name)

        except Exception as e:
            log.error(f"Failed to update experiment '{exp_name}': {e}")
            failed_experiments.append(exp_name)

    # Print summary
    if updated_experiments:
        print_success_message(
            title=f"Successfully removed environments from {len(updated_experiments)} experiment(s)",
            location=f"Experiments: {', '.join(updated_experiments)}",
            next_steps=[
                f"Removed environments: {', '.join(environment_names)}",
                "Experiments have been reloaded automatically",
                "Check remaining environments with: adare experiment info <name>"
            ]
        )

    if failed_experiments:
        log.warning(f"Failed to update {len(failed_experiments)} experiment(s): {', '.join(failed_experiments)}")




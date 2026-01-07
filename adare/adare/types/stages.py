import attrs
from datetime import datetime, timezone
import typing
from typing import ClassVar
import cattrs

from adarelib.constants import StatusEnum

# -------------------------------
# Stage Registry Infrastructure
# -------------------------------

_stage_registry: dict[str, typing.Type["Stage"]] = {}

def register_stage(cls: typing.Type["Stage"]) -> typing.Type["Stage"]:
    instance = cls()
    if not hasattr(instance, "name"):
        raise ValueError(f"Cannot register stage without 'name': {cls}")
    _stage_registry[instance.name] = cls
    return cls
def get_stage_class(name: str) -> typing.Optional[typing.Type["Stage"]]:
    return _stage_registry.get(name)

# -------------------------------
# cattrs Converter Setup
# -------------------------------

converter = cattrs.Converter()

# Handle datetime → str and back
converter.register_unstructure_hook(datetime, lambda dt: dt.isoformat() if dt else None)
converter.register_structure_hook(datetime, lambda s, _: datetime.fromisoformat(s) if s else None)

# Handle StatusEnum → int and back
converter.register_unstructure_hook(StatusEnum, lambda e: int(e))
converter.register_structure_hook(StatusEnum, lambda i, _: StatusEnum(i))

# -------------------------------
# Stage Base Class
# -------------------------------

@attrs.define
class Stage:
    # Class-level metadata
    name: ClassVar[str] = 'stage'
    msg: ClassVar[str] = 'todo ...'
    description: ClassVar[str] = 'stage description'
    parent: ClassVar[typing.Optional[str]] = None
    optional: ClassVar[bool] = False

    # Runtime state (instance fields)
    start_time: typing.Optional[datetime] = None
    end_time: typing.Optional[datetime] = None
    status: int = attrs.field(default=StatusEnum.NONE)
    sub_msg: str = ''
    result_status: int = attrs.field(default=StatusEnum.NONE)

    def __str__(self):
        return f'{self.name}: {self.msg}'

    def start(self):
        self.start_time = datetime.now(timezone.utc)

    def end(self, status: int = StatusEnum.FINISHED):
        self.end_time = datetime.now(timezone.utc)
        if self.status == StatusEnum.NONE:
            self.status = status

    def set_status(self, status: int):
        self.status = status

    def to_dict(self) -> dict:
        data = converter.unstructure(self)
        # Inject class-level metadata into the dict
        data.update({
            'name': self.name,
            'msg': self.msg,
            'description': self.description,
            'parent': self.parent,
            'optional': self.optional,
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Stage":
        stage_cls = get_stage_class(data["name"])
        if not stage_cls:
            raise ValueError(f"Unknown stage: {data['name']}")
        return converter.structure(data, stage_cls)

    @classmethod
    def get_subclasses(cls) -> list[type]:
        """Recursively get all subclasses of this Stage class."""
        subclasses = set()
        def recurse(sub):
            for sc in sub.__subclasses__():
                subclasses.add(sc)
                recurse(sc)
        recurse(cls)
        return list(subclasses)

# ----------------------------------
# Concrete Stages
# ----------------------------------

@register_stage
@attrs.define
class VMRunStage(Stage):
    name: ClassVar[str] = 'vm_start'
    msg: ClassVar[str] = 'Starting Virtual Machine'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMStopStage(Stage):
    name: ClassVar[str] = 'vm_stop'
    msg: ClassVar[str] = 'Stopping Virtual Machine'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class VMDestroyStage(Stage):
    name: ClassVar[str] = 'vm_destroy'
    msg: ClassVar[str] = 'Destroying Virtual Machine'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class VMWaitTillReadyStage(Stage):
    name: ClassVar[str] = 'vm_wait_till_ready'
    msg: ClassVar[str] = 'Waiting until VM is ready'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMStartStage(Stage):
    name: ClassVar[str] = 'vm_start'
    msg: ClassVar[str] = 'Starting virtual machine'
    description: ClassVar[str] = 'Booting the VM via hypervisor'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMGuestAgentWaitStage(Stage):
    name: ClassVar[str] = 'vm_guest_agent_wait'
    msg: ClassVar[str] = 'Waiting for guest system to be ready'
    description: ClassVar[str] = 'Waiting for guest agent and display server'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMCreateStage(Stage):
    name: ClassVar[str] = 'vm_create'
    msg: ClassVar[str] = 'Creating Virtual Machine'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMDiskPreparationStage(Stage):
    name: ClassVar[str] = 'vm_disk_preparation'
    msg: ClassVar[str] = 'Preparing VM disk image'
    description: ClassVar[str] = 'Converting disk format and creating experiment environment'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMIntegrityVerificationStage(Stage):
    name: ClassVar[str] = 'vm_integrity_verification'
    msg: ClassVar[str] = 'Verifying VM file integrity'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMImportStage(Stage):
    name: ClassVar[str] = 'vm_import'
    msg: ClassVar[str] = 'Importing VM'
    parent: ClassVar[str] = 'vm_disk_preparation'

@register_stage
@attrs.define
class VMDiskOverlayCreationStage(Stage):
    name: ClassVar[str] = 'vm_disk_overlay_creation'
    msg: ClassVar[str] = 'Creating experiment overlay disk'
    description: ClassVar[str] = 'Creating copy-on-write overlay for experiment isolation'
    parent: ClassVar[str] = 'vm_disk_preparation'

@register_stage
@attrs.define
class VMDiskFormatDetectionStage(Stage):
    name: ClassVar[str] = 'vm_disk_format_detection'
    msg: ClassVar[str] = 'Detecting disk format'
    description: ClassVar[str] = 'Determining source disk format (qcow2, vmdk, ova, etc.)'
    parent: ClassVar[str] = 'vm_disk_preparation'

@register_stage
@attrs.define
class VMDiskConversionStage(Stage):
    name: ClassVar[str] = 'vm_disk_conversion'
    msg: ClassVar[str] = 'Converting disk format to qcow2'
    description: ClassVar[str] = 'Converting source disk to QEMU-compatible qcow2 format'
    parent: ClassVar[str] = 'vm_disk_preparation'

@register_stage
@attrs.define
class VMNetworkingStage(Stage):
    name: ClassVar[str] = 'vm_networking_setup'
    msg: ClassVar[str] = 'Configuring VM networking'
    description: ClassVar[str] = 'Setting up port forwarding for WebSocket communication'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMFileTransferSetupStage(Stage):
    name: ClassVar[str] = 'vm_file_transfer_setup'
    msg: ClassVar[str] = 'Setting up file transfer to VM'
    description: ClassVar[str] = 'Transferring files to VM (shared folders for VirtualBox, disk copy for QEMU)'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMMountSharedDirectoriesStage(Stage):
    name: ClassVar[str] = 'vm_mount_shared_directories'
    msg: ClassVar[str] = 'Mounting shared directories in guest'
    description: ClassVar[str] = 'Mounting VirtualBox shared folders inside the VM (VirtualBox-specific, post-boot)'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class ExperimentIntegrityCheckStage(Stage):
    name: ClassVar[str] = 'integrity_check_experiment'
    msg: ClassVar[str] = 'Checking experiment integrity'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class ProjectIntegrityCheckStage(Stage):
    name: ClassVar[str] = 'integrity_check_project'
    msg: ClassVar[str] = 'Checking project integrity'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class InstallAdareVMStage(Stage):
    name: ClassVar[str] = 'install_adare_vm'
    msg: ClassVar[str] = 'Installing AdareVM'
    parent: ClassVar[str] = 'software_installation'

@register_stage
@attrs.define
class ConnectToVMStage(Stage):
    name: ClassVar[str] = 'connect_to_vm'
    msg: ClassVar[str] = 'Connecting to VM via WebSocket'
    parent: ClassVar[str] = 'software_installation'

@register_stage
@attrs.define
class InstallationsStage(Stage):
    name: ClassVar[str] = 'environment_installations'
    msg: ClassVar[str] = 'Installing environment software'
    parent: ClassVar[str] = 'software_installation'

@register_stage
@attrs.define
class TestfunctionDependenciesStage(Stage):
    name: ClassVar[str] = 'testfunction_dependencies'
    msg: ClassVar[str] = 'Installing testfunction dependencies'
    description: ClassVar[str] = 'Installing Python packages required by testfunctions via Poetry'
    parent: ClassVar[str] = 'experiment_execution'

@register_stage
@attrs.define
class ExperimentRunStage(Stage):
    name: ClassVar[str] = 'experiment_run'
    msg: ClassVar[str] = 'Running the playbook'
    parent: ClassVar[str] = 'experiment_execution'

@register_stage
@attrs.define
class SystemInfoCollectionStage(Stage):
    name: ClassVar[str] = 'system_info_collection'
    msg: ClassVar[str] = 'Collecting system information'
    description: ClassVar[str] = 'Collecting OS info and installed software/packages from guest VM'
    parent: ClassVar[str] = 'experiment_execution'

@register_stage
@attrs.define
class ExperimentTestStage(Stage):
    name: ClassVar[str] = 'experiment_test'
    msg: ClassVar[str] = 'Running test'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiClickStage(Stage):
    name: ClassVar[str] = 'gui_click'
    msg: ClassVar[str] = 'GUI click action'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiIdleStage(Stage):
    name: ClassVar[str] = 'gui_idle'
    msg: ClassVar[str] = 'GUI idle wait'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentGuiFindStage(Stage):
    name: ClassVar[str] = 'gui_find'
    msg: ClassVar[str] = 'GUI find element'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentActionStage(Stage):
    name: ClassVar[str] = 'experiment_action'
    msg: ClassVar[str] = 'Executing action'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentActionFindStage(Stage):
    name: ClassVar[str] = 'action_find'
    msg: ClassVar[str] = 'Finding target'
    parent: ClassVar[str] = 'experiment_action'

@register_stage
@attrs.define
class ExperimentActionExecuteStage(Stage):
    name: ClassVar[str] = 'action_execute'
    msg: ClassVar[str] = 'Executing action'
    parent: ClassVar[str] = 'experiment_action'

@register_stage
@attrs.define
class ExperimentGuiKeypressStage(Stage):
    name: ClassVar[str] = 'gui_keypress'
    msg: ClassVar[str] = 'GUI keypress action'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class ExperimentCommandStage(Stage):
    name: ClassVar[str] = 'experiment_command'
    msg: ClassVar[str] = 'Executing command'
    parent: ClassVar[str] = 'experiment_run'

@register_stage
@attrs.define
class VagrantBoxExistCheckStage(Stage):
    name: ClassVar[str] = 'vm_exist_check'
    msg: ClassVar[str] = 'Checking if Vagrant box exists'

# ----------------------------------
# Top-Level Parent Stages (Main Progress Phases)
# ----------------------------------

@register_stage
@attrs.define
class ExperimentPreparationStage(Stage):
    name: ClassVar[str] = 'experiment_preparation'
    msg: ClassVar[str] = 'Preparing experiment'
    description: ClassVar[str] = 'Setting up directories, validating configuration, and performing integrity checks'

@register_stage
@attrs.define
class VirtualMachineSetupStage(Stage):
    name: ClassVar[str] = 'vm_setup'
    msg: ClassVar[str] = 'Setting up Virtual Machine'
    description: ClassVar[str] = 'Creating, starting, and configuring the virtual machine'

@register_stage
@attrs.define
class SoftwareInstallationStage(Stage):
    name: ClassVar[str] = 'software_installation'
    msg: ClassVar[str] = 'Installing software and services'
    description: ClassVar[str] = 'Installing AdareVM, connecting services, and setting up environment'

@register_stage
@attrs.define
class ExperimentExecutionStage(Stage):
    name: ClassVar[str] = 'experiment_execution'
    msg: ClassVar[str] = 'Executing experiment'
    description: ClassVar[str] = 'Running the experiment playbook and tests'

@register_stage
@attrs.define
class CleanupShutdownStage(Stage):
    name: ClassVar[str] = 'cleanup_shutdown'
    msg: ClassVar[str] = 'Shutdown & Cleanup'
    description: ClassVar[str] = 'Finalizing results and cleaning up resources'

# ----------------------------------
# Sub-Stages for Experiment Preparation (Consolidated)
# ----------------------------------

@register_stage
@attrs.define
class SetupExperimentEnvironmentStage(Stage):
    name: ClassVar[str] = 'setup_experiment_environment'
    msg: ClassVar[str] = 'Setting up experiment environment'
    description: ClassVar[str] = 'Setting up directories, validating playbook, and resolving environment'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class ValidateIntegrityStage(Stage):
    name: ClassVar[str] = 'validate_integrity'
    msg: ClassVar[str] = 'Validating experiment and project integrity'
    description: ClassVar[str] = 'Checking experiment integrity and project integrity'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class PrepareRunEnvironmentStage(Stage):
    name: ClassVar[str] = 'prepare_run_environment'
    msg: ClassVar[str] = 'Preparing run environment'
    description: ClassVar[str] = 'Checking application data and creating run directory'
    parent: ClassVar[str] = 'experiment_preparation'

@register_stage
@attrs.define
class StartComputerVisionServerStage(Stage):
    name: ClassVar[str] = 'start_computer_vision_server'
    msg: ClassVar[str] = 'Starting computer vision server'
    parent: ClassVar[str] = 'experiment_preparation'

# ----------------------------------
# Sub-Stages for Cleanup & Shutdown
# ----------------------------------

@register_stage
@attrs.define
class FinalizeStage(Stage):
    name: ClassVar[str] = 'finalize'
    msg: ClassVar[str] = 'Finalizing results'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class ShutdownComputerVisionServerStage(Stage):
    name: ClassVar[str] = 'shutdown_computer_vision_server'
    msg: ClassVar[str] = 'Stopping computer vision server'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class ShutdownWebSocketStage(Stage):
    name: ClassVar[str] = 'shutdown_websocket'
    msg: ClassVar[str] = 'Disconnecting WebSocket'
    parent: ClassVar[str] = 'cleanup_shutdown'

# ----------------------------------
# VM Snapshot Management Stages
# ----------------------------------

@register_stage
@attrs.define
class VMSnapshotRestoreStage(Stage):
    name: ClassVar[str] = 'vm_snapshot_restore'
    msg: ClassVar[str] = 'Resetting VM to base snapshot'
    description: ClassVar[str] = 'Fast restore from base snapshot for quick setup'
    parent: ClassVar[str] = 'vm_setup'

@register_stage  
@attrs.define
class VMSnapshotCreateStage(Stage):
    name: ClassVar[str] = 'vm_snapshot_create'
    msg: ClassVar[str] = 'Creating base snapshot'
    description: ClassVar[str] = 'Creating base snapshot for future fast restores'
    parent: ClassVar[str] = 'vm_setup'

@register_stage
@attrs.define
class VMExperimentSnapshotStage(Stage):
    name: ClassVar[str] = 'vm_experiment_snapshot' 
    msg: ClassVar[str] = 'Creating experiment snapshot'
    description: ClassVar[str] = 'Creating snapshot for experiment recovery/debugging'
    parent: ClassVar[str] = 'cleanup_shutdown'

@register_stage
@attrs.define
class VMTestSetupStage(Stage):
    name: ClassVar[str] = 'vm_test_setup'
    msg: ClassVar[str] = 'VM Compatibility Test Setup'
    description: ClassVar[str] = 'Setting up VM compatibility test environment'
    parent: ClassVar[typing.Optional[str]] = None

@register_stage
@attrs.define
class VMCompatibilityTestStage(Stage):
    name: ClassVar[str] = 'vm_compatibility_test'
    msg: ClassVar[str] = 'VM Compatibility Testing'
    description: ClassVar[str] = 'Running ADARE compatibility tests on the VM'
    parent: ClassVar[typing.Optional[str]] = None

@register_stage
@attrs.define
class VMTestCleanupStage(Stage):
    name: ClassVar[str] = 'vm_test_cleanup'
    msg: ClassVar[str] = 'VM Test Cleanup'
    description: ClassVar[str] = 'Cleaning up VM test resources'
    parent: ClassVar[typing.Optional[str]] = None

# VM Test Substages - Individual compatibility tests
@register_stage
@attrs.define
class VMResponseTestStage(Stage):
    name: ClassVar[str] = 'vm_response_test'
    msg: ClassVar[str] = 'Testing VM command responsiveness'
    description: ClassVar[str] = 'Verify VM can execute basic commands'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMSharedFoldersTestStage(Stage):
    name: ClassVar[str] = 'vm_shared_folders_test'
    msg: ClassVar[str] = 'Testing shared folder accessibility'
    description: ClassVar[str] = 'Verify VM can access mounted shared folders'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMPythonTestStage(Stage):
    name: ClassVar[str] = 'vm_python_test'
    msg: ClassVar[str] = 'Testing Python installation'
    description: ClassVar[str] = 'Verify Python is available in VM'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMPoetryTestStage(Stage):
    name: ClassVar[str] = 'vm_poetry_test'
    msg: ClassVar[str] = 'Testing Poetry installation'
    description: ClassVar[str] = 'Verify Poetry package manager is available'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMAdareServerTestStage(Stage):
    name: ClassVar[str] = 'vm_adare_server_test'
    msg: ClassVar[str] = 'Starting AdareVM server'
    description: ClassVar[str] = 'Install dependencies and start AdareVM WebSocket server'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMWebSocketTestStage(Stage):
    name: ClassVar[str] = 'vm_websocket_test'
    msg: ClassVar[str] = 'Testing WebSocket connection'
    description: ClassVar[str] = 'Establish WebSocket connection to AdareVM server'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMScreenshotTestStage(Stage):
    name: ClassVar[str] = 'vm_screenshot_test'
    msg: ClassVar[str] = 'Testing screenshot capture'
    description: ClassVar[str] = 'Verify screenshot functionality via WebSocket'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMClickTestStage(Stage):
    name: ClassVar[str] = 'vm_click_test'
    msg: ClassVar[str] = 'Testing mouse click commands'
    description: ClassVar[str] = 'Verify mouse click functionality via WebSocket'
    parent: ClassVar[str] = 'vm_compatibility_test'

@register_stage
@attrs.define
class VMFileTransferRetrievalStage(Stage):
    name: ClassVar[str] = 'vm_file_transfer_retrieval'
    msg: ClassVar[str] = 'Retrieving artifacts from VM'
    description: ClassVar[str] = 'Copying experiment artifacts from VM to host'
    parent: ClassVar[str] = 'vm_destroy'
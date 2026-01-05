"""
Abstract base class for VM lifecycle management across hypervisors.

This module defines the strategy pattern interface for hypervisor-specific
VM lifecycle operations. Each hypervisor implementation (VirtualBox, QEMU, etc.)
must provide a concrete strategy that handles its specific requirements.
"""
from abc import ABC, abstractmethod
import threading
from typing import Optional
import logging

log = logging.getLogger(__name__)


class AbstractVMLifecycleStrategy(ABC):
    """
    Abstract strategy for VM lifecycle management across hypervisors.

    This class defines the interface that all hypervisor-specific lifecycle
    strategies must implement. It handles the orchestration of VM preparation,
    file transfer, initialization, and cleanup in a way that abstracts away
    the differences between hypervisors like VirtualBox (shared folders) and
    QEMU (libguestfs).
    """

    @abstractmethod
    async def prepare_vm_for_experiment(self, context):
        """
        Create VM instance and allocate resources (port, instance name).

        This method handles hypervisor-specific VM creation and resource
        allocation. It should:
        - Create or import the VM instance
        - Allocate unique ports for communication
        - Configure VM-specific settings (CPU, memory, etc.)
        - Create base snapshots if needed

        Args:
            context: ExperimentRunCtx containing all experiment configuration

        Raises:
            VMSetupError: If VM preparation fails
        """
        pass

    @abstractmethod
    async def setup_networking(self, context):
        """
        Setup networking configuration (port forwarding, network interfaces).

        This method handles hypervisor-specific networking setup:
        - VirtualBox: Port forwarding via VBoxManage
        - QEMU: Port forwarding via config + libvirt XML

        Called after VM creation but before file transfer.

        Args:
            context: ExperimentRunCtx containing configuration

        Raises:
            VMSetupError: If networking setup fails
        """
        pass

    @abstractmethod
    async def setup_file_transfer(self, context):
        """
        Setup mechanism for transferring files to/from VM.

        This method handles hypervisor-specific file transfer setup:
        - VirtualBox: Configure shared folders (VM can be running)
        - QEMU: Stop VM, use libguestfs to place files on disk

        The timing and mechanism differ per hypervisor but are abstracted
        from the caller.

        Args:
            context: ExperimentRunCtx containing directories and configuration

        Raises:
            VMSetupError: If file transfer setup fails
        """
        pass

    @abstractmethod
    async def start_and_initialize_vm(self, context):
        """
        Start VM and perform post-boot initialization.

        This method handles hypervisor-specific VM startup and initialization:
        - VirtualBox: start() -> mount shared folders
        - QEMU: start() -> wait for guest agent (files already on disk)

        Args:
            context: ExperimentRunCtx containing VM and configuration

        Raises:
            VMSetupError: If VM start or initialization fails
        """
        pass

    @abstractmethod
    async def retrieve_artifacts(self, context, post_interrupt: bool = False):
        """
        Retrieve experiment artifacts from VM.

        This method handles hypervisor-specific artifact retrieval:
        - VirtualBox: No-op (artifacts already on host via shared folders)
        - QEMU: stop() -> libguestfs -> copy artifacts -> cleanup

        Args:
            context: ExperimentRunCtx containing VM and output directories
            post_interrupt: If True, we're in post-interrupt cleanup (may affect behavior)

        Raises:
            VMSetupError: If artifact retrieval fails
        """
        pass

    @abstractmethod
    async def cleanup_vm(self, context, post_interrupt: bool = False):
        """
        Cleanup VM resources, handle snapshots, release instance.

        This method handles hypervisor-specific cleanup operations:
        - Create experiment snapshot if requested
        - Clean up port forwarding
        - Release VM instance for reuse
        - Handle interrupted experiments gracefully

        Args:
            context: ExperimentRunCtx containing VM and configuration
            post_interrupt: True if cleaning up after user interrupt

        Raises:
            VMSetupError: If cleanup fails (logged but not raised)
        """
        pass

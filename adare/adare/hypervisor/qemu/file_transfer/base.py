"""
Abstract base class for file transfer strategies.

Defines the interface that all file transfer implementations must follow.
Each strategy handles a different mechanism for getting files to/from QEMU guests:
- VirtioFS: shared directories via virtio-fs filesystem device
- Libguestfs: offline disk manipulation via guestfish CLI
- QGA: file transfer via QEMU Guest Agent guest-file-* operations
"""
from abc import ABC, abstractmethod
from typing import Any


class FileTransferStrategy(ABC):
    """Strategy interface for transferring files to/from QEMU guests.

    The lifecycle calls these methods in order:
    1. setup() - before VM boot (prepare transfer mechanism)
    2. post_boot_transfer() - after VM boot (mount shares, upload files, etc.)
    3. retrieve_artifacts() - at experiment end (download results)
    """

    @property
    @abstractmethod
    def setup_description(self) -> str:
        """What setup() actually does (e.g. 'Configuring VirtioFS shares')."""

    @property
    @abstractmethod
    def post_boot_description(self) -> str:
        """What post_boot_transfer() does (e.g. 'Mounting VirtioFS shares')."""

    @property
    @abstractmethod
    def retrieval_description(self) -> str:
        """What retrieve_artifacts() does (e.g. 'Downloading via QGA')."""

    @property
    def has_post_boot_transfer(self) -> bool:
        """Whether this strategy needs post-boot transfer work."""
        return True

    @abstractmethod
    async def setup(self, context: Any) -> None:
        """Prepare transfer mechanism (before VM boot).

        Called from setup_file_transfer(). May modify VM config,
        create shared directories, copy files to disk, etc.

        Args:
            context: ExperimentRunCtx with directories and VM
        """

    @abstractmethod
    async def post_boot_transfer(self, context: Any) -> None:
        """Perform post-boot file transfer actions.

        Called from start_and_initialize_vm() after guest agent is ready.
        May mount filesystems, upload files via QGA, etc.

        Args:
            context: ExperimentRunCtx with directories and VM
        """

    @abstractmethod
    async def retrieve_artifacts(self, context: Any) -> None:
        """Retrieve experiment artifacts from the guest.

        Called from retrieve_artifacts(). Downloads logs, artifacts, etc.

        Args:
            context: ExperimentRunCtx with directories and VM
        """

    @abstractmethod
    def requires_vm_stop_for_retrieval(self) -> bool:
        """Whether VM must be stopped before artifact retrieval.

        Returns:
            True if VM must be stopped first (libguestfs),
            False if VM should stay running (virtiofs, qga).
        """

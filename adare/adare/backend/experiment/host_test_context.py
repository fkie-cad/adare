"""
Host Test Context for ADARE.

This module provides the service container (context) that is passed to
host-side tests, enabling clean dependency injection and modular test design.
"""

from pathlib import Path

import attrs

from adare.backend.experiment.host_services import (
    CVService,
    GuestCommandProxy,
    GuestFileProxy,
    ScreenshotService,
    VMFileService,
)


@attrs.define
class HostTestContext:
    """
    Service container for host-side tests.

    This context provides all services that host-side tests may need,
    using dependency injection for clean separation and testability.

    Services:
        - cv: Computer vision (text/icon detection via CV server)
        - screenshot: Screenshot capture via WebSocket
        - vm_file: File access from VM (pulls files to host)
        - guest_file: Direct QGA file proxy (host-mode only, optional)
        - guest_command: Direct QGA command proxy (host-mode only, optional)

    Attributes:
        cv: CVService instance for visual analysis
        screenshot: ScreenshotService instance for capturing screenshots
        vm_file: VMFileService instance for VM file access
        guest_file: GuestFileProxy for QGA-based file transfer (host-mode)
        guest_command: GuestCommandProxy for QGA-based commands (host-mode)
        playbook_dir: Path to playbook directory (for relative paths)
        experiment_dir: Path to experiment directory
    """

    # Core services
    cv: CVService
    screenshot: ScreenshotService
    vm_file: VMFileService

    # Host-mode QGA services (optional - only set in host test mode)
    guest_file: GuestFileProxy | None = None
    guest_command: GuestCommandProxy | None = None

    # Context paths
    playbook_dir: Path = attrs.field(default=Path('.'))
    experiment_dir: Path = attrs.field(default=Path('.'))

    @classmethod
    def create(
        cls,
        mcp_client,
        websocket_client,
        action_executor,
        playbook_dir: Path,
        experiment_dir: Path
    ) -> "HostTestContext":
        """
        Factory method to create HostTestContext with all services (agent mode).

        Args:
            mcp_client: MCP client for CV server
            websocket_client: WebSocket client for screenshots
            action_executor: ActionExecutor for file pulls
            playbook_dir: Path to playbook directory
            experiment_dir: Path to experiment directory

        Returns:
            HostTestContext instance with all services initialized
        """
        # Create service instances
        cv_service = CVService(mcp_client)
        screenshot_service = ScreenshotService(websocket_client)
        vm_file_service = VMFileService(action_executor)

        return cls(
            cv=cv_service,
            screenshot=screenshot_service,
            vm_file=vm_file_service,
            playbook_dir=playbook_dir,
            experiment_dir=experiment_dir
        )

    @classmethod
    def create_host_mode(
        cls,
        vm,
        guest_os: str,
        playbook_dir: Path,
        experiment_dir: Path,
        mcp_client=None,
    ) -> "HostTestContext":
        """
        Factory method to create HostTestContext for host-mode execution.

        In host mode there's no WebSocket client. CV/screenshot services
        require the MCP client (optional). GuestFileProxy and GuestCommandProxy
        are available for QGA-based operations.

        Args:
            vm: QEMU VM instance
            guest_os: Guest OS identifier
            playbook_dir: Path to playbook directory
            experiment_dir: Path to experiment directory
            mcp_client: MCP client for CV server (optional)

        Returns:
            HostTestContext with QGA-based services
        """
        from adare.backend.experiment.host_services.guest_command_proxy import GuestCommandProxy
        from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy

        guest_file = GuestFileProxy(vm=vm, guest_os=guest_os)
        guest_command = GuestCommandProxy(vm=vm, guest_os=guest_os)

        # CV service is available if MCP client is provided
        cv_service = CVService(mcp_client) if mcp_client else None
        # No WebSocket-based screenshot/vm_file in host mode
        screenshot_service = None
        vm_file_service = None

        return cls(
            cv=cv_service,
            screenshot=screenshot_service,
            vm_file=vm_file_service,
            guest_file=guest_file,
            guest_command=guest_command,
            playbook_dir=playbook_dir,
            experiment_dir=experiment_dir
        )

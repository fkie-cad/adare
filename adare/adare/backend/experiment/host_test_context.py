"""
Host Test Context for ADARE.

This module provides the service container (context) that is passed to
host-side tests, enabling clean dependency injection and modular test design.
"""

import attrs
from pathlib import Path
from typing import Optional

from adare.backend.experiment.host_services import (
    CVService,
    ScreenshotService,
    VMFileService
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

    Attributes:
        cv: CVService instance for visual analysis
        screenshot: ScreenshotService instance for capturing screenshots
        vm_file: VMFileService instance for VM file access
        playbook_dir: Path to playbook directory (for relative paths)
        experiment_dir: Path to experiment directory
    """

    # Core services
    cv: CVService
    screenshot: ScreenshotService
    vm_file: VMFileService

    # Context paths
    playbook_dir: Path
    experiment_dir: Path

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
        Factory method to create HostTestContext with all services.

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
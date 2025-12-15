"""
Command builders for installing and running adarevm agent in VMs.

This module provides a clean separation of concerns for building platform-specific
commands to install and run the adarevm agent. It uses the Builder pattern to
handle the complexity of 8 different execution paths:
- Windows/Linux × Conda/Poetry × Wheels/Editable

The refactoring reduces the main install_and_run_adare_vm function from 191 lines
with deep nesting to ~50 lines of clear orchestration.
"""

# external imports
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import threading

log = logging.getLogger(__name__)


@dataclass
class EnvironmentInfo:
    """Information about the detected Python environment in the VM."""
    use_conda: bool
    conda_env_exists: bool
    miniforge_path: Optional[str]
    platform: str  # 'windows' or 'linux'


@dataclass
class CommandSet:
    """Collection of commands needed to set up and run adarevm."""
    setup_commands: List[str]  # PATH setup, firewall rules, etc.
    install_command: str
    run_command: str
    run_cwd: Optional[str]
    skip_installation: bool


class AgentCommandBuilder(ABC):
    """Abstract base for building platform-specific agent installation commands."""

    def __init__(self, wheels_dir: Path, shared_folders: dict, websocket_port: int):
        self.wheels_dir = wheels_dir
        self.shared_folders = shared_folders
        self.websocket_port = websocket_port
        self.wheels_available = wheels_dir.exists() and bool(list(wheels_dir.glob('*.whl')))

    @abstractmethod
    async def build_setup_commands(self, env_info: EnvironmentInfo) -> List[str]:
        """Build platform-specific setup commands (PATH, firewall, etc.)."""
        pass

    @abstractmethod
    def build_install_command(self, env_info: EnvironmentInfo) -> str:
        """Build installation command based on environment."""
        pass

    @abstractmethod
    def build_run_command(self, env_info: EnvironmentInfo) -> tuple[str, Optional[str]]:
        """Build run command and optional cwd. Returns (command, cwd)."""
        pass

    async def build_commands(self, env_info: EnvironmentInfo, vm, stop_event: threading.Event) -> CommandSet:
        """Main entry point: build complete command set."""
        setup_commands = await self.build_setup_commands(env_info)
        install_command = self.build_install_command(env_info)
        run_command, run_cwd = self.build_run_command(env_info)

        # Check if we can skip installation
        skip_installation = await self._check_skip_installation(env_info, vm, stop_event)

        return CommandSet(
            setup_commands=setup_commands,
            install_command=install_command,
            run_command=run_command,
            run_cwd=run_cwd,
            skip_installation=skip_installation
        )

    async def _check_skip_installation(self, env_info: EnvironmentInfo, vm, stop_event: threading.Event) -> bool:
        """Unified skip-installation check (eliminates 4 duplicates)."""
        if not self.wheels_available:
            return False

        try:
            from adare.backend.experiment.agent_installer import should_skip_installation
            return await should_skip_installation(
                wheels_dir=self.wheels_dir,
                vm=vm,
                use_conda=env_info.use_conda,
                platform=env_info.platform,
                stop_event=stop_event
            )
        except Exception as e:
            log.warning(f"Version check failed: {e}, proceeding with installation")
            return False


class WindowsAgentCommandBuilder(AgentCommandBuilder):
    """Windows-specific command builder."""

    async def build_setup_commands(self, env_info: EnvironmentInfo) -> List[str]:
        """Build Windows setup commands."""
        commands = []

        # Firewall rule for adarevm WebSocket server
        firewall_cmd = f'New-NetFirewallRule -DisplayName "adarevm" -Direction Inbound -Action Allow -Protocol TCP -LocalPort {self.websocket_port}'
        commands.append(firewall_cmd)

        # PATH setup for project-wide and experiment-specific tools
        commands.append(r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\shared\tools", "User")')
        commands.append(r'[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\adare\experiment\shared\tools", "User")')

        # Mount VirtualBox shared folders temporarily (forces network provider initialization)
        commands.append(r'net use Z: \\vboxsvr\adare; net use Z: /delete')

        return commands

    def build_install_command(self, env_info: EnvironmentInfo) -> str:
        """Build Windows install command."""
        if env_info.use_conda:
            return self._build_conda_install_command()
        else:
            return self._build_poetry_install_command()

    def _build_conda_install_command(self) -> str:
        """Build Conda installation command."""
        if self.wheels_available:
            # PowerShell array expansion: @(Get-ChildItem ...) forces wildcard expansion
            # before pip sees the arguments. PowerShell doesn't expand wildcards in
            # base64-encoded commands, so we must explicitly use Get-ChildItem.
            return r'%USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install --force-reinstall @(Get-ChildItem \\vboxsvr\adare\wheels\*.whl | Select-Object -ExpandProperty FullName)'
        else:
            # Editable install from shared folder source
            return r'cd \\vboxsvr\adare\adarelib; %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install .; cd \\vboxsvr\adare\adarevm; %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install .'

    def _build_poetry_install_command(self) -> str:
        """Build Poetry installation command."""
        if self.wheels_available:
            return r'pip install --force-reinstall @(Get-ChildItem \\vboxsvr\adare\wheels\*.whl | Select-Object -ExpandProperty FullName)'
        else:
            # Editable install via Poetry
            return r'cd \\vboxsvr\adare\adarevm; poetry install'

    def build_run_command(self, env_info: EnvironmentInfo) -> tuple[str, Optional[str]]:
        """Build Windows run command."""
        if env_info.use_conda:
            if self.wheels_available:
                # Wheel: call directly from conda env (no UNC path navigation)
                return (r'%USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare adarevm', None)
            else:
                # Editable: cd to source directory for Poetry context
                return (r'cd \\vboxsvr\adare\adarevm; %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare adarevm', None)
        else:
            if self.wheels_available:
                # Wheel: installed in PATH via pip
                return ('adarevm', None)
            else:
                # Editable: poetry run from source directory
                return (r'cd \\vboxsvr\adare\adarevm; poetry run adarevm', None)


class LinuxAgentCommandBuilder(AgentCommandBuilder):
    """Linux-specific command builder."""

    async def build_setup_commands(self, env_info: EnvironmentInfo) -> List[str]:
        """Build Linux setup commands."""
        return [
            # Add project-wide tools to PATH
            "grep -qxF 'export PATH=$PATH:/adare/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/shared/tools' >> ~/.bashrc && source ~/.bashrc",
            # Add experiment-specific tools to PATH
            "grep -qxF 'export PATH=$PATH:/adare/experiment/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/experiment/shared/tools' >> ~/.bashrc && source ~/.bashrc"
        ]

    def build_install_command(self, env_info: EnvironmentInfo) -> str:
        """Build Linux install command."""
        if env_info.use_conda:
            return self._build_conda_install_command()
        else:
            return self._build_poetry_install_command()

    def _build_conda_install_command(self) -> str:
        """Build Conda installation command."""
        if self.wheels_available:
            # Wheel install + X11 permission for GUI automation
            return '/home/adare/.miniforge3/bin/conda run -n pyadare pip install --force-reinstall /adare/app/wheels/*.whl && xhost +SI:localuser:root'
        else:
            # Editable install from mounted source
            return 'cd /adare/app/adarelib && /home/adare/.miniforge3/bin/conda run -n pyadare pip install . && cd /adare/app/adarevm && /home/adare/.miniforge3/bin/conda run -n pyadare pip install . && xhost +SI:localuser:root'

    def _build_poetry_install_command(self) -> str:
        """Build Poetry installation command."""
        if self.wheels_available:
            # Wheel install + X11 permission
            return 'pip install --force-reinstall /adare/app/wheels/*.whl && xhost +SI:localuser:root'
        else:
            # Editable install via Poetry
            return 'cd /adare/app/adarevm && poetry install && xhost +SI:localuser:root'

    def build_run_command(self, env_info: EnvironmentInfo) -> tuple[str, Optional[str]]:
        """Build Linux run command."""
        if env_info.use_conda:
            # Conda: run with log file argument
            return ('/home/adare/.miniforge3/bin/conda run -n pyadare adarevm /adare/run/logs/adarevm.log', None)
        else:
            # Poetry: run from source directory with log file
            return ('poetry run adarevm /adare/run/logs/adarevm.log', '/adare/app/adarevm')


# Environment Detection Helpers

async def detect_environment(vm, platform: str, stop_event: threading.Event) -> EnvironmentInfo:
    """Detect which Python environment is available in the VM."""
    if platform == 'windows':
        return await _detect_windows_environment(vm, stop_event)
    else:
        return await _detect_linux_environment(vm, stop_event)


async def _detect_windows_environment(vm, stop_event: threading.Event) -> EnvironmentInfo:
    """Detect Windows Python environment."""
    # Check for Miniforge installation
    check_miniforge = r'if (Test-Path "$env:USERPROFILE\.miniforge3") { exit 0 } else { exit 1 }'
    miniforge_result = await vm.run_command(check_miniforge, stop_event=stop_event)

    if miniforge_result.returncode == 0:
        # Check for pyadare conda environment
        check_conda_env = r'& "$env:USERPROFILE\.miniforge3\Scripts\conda.exe" env list | Select-String "^pyadare " | Out-Null; if ($?) { Write-Output "env_exists" } else { Write-Output "env_not_found" }'
        conda_env_result = await vm.run_command(check_conda_env, stop_event=stop_event)

        if 'env_exists' in conda_env_result.stdout:
            log.info(f"Using Miniforge conda environment 'pyadare' for VM '{vm.vm_name}'")
            return EnvironmentInfo(
                use_conda=True,
                conda_env_exists=True,
                miniforge_path=r'%USERPROFILE%\.miniforge3',
                platform='windows'
            )
        else:
            log.warning(f"Miniforge found but 'pyadare' environment does not exist for VM '{vm.vm_name}', falling back to Poetry")

    # Fallback to Poetry
    log.info(f"Using Poetry for VM '{vm.vm_name}'")
    return EnvironmentInfo(
        use_conda=False,
        conda_env_exists=False,
        miniforge_path=None,
        platform='windows'
    )


async def _detect_linux_environment(vm, stop_event: threading.Event) -> EnvironmentInfo:
    """Detect Linux Python environment."""
    # Check for Miniforge installation
    check_miniforge = 'test -d /home/adare/.miniforge3 && echo "exists" || echo "not_found"'
    miniforge_result = await vm.run_command(check_miniforge, stop_event=stop_event)

    if 'exists' in miniforge_result.stdout:
        # Check for pyadare conda environment
        check_conda_env = '/home/adare/.miniforge3/bin/conda env list | grep -q "^pyadare " && echo "env_exists" || echo "env_not_found"'
        conda_env_result = await vm.run_command(check_conda_env, stop_event=stop_event)

        if 'env_exists' in conda_env_result.stdout:
            log.info(f"Using Miniforge conda environment 'pyadare' for VM '{vm.vm_name}'")
            return EnvironmentInfo(
                use_conda=True,
                conda_env_exists=True,
                miniforge_path='/home/adare/.miniforge3',
                platform='linux'
            )
        else:
            log.warning(f"Miniforge found but 'pyadare' environment does not exist for VM '{vm.vm_name}', falling back to Poetry")

    # Fallback to Poetry
    log.info(f"Using Poetry for VM '{vm.vm_name}'")
    return EnvironmentInfo(
        use_conda=False,
        conda_env_exists=False,
        miniforge_path=None,
        platform='linux'
    )

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
from typing import List, Tuple, Optional, Any
import threading

log = logging.getLogger(__name__)


@dataclass
class EnvironmentInfo:
    """Information about the detected Python environment in the VM."""
    use_conda: bool
    conda_env_exists: bool
    miniforge_path: Optional[str]
    platform: str  # 'windows' or 'linux'
    python_exe_path: Optional[str] = None  # Full path to python.exe (Windows non-conda)


@dataclass
class SetupCommand:
    """A setup command with its admin requirement."""
    command: str
    requires_admin: bool


@dataclass
class CommandSet:
    """Collection of commands needed to set up and run adarevm."""
    setup_commands: List[SetupCommand]  # Setup commands with admin flags
    install_command: str
    run_command: str
    run_cwd: Optional[str]
    skip_installation: bool


class AgentCommandBuilder(ABC):
    """Abstract base for building platform-specific agent installation commands."""

    def __init__(self, wheels_dir: Path, shared_folders: dict, websocket_port: int, skip_xhost: bool = False, hypervisor_type: str = 'virtualbox'):
        self.wheels_dir = wheels_dir
        self.shared_folders = shared_folders
        self.websocket_port = websocket_port
        self.skip_xhost = skip_xhost
        self.hypervisor_type = hypervisor_type
        self.wheels_available = wheels_dir.exists() and bool(list(wheels_dir.glob('*.whl')))

    @abstractmethod
    async def build_setup_commands(self, env_info: EnvironmentInfo) -> List[SetupCommand]:
        """Build platform-specific setup commands with admin requirements."""
        pass

    @abstractmethod
    def build_install_command(self, env_info: EnvironmentInfo, vm: Any = None) -> str:
        """Build installation command string."""
        pass

    @abstractmethod
    def build_run_command(self, env_info: EnvironmentInfo, vm: Any = None) -> Tuple[str, Optional[str]]:
        """Build run command and optional cwd. Returns (command, cwd)."""
        pass

    async def build_commands(self, env_info: EnvironmentInfo, vm, stop_event: threading.Event) -> CommandSet:
        """Main entry point: build complete command set."""
        setup_commands = await self.build_setup_commands(env_info)
        install_command = self.build_install_command(env_info, vm)
        run_command, run_cwd = self.build_run_command(env_info, vm)

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

    async def build_setup_commands(self, env_info: EnvironmentInfo) -> List[SetupCommand]:
        """Build Windows setup commands with per-command admin requirements."""
        commands = []

        # Firewall rule for adarevm WebSocket server (REQUIRES ADMIN)
        # Use single quotes to avoid conflict with outer double quotes in commands.py wrapper
        firewall_cmd = f"New-NetFirewallRule -DisplayName 'adarevm' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {self.websocket_port}"
        commands.append(SetupCommand(command=firewall_cmd, requires_admin=True))

        # PATH setup for project-wide tools (User-level, no admin needed)
        # Use single quotes and string concatenation to avoid double quotes (which conflict with commands.py wrapper)
        commands.append(SetupCommand(
            command=r"[Environment]::SetEnvironmentVariable('Path', $env:Path + ';C:\adare\shared\tools', 'User')",
            requires_admin=False
        ))

        # PATH setup for experiment-specific tools (User-level, no admin needed)
        commands.append(SetupCommand(
            command=r"[Environment]::SetEnvironmentVariable('Path', $env:Path + ';C:\adare\experiment\shared\tools', 'User')",
            requires_admin=False
        ))

        # Mount VirtualBox shared folders temporarily (no admin needed)
        # Skip for QEMU - uses file transfer instead of shared folders
        if self.hypervisor_type == 'virtualbox':
            commands.append(SetupCommand(
                command=r'net use Z: \\vboxsvr\adare; net use Z: /delete',
                requires_admin=False
            ))

        return commands

    def build_install_command(self, env_info: EnvironmentInfo, vm: Any = None) -> str:
        """Build Windows installation command."""
        if env_info.use_conda and env_info.conda_env_exists:
            return self._build_conda_install_command()
        else:
            return self._build_poetry_install_command(env_info, vm)
            
    def _resolve_python_path(self, vm: Any) -> str:
        """Resolve absolute path to python executable from discovered guest PATH."""
        default_python = "python" # Fallback to python as requested by user
        
        if not vm or not hasattr(vm, '_cached_guest_path') or not vm._cached_guest_path:
            return default_python
            
        # Parse PATH entries
        path_entries = vm._cached_guest_path.split(';')
        
        # Look for Python entry (prefer user installation)
        # Typical pattern: ...\AppData\Local\Programs\Python\Python312\
        for entry in path_entries:
            if 'Programs\\Python\\Python' in entry and 'Scripts' not in entry:
                # Found python root dir
                python_exe = f"{entry.rstrip('\\')}\\python.exe"
                return f'& "{python_exe}"'
                
        return default_python

    def _build_conda_install_command(self) -> str:
        """Build Conda installation command."""
        # Use different paths for QEMU (file transfer) vs VirtualBox (shared folders)
        if self.hypervisor_type == 'qemu':
            wheels_path = r'C:\adare\vm\wheels\*.whl'
            adarelib_path = r'C:\adare\vm\adarelib'
            adarevm_path = r'C:\adare\vm\adarevm'
        else:
            wheels_path = r'\\vboxsvr\adare\wheels\*.whl'
            adarelib_path = r'\\vboxsvr\adare\adarelib'
            adarevm_path = r'\\vboxsvr\adare\adarevm'

        if self.wheels_available:
            # PowerShell array expansion: @(Get-ChildItem ...) forces wildcard expansion
            # before pip sees the arguments. PowerShell doesn't expand wildcards in
            # base64-encoded commands, so we must explicitly use Get-ChildItem.
            return rf'%USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install --ignore-installed @(Get-ChildItem {wheels_path} | Select-Object -ExpandProperty FullName)'
        else:
            # Editable install from shared folder source
            return rf'cd {adarelib_path}; %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install .; cd {adarevm_path}; %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare pip install .'

    def _build_poetry_install_command(self, env_info: EnvironmentInfo, vm: Any = None) -> str:
        """Build pip installation command (pip is in PATH via user's PATH discovery)."""
        # Use different paths for QEMU (file transfer) vs VirtualBox (shared folders)
        if self.hypervisor_type == 'qemu':
            wheels_path = r'C:\adare\vm\wheels\*.whl'
            adarevm_path = r'C:\adare\vm\adarevm'
        else:
            wheels_path = r'\\vboxsvr\adare\wheels\*.whl'
            adarevm_path = r'\\vboxsvr\adare\adarevm'

        if self.wheels_available:
            # Resolve absolute path to python to avoid PATH issues
            python_cmd = self._resolve_python_path(vm)
            log.info(f"Using executed python command: {python_cmd}")
            
            return rf'{python_cmd} -m pip install --ignore-installed @(Get-ChildItem {wheels_path} | Select-Object -ExpandProperty FullName)'
        else:
            # Editable install via Poetry
            return rf'cd {adarevm_path}; poetry install'

    def build_run_command(self, env_info: EnvironmentInfo, vm: Any = None) -> tuple[str, Optional[str]]:
        """Build Windows run command."""
        # Use different paths for QEMU (file transfer) vs VirtualBox (shared folders)
        if self.hypervisor_type == 'qemu':
            adarevm_path = r'C:\adare\vm\adarevm'
        else:
            adarevm_path = r'\\vboxsvr\adare\adarevm'
            
        # Log path is standard across all Windows environments
        log_path = r'C:\adare\run\logs\adarevm.log'

        if env_info.use_conda:
            if self.wheels_available:
                # Wheel: call directly from conda env (no UNC path navigation)
                return (rf'%USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare adarevm {log_path}', None)
            else:
                # Editable: cd to source directory for Poetry context
                return (rf'cd {adarevm_path}; %USERPROFILE%\.miniforge3\Scripts\conda.exe run -n pyadare adarevm {log_path}', None)
        else:
            if self.wheels_available:
                # Wheel: run via python absolute path (reliable)
                python_cmd = self._resolve_python_path(vm)
                return (rf'adarevm {log_path}', None)
            else:
                # Editable: poetry run from source directory
                return (rf'cd {adarevm_path}; poetry run adarevm {log_path}', None)


class LinuxAgentCommandBuilder(AgentCommandBuilder):
    """Linux-specific command builder."""

    async def build_setup_commands(self, env_info: EnvironmentInfo) -> List[SetupCommand]:
        """Build Linux setup commands with per-command admin requirements."""
        return [
            # Add project-wide tools to PATH (user bashrc, no admin needed)
            SetupCommand(
                command="grep -qxF 'export PATH=$PATH:/adare/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/shared/tools' >> ~/.bashrc; . ~/.bashrc",
                requires_admin=False
            ),
            # Add experiment-specific tools to PATH (user bashrc, no admin needed)
            SetupCommand(
                command="grep -qxF 'export PATH=$PATH:/adare/experiment/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/experiment/shared/tools' >> ~/.bashrc; . ~/.bashrc",
                requires_admin=False
            )
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
            # Wheel install + X11 permission for GUI automation (if needed)
            cmd = '/home/adare/.miniforge3/bin/conda run -n pyadare pip install --ignore-installed /adare/vm/wheels/*.whl'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd
        else:
            # Editable install from mounted source
            cmd = 'cd /adare/vm/adarelib && /home/adare/.miniforge3/bin/conda run -n pyadare pip install . && cd /adare/vm/adarevm && /home/adare/.miniforge3/bin/conda run -n pyadare pip install .'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd

    def _build_poetry_install_command(self) -> str:
        """Build Poetry installation command."""
        if self.wheels_available:
            # Use find for reliable wheel discovery (works with QEMU guest agent)
            # --no-cache-dir avoids cache permission issues
            cmd = 'find /adare/vm/wheels -name "*.whl" -exec pip3 install --break-system-packages --no-cache-dir --ignore-installed {} +'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd
        else:
            # Editable install via Poetry
            cmd = 'cd /adare/vm/adarevm && poetry install'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd

    def build_run_command(self, env_info: EnvironmentInfo) -> tuple[str, Optional[str]]:
        """Build Linux run command."""
        if env_info.use_conda:
            # Conda: wrapper handles both wheels and editable
            return ('/home/adare/.miniforge3/bin/conda run -n pyadare adarevm /adare/run/logs/adarevm.log', None)
        else:
            # Non-conda: check installation method
            if self.wheels_available:
                # Wheels: installed in PATH via pip3, run directly
                return ('adarevm /adare/run/logs/adarevm.log', None)
            else:
                # Editable: poetry run from source directory
                return ('poetry run adarevm /adare/run/logs/adarevm.log', '/adare/vm/adarevm')


# Environment Detection Helpers

def _extract_python_path_from_cached_path(cached_path: Optional[str]) -> Optional[str]:
    """Extract Python executable path from cached guest PATH.

    Parses PATH entries to find Python installation directory
    (e.g., C:\\Users\\adare\\AppData\\Local\\Programs\\Python\\Python312\\)
    and returns the full path to python.exe.

    Args:
        cached_path: The cached PATH string from VM discovery

    Returns:
        Full path to python.exe if found, None otherwise
    """
    if not cached_path:
        return None

    import re
    # Split PATH by semicolon and look for Python directory (not Scripts)
    for entry in cached_path.split(';'):
        entry = entry.strip().rstrip('\\')
        # Match patterns like: ...Python\Python312 or ...Python312 (not Scripts)
        if re.search(r'Python\d+$', entry, re.IGNORECASE):
            python_exe = f"{entry}\\python.exe"
            return python_exe

    return None


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
            log.warning(f"Miniforge found but 'pyadare' environment does not exist for VM '{vm.vm_name}', falling back to system Python")

    # Fallback to system Python (non-conda) - pip/py must be in PATH
    # No pre-check needed - if pip isn't available, install will fail with clear error
    log.info(f"Using system Python (non-conda) for VM '{vm.vm_name}'")
    return EnvironmentInfo(
        use_conda=False,
        conda_env_exists=False,
        miniforge_path=None,
        platform='windows',
        python_exe_path=None  # Not needed - pip/py are in PATH
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
            log.warning(f"Miniforge found but 'pyadare' environment does not exist for VM '{vm.vm_name}', falling back to system Python")

    # Fallback to system Python (non-conda)
    log.info(f"Using system Python (non-conda) for VM '{vm.vm_name}'")
    return EnvironmentInfo(
        use_conda=False,
        conda_env_exists=False,
        miniforge_path=None,
        platform='linux'
    )

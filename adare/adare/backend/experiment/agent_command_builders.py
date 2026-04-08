"""
Command builders for installing and running adarevm agent in VMs.

This module provides a clean separation of concerns for building platform-specific
commands to install and run the adarevm agent. It uses the Builder pattern to
handle the complexity of different execution paths:
- Windows/Linux × Conda/Poetry × Wheels/Editable × virtio-fs/libguestfs

For QEMU hypervisor:
- virtio-fs mode (default): Windows uses Z:\\ paths, Linux uses /adare
- libguestfs mode (fallback): Both platforms use /adare or C:\\adare paths
"""

# external imports
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional, Any
import threading
import json

log = logging.getLogger(__name__)


def _use_shared_folder_mode() -> bool:
    """Check if shared folder mode (virtio-fs) is actually available.

    Must match the logic in file_transfer/__init__.py:detect_file_transfer_mode().
    """
    import shutil
    libguestfs_env = os.environ.get('QEMU_LIBGUESTFS', '').lower()
    if libguestfs_env in ('true', '1', 'yes'):
        return False
    return bool(shutil.which('virtiofsd'))


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

    def __init__(
        self,
        wheels_dir: Path,
        shared_folders: dict,
        websocket_port: int,
        skip_xhost: bool = False,
        hypervisor_type: str = 'virtualbox',
        installation_mode: str = "wheel"
    ):
        self.wheels_dir = wheels_dir
        self.shared_folders = shared_folders
        self.websocket_port = websocket_port
        self.skip_xhost = skip_xhost
        self.hypervisor_type = hypervisor_type
        self.installation_mode = installation_mode
        self.wheels_available = wheels_dir.exists() and bool(list(wheels_dir.glob('*.whl')))

    @abstractmethod
    async def build_setup_commands(self, env_info: EnvironmentInfo, vm: Any = None) -> List[SetupCommand]:
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
        
    def _build_config_file_payload(self) -> str:
        """Build JSON content for config.json.

        Path selection for QEMU:
        - virtio-fs mode (default): Windows uses Z:\\ (virtio-fs mount point)
        - libguestfs mode: Windows uses C:\\adare (files copied to disk)
        - VirtualBox: Uses C:\\adare (shared folder mount point)
        - Linux: Always uses /adare
        """
        if isinstance(self, WindowsAgentCommandBuilder):
            # QEMU: Always uses C:\adare (mounted via virtiofs.exe or copied via guestfish)
            if self.hypervisor_type == 'qemu':
                project_tools = r'C:/adare/project_shared/tools'
                experiment_tools = r'C:/adare/shared/tools'
                project_data = r'C:/adare/project_shared/data'
                experiment_data = r'C:/adare/shared/data'
                log_path = r'C:/adare/run/logs/adarevm.log'
            else:
                # VirtualBox - use C:\adare (via Z: mount) or similar logic if needed, 
                # but for simplicity we keep it consistent where possible.
                # Note: VirtualBox usually mounts to Z: then we might want C:\adare mapped?
                # Actually legacy logic for VBox used C:\adare as well in config.
                project_tools = r'C:/adare/project_shared/tools'
                experiment_tools = r'C:/adare/shared/tools'
                project_data = r'C:/adare/project_shared/data'
                experiment_data = r'C:/adare/shared/data'
                log_path = r'C:/adare/run/logs/adarevm.log'
        else:
            # Linux always uses /adare
            project_tools = '/adare/project_shared/tools'
            experiment_tools = '/adare/shared/tools'
            project_data = '/adare/project_shared/data'
            experiment_data = '/adare/shared/data'
            log_path = '/adare/run/logs/adarevm.log'

        config = {
            "tools_paths": [project_tools, experiment_tools],
            "data_paths": [project_data, experiment_data],
            "logfile": log_path,
            "installation_mode": self.installation_mode
        }
        return json.dumps(config)

    async def build_commands(self, env_info: EnvironmentInfo, vm, stop_event: threading.Event) -> CommandSet:
        """Main entry point: build complete command set."""
        setup_commands = await self.build_setup_commands(env_info, vm)
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

    async def build_setup_commands(self, env_info: EnvironmentInfo, vm: Any = None) -> List[SetupCommand]:
        """Build Windows setup commands with per-command admin requirements."""
        commands = []
        base_path = r'C:\adare'

        # Firewall rule for adarevm WebSocket server (REQUIRES ADMIN)
        # Use single quotes to avoid conflict with outer double quotes in commands.py wrapper
        # Always open guest port 18765 (adarevm default). Port forwarding maps host:websocket_port → guest:18765.
        # Remove stale rules first to prevent accumulation from previous runs.
        firewall_cmd = (
            "Remove-NetFirewallRule -DisplayName 'adarevm' -ErrorAction SilentlyContinue; "
            "New-NetFirewallRule -DisplayName 'adarevm' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 18765"
        )
        commands.append(SetupCommand(command=firewall_cmd, requires_admin=True))

        # PATH setup for project-wide tools (User-level, no admin needed)
        # Use single quotes and string concatenation to avoid double quotes (which conflict with commands.py wrapper)
        # commands.append(SetupCommand(
        #     command=f"[Environment]::SetEnvironmentVariable('Path', $env:Path + ';{base_path}\\project_shared\\tools', 'User')",
        #     requires_admin=False
        # ))

        # PATH setup for experiment-specific tools (User-level, no admin needed)
        # commands.append(SetupCommand(
        #     command=f"[Environment]::SetEnvironmentVariable('Path', $env:Path + ';{base_path}\\shared\\tools', 'User')",
        #     requires_admin=False
        # ))



        # Mount VirtualBox shared folders temporarily (no admin needed)
        # Note: QEMU virtio-fs mounting is handled in lifecycle.py:_mount_virtiofs_windows()
        if self.hypervisor_type == 'virtualbox':
            commands.append(SetupCommand(
                command=r'net use Z: \\vboxsvr\adare; net use Z: /delete',
                requires_admin=False
            ))

        # Write config.json to run directory (User-level, no admin needed)
        # SKIP for QEMU virtio-fs mode: Host already writes this file to the shared directory
        # We only need to write it for VirtualBox or QEMU libguestfs mode
        if not (self.hypervisor_type == 'qemu' and _use_shared_folder_mode()):
            # We use a single-quoted string for content to avoid shell expansion issues
            # JSON content itself uses double quotes
            config_content = self._build_config_file_payload()
            # Escape single quotes in JSON (though json.dumps usually doesn't produce them)
            config_content_safe = config_content.replace("'", "''")

            # Ensure directory exists and write file
            # Using PowerShell to write file with UTF8 encoding
            commands.append(SetupCommand(
                command=f"New-Item -ItemType Directory -Force -Path '{base_path}\\run' | Out-Null; Set-Content -Path '{base_path}\\run\\config.json' -Value '{config_content_safe}' -Encoding UTF8",
                requires_admin=False
            ))

        return commands

    def build_install_command(self, env_info: EnvironmentInfo, vm: Any = None) -> str:
        """Build Windows installation command."""
        if env_info.use_conda and env_info.conda_env_exists:
            return self._build_conda_install_command()
        else:
            return self._build_uv_install_command(env_info, vm)
            
    def _resolve_python_path(self, vm: Any) -> str:
        """Resolve absolute path to python executable from discovered guest PATH.

        Matches both user-install paths (AppData\\Local\\Programs\\Python\\Python311)
        and all-users install paths (C:\\Program Files\\Python311).
        """
        import re
        default_python = "python" # Fallback to python as requested by user

        if not vm or not hasattr(vm, '_cached_guest_path') or not vm._cached_guest_path:
            log.warning("Python not found in guest PATH — falling back to bare 'python'. On ARM64 VMs this likely means Python installation failed; recreate the VM to use the updated template.")
            return default_python

        # Parse PATH entries
        path_entries = vm._cached_guest_path.split(';')

        # Look for Python root directory entry
        # Matches: ...\Programs\Python\Python311, C:\Program Files\Python311, etc.
        for entry in path_entries:
            entry_clean = entry.strip().rstrip('\\')
            if re.search(r'Python3\d+$', entry_clean, re.IGNORECASE) and 'Scripts' not in entry_clean:
                python_exe = f"{entry_clean}\\python.exe"
                return f'& "{python_exe}"'

        return default_python

    def _resolve_adarevm_path(self, vm: Any) -> str:
        """Resolve absolute path to adarevm executable from discovered guest PATH.

        Matches both user-install paths (AppData\\Local\\Programs\\Python\\Python311\\Scripts)
        and all-users install paths (C:\\Program Files\\Python311\\Scripts).
        """
        import re
        default_adarevm = "adarevm" # Fallback

        if not vm or not hasattr(vm, '_cached_guest_path') or not vm._cached_guest_path:
            return default_adarevm

        # Parse PATH entries
        path_entries = vm._cached_guest_path.split(';')

        # Look for Python Scripts entry
        # Matches: ...\Python311\Scripts, C:\Program Files\Python311\Scripts, etc.
        for entry in path_entries:
            entry_clean = entry.strip().rstrip('\\')
            if re.search(r'Python3\d+', entry_clean, re.IGNORECASE) and 'Scripts' in entry_clean:
                adarevm_exe = f"{entry_clean}\\adarevm.exe"
                return f'& "{adarevm_exe}"'

        # Fallback: derive Scripts from Python root
        for entry in path_entries:
            entry_clean = entry.strip().rstrip('\\')
            if re.search(r'Python3\d+$', entry_clean, re.IGNORECASE) and 'Scripts' not in entry_clean:
                adarevm_exe = f"{entry_clean}\\Scripts\\adarevm.exe"
                return f'& "{adarevm_exe}"'

        return default_adarevm

    def _build_conda_install_command(self) -> str:
        """Build Conda installation command."""
        # Use different paths based on hypervisor and mode:
        # - QEMU (both modes): C:\adare\vm\wheels
        # - VirtualBox: \\vboxsvr\adare\wheels
        if self.hypervisor_type == 'qemu':
            # Unified path for QEMU (virtiofs mounts to C:\adare, libguestfs copies to C:\adare)
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
            return rf'C:\Users\adare\.miniforge3\Scripts\conda.exe run -n pyadare pip install --force-reinstall @(Get-ChildItem {wheels_path} | Select-Object -ExpandProperty FullName)'
        else:
            # Editable install from shared folder source
            return rf'cd {adarelib_path}; C:\Users\adare\.miniforge3\Scripts\conda.exe run -n pyadare pip install .; cd {adarevm_path}; C:\Users\adare\.miniforge3\Scripts\conda.exe run -n pyadare pip install .'

    def _build_uv_install_command(self, env_info: EnvironmentInfo, vm: Any = None) -> str:
        """Build pip installation command (pip is in PATH via user's PATH discovery)."""
        # Use different paths based on hypervisor and mode
        if self.hypervisor_type == 'qemu':
            # Unified path for QEMU (virtiofs mounts to C:\adare, libguestfs copies to C:\adare)
            wheels_path = r'C:\adare\vm\wheels\*.whl'
            adarevm_path = r'C:\adare\vm\adarevm'
        else:
            wheels_path = r'\\vboxsvr\adare\wheels\*.whl'
            adarevm_path = r'\\vboxsvr\adare\adarevm'

        if self.wheels_available:
            # Resolve absolute path to python to avoid PATH issues
            python_cmd = self._resolve_python_path(vm)
            log.info(f"Using executed python command: {python_cmd}")

            return rf'{python_cmd} -m pip install --force-reinstall @(Get-ChildItem {wheels_path} | Select-Object -ExpandProperty FullName)'
        else:
            # Editable install via uv
            return rf'cd {adarevm_path}; uv sync'

    def build_run_command(self, env_info: EnvironmentInfo, vm: Any = None) -> tuple[str, Optional[str]]:
        """Build Windows run command."""
        base_path = r'C:\adare'
        
        # Determine base path based on hypervisor and mode
        # QEMU always uses C:\adare (virtiofs mounts there, or files copied there)
        # Tools/data paths use the base path
        project_tools = f'{base_path}\\project_shared\\tools'
        experiment_tools = f'{base_path}\\shared\\tools'
        project_data = f'{base_path}\\project_shared\\data'
        experiment_data = f'{base_path}\\shared\\data'

        # adarevm source path differs between hypervisors
        if self.hypervisor_type == 'qemu':
             # Unified path for QEMU
            adarevm_path = r'C:\adare\vm\adarevm'
        else:
            # VirtualBox uses UNC path for source code access
            adarevm_path = r'\\vboxsvr\adare\adarevm'

        # Pass tools_paths as CLI args so adarevm has them even if config.json
        # can't be read (e.g. SMB junction not ready at startup)
        cli_args = f'--tools-path "{project_tools}" --tools-path "{experiment_tools}"'

        if env_info.use_conda:
            conda_exe = rf'{env_info.miniforge_path}\Scripts\conda.exe'
            if self.wheels_available:
                # Wheel: call directly from conda env (no UNC path navigation)
                return (rf'{conda_exe} run -n pyadare adarevm {cli_args}', None)
            else:
                # Editable: cd to source directory for uv context
                return (rf'cd {adarevm_path}; {conda_exe} run -n pyadare adarevm {cli_args}', None)
        else:
            if self.wheels_available:
                # Wheel: run via python absolute path (reliable)
                # python_cmd = self._resolve_python_path(vm) # Using resolved path
                # Just use 'adarevm' if in path, or python -m adarevm
                return (rf'adarevm {cli_args}', None)
            else:
                # Editable: uv run from source directory
                return (rf'cd {adarevm_path}; uv run adarevm {cli_args}', None)


class LinuxAgentCommandBuilder(AgentCommandBuilder):
    """Linux-specific command builder."""

    async def build_setup_commands(self, env_info: EnvironmentInfo, vm: Any = None) -> List[SetupCommand]:
        """Build Linux setup commands with per-command admin requirements."""
        commands = [
            # Add project-wide tools to PATH (user bashrc, no admin needed)
            SetupCommand(
                command="grep -qxF 'export PATH=$PATH:/adare/project_shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/project_shared/tools' >> ~/.bashrc; . ~/.bashrc",
                requires_admin=False
            ),
            # Add experiment-specific tools to PATH (user bashrc, no admin needed)
            SetupCommand(
                command="grep -qxF 'export PATH=$PATH:/adare/shared/tools' ~/.bashrc || echo 'export PATH=$PATH:/adare/shared/tools' >> ~/.bashrc; . ~/.bashrc",
                requires_admin=False
            ),
            # Add ~/.local/bin to PATH for installations (user bashrc, no admin needed)
            SetupCommand(
                command="grep -qxF 'export PATH=\"$HOME/.local/bin:$PATH\"' ~/.bashrc || echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc; . ~/.bashrc",
                requires_admin=False
            )
        ]

        # Write config.json to run directory
        # SKIP for QEMU virtio-fs mode: Host already writes this file to the shared directory
        if not (self.hypervisor_type == 'qemu' and _use_shared_folder_mode()):
            commands.append(SetupCommand(
                command=f"mkdir -p /adare/run && echo '{self._build_config_file_payload()}' > /adare/run/config.json",
                requires_admin=False
            ))
            
        return commands

    def build_install_command(self, env_info: EnvironmentInfo, vm: Any = None) -> str:
        """Build Linux install command."""
        if env_info.use_conda:
            return self._build_conda_install_command()
        else:
            return self._build_uv_install_command()

    def _build_conda_install_command(self) -> str:
        """Build Conda installation command."""
        if self.wheels_available:
            # Wheel install + X11 permission for GUI automation (if needed)
            cmd = '/home/adare/.miniforge3/bin/conda run -n pyadare pip install --force-reinstall /adare/vm/wheels/*.whl'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd
        else:
            # Editable install from mounted source
            cmd = 'cd /adare/vm/adarelib && /home/adare/.miniforge3/bin/conda run -n pyadare pip install . && cd /adare/vm/adarevm && /home/adare/.miniforge3/bin/conda run -n pyadare pip install .'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd

    def _build_uv_install_command(self) -> str:
        """Build uv installation command."""
        if self.wheels_available:
            # Use find for reliable wheel discovery (works with QEMU guest agent)
            # --no-cache-dir avoids cache permission issues
            cmd = 'find /adare/vm/wheels -name "*.whl" -exec pip3 install --no-cache-dir --force-reinstall {} +'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd
        else:
            # Editable install via uv
            cmd = 'cd /adare/vm/adarevm && uv sync'
            if not self.skip_xhost:
                cmd += ' && xhost +SI:localuser:root'
            return cmd

    def build_run_command(self, env_info: EnvironmentInfo, vm: Any = None) -> tuple[str, Optional[str]]:
        """Build Linux run command."""
        # Minimal CLI args - relying on default /adare/run and config.json
        cli_args = ""

        if env_info.use_conda:
            # Conda: wrapper handles both wheels and editable
            return (f'/home/adare/.miniforge3/bin/conda run -n pyadare adarevm {cli_args}', None)
        else:
            # Non-conda: check installation method
            if self.wheels_available:
                # Wheels: installed in PATH via pip3, run directly
                return (f'adarevm {cli_args}', None)
            else:
                # Editable: uv run from source directory
                return (f'uv run adarevm {cli_args}', '/adare/vm/adarevm')


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
    # Use explicit user home path — $env:USERPROFILE resolves to SYSTEM's profile
    # when commands run via QEMU Guest Agent (NT AUTHORITY\SYSTEM context)
    user_home = rf'C:\Users\{vm.username}'
    miniforge_path = rf'{user_home}\.miniforge3'
    check_miniforge = rf'if (Test-Path "{miniforge_path}") {{ exit 0 }} else {{ exit 1 }}'
    miniforge_result = await vm.run_command(check_miniforge, stop_event=stop_event)

    if miniforge_result.returncode == 0:
        # Check for pyadare conda environment
        check_conda_env = rf'& "{miniforge_path}\Scripts\conda.exe" env list | Select-String "^pyadare " | Out-Null; if ($?) {{ Write-Output "env_exists" }} else {{ Write-Output "env_not_found" }}'
        conda_env_result = await vm.run_command(check_conda_env, stop_event=stop_event)

        if 'env_exists' in conda_env_result.stdout:
            log.info(f"Using Miniforge conda environment 'pyadare' for VM '{vm.vm_name}'")
            return EnvironmentInfo(
                use_conda=True,
                conda_env_exists=True,
                miniforge_path=miniforge_path,
                platform='windows'
            )
        else:
            # Attempt to create pyadare env as recovery
            python_version = '3.11' if getattr(vm, 'architecture', None) == 'aarch64' else '3.10'
            log.warning(
                f"Miniforge found but 'pyadare' environment missing for VM '{vm.vm_name}'. "
                f"Attempting to create it with Python {python_version}..."
            )
            create_env_cmd = rf'& "{miniforge_path}\Scripts\conda.exe" create -n pyadare python={python_version} -y'
            create_result = await vm.run_command(create_env_cmd, stop_event=stop_event, timeout=300)

            if create_result.returncode == 0:
                log.info(f"Successfully created 'pyadare' conda environment for VM '{vm.vm_name}'")
                return EnvironmentInfo(
                    use_conda=True,
                    conda_env_exists=True,
                    miniforge_path=miniforge_path,
                    platform='windows'
                )
            else:
                log.error(
                    f"Failed to create 'pyadare' conda environment for VM '{vm.vm_name}': "
                    f"{create_result.stderr}"
                )

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

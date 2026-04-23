"""
Guest Command Proxy for Host-Mode Test Execution.

Wraps vm.run_command() (QGA guest-exec) with convenience methods for
common system-state queries used by testfunctions.
"""

import contextlib
import logging

from adare.hypervisor.base.models import CommandResult

from .vm_operation_proxy import VMOperationProxy

log = logging.getLogger(__name__)


class GuestCommandProxy(VMOperationProxy):
    """
    Proxy for executing commands on guest VM via QGA guest-exec.

    Provides both raw command execution and convenience methods for
    common system-state queries (process checking, service status, etc.)
    that system-state testfunctions need.
    """

    def __init__(self, vm, guest_os: str):
        """
        Initialize guest command proxy.

        Args:
            vm: QEMU VM instance with run_command() support
            guest_os: Guest OS identifier (e.g. 'linux', 'windows')
        """
        super().__init__(vm, guest_os)

    async def run(self, command: str, silent: bool = False, admin: bool = False,
                  cwd: str | None = None) -> CommandResult:
        """Execute a command on the guest via QGA.

        Args:
            command: Command string to execute
            silent: Suppress log output
            admin: Run with elevated privileges
            cwd: Working directory for command

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        return await self.vm.run_command(
            command,
            silent=silent,
            admin=admin,
            cwd=cwd
        )

    async def is_process_running(self, process_name: str) -> bool:
        """Check if a process is running on the guest.

        Args:
            process_name: Process name to search for

        Returns:
            True if at least one matching process is found
        """
        if self.is_windows:
            cmd = f'Get-Process -Name "{process_name}" -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count'
            result = await self.run(cmd, silent=True)
            try:
                return int(result.stdout.strip()) > 0
            except ValueError:
                return False
        else:
            cmd = f"pgrep -x '{process_name}' > /dev/null 2>&1 && echo RUNNING || echo STOPPED"
            result = await self.run(cmd, silent=True)
            return 'RUNNING' in result.stdout

    async def get_service_status(self, service_name: str) -> str:
        """Get the status of a system service on the guest.

        Args:
            service_name: Name of the service

        Returns:
            Service status string (e.g. 'active', 'inactive', 'running', 'stopped')
        """
        if self.is_windows:
            cmd = f'(Get-Service -Name "{service_name}" -ErrorAction SilentlyContinue).Status'
            result = await self.run(cmd, silent=True)
            return result.stdout.strip().lower() if result.returncode == 0 else 'unknown'
        cmd = f"systemctl is-active '{service_name}' 2>/dev/null || echo unknown"
        result = await self.run(cmd, silent=True)
        return result.stdout.strip()

    async def user_exists(self, username: str) -> bool:
        """Check if a user account exists on the guest.

        Args:
            username: Username to check

        Returns:
            True if user exists
        """
        if self.is_windows:
            cmd = (
                f'if (Get-LocalUser -Name "{username}" -ErrorAction SilentlyContinue) '
                f'{{ echo "EXISTS" }} else {{ echo "MISSING" }}'
            )
        else:
            cmd = f"id '{username}' > /dev/null 2>&1 && echo EXISTS || echo MISSING"

        result = await self.run(cmd, silent=True)
        return 'EXISTS' in result.stdout

    async def get_file_stat(self, guest_path: str) -> dict:
        """Get file stat information from guest.

        Args:
            guest_path: Path to file on guest

        Returns:
            Dict with keys: permissions, owner, group, size, mtime, atime, ctime
        """
        stat_info = {}

        if self.is_windows:
            cmd = (
                f'$f = Get-Item -LiteralPath "{guest_path}" -Force; '
                f'"SIZE:" + $f.Length; '
                f'"MTIME:" + (Get-Date $f.LastWriteTimeUtc -UFormat "%s"); '
                f'"ATIME:" + (Get-Date $f.LastAccessTimeUtc -UFormat "%s"); '
                f'"CTIME:" + (Get-Date $f.CreationTimeUtc -UFormat "%s")'
            )
        else:
            cmd = f"stat -c 'PERM:%a OWNER:%U GROUP:%G SIZE:%s MTIME:%Y ATIME:%X CTIME:%Z' '{guest_path}'"

        result = await self.run(cmd, silent=True)
        if result.returncode != 0:
            log.warning(f"GuestCommandProxy: stat failed for {guest_path}: {result.stderr}")
            return stat_info

        output = result.stdout.strip()
        for part in output.replace('\n', ' ').split():
            if ':' not in part:
                continue
            key, _, value = part.partition(':')
            key = key.lower()
            if key in ('perm', 'permissions'):
                stat_info['permissions'] = value
            elif key == 'owner':
                stat_info['owner'] = value
            elif key == 'group':
                stat_info['group'] = value
            elif key == 'size':
                with contextlib.suppress(ValueError):
                    stat_info['size'] = int(value)
            elif key == 'mtime':
                with contextlib.suppress(ValueError):
                    stat_info['mtime'] = float(value)
            elif key == 'atime':
                with contextlib.suppress(ValueError):
                    stat_info['atime'] = float(value)
            elif key == 'ctime':
                with contextlib.suppress(ValueError):
                    stat_info['ctime'] = float(value)

        return stat_info

    async def search_log_file(self, log_path: str, pattern: str, max_lines: int = 1000) -> tuple[bool, list[str]]:
        """Search a log file for entries matching a regex pattern.

        Args:
            log_path: Path to the log file on the guest
            pattern: Regex pattern to search for
            max_lines: Maximum lines to search from end of file

        Returns:
            Tuple of (found: bool, matching_lines: list[str])
        """
        if self.is_windows:
            cmd = (
                f'Get-Content -Path "{log_path}" -Tail {max_lines} '
                f'| Select-String -Pattern "{pattern}" '
                f'| ForEach-Object {{ $_.Line }}'
            )
        else:
            cmd = f"tail -n {max_lines} '{log_path}' | grep -E '{pattern}'"

        result = await self.run(cmd, silent=True)
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            return True, lines
        return False, []

    async def registry_key_exists(self, key_path: str) -> bool:
        """Check if a Windows registry key exists.

        Args:
            key_path: Full registry path (e.g. 'HKLM\\\\Software\\\\Microsoft')

        Returns:
            True if registry key exists
        """
        ps_path = self._to_powershell_registry_path(key_path)
        cmd = f'if (Test-Path "Registry::{ps_path}") {{ echo "EXISTS" }} else {{ echo "MISSING" }}'
        result = await self.run(cmd, silent=True)
        return 'EXISTS' in result.stdout

    async def registry_value_get(self, key_path: str, value_name: str) -> tuple[bool, str | None, str | None]:
        """Get a Windows registry value.

        Args:
            key_path: Full registry key path
            value_name: Value name within the key

        Returns:
            Tuple of (exists: bool, value: str or None, type_name: str or None)
        """
        ps_path = self._to_powershell_registry_path(key_path)
        cmd = (
            f'try {{ '
            f'$val = Get-ItemProperty -Path "Registry::{ps_path}" -Name "{value_name}" -ErrorAction Stop; '
            f'$raw = $val."{value_name}"; '
            f'$kind = (Get-Item "Registry::{ps_path}").GetValueKind("{value_name}"); '
            f'"VALUE:" + [string]$raw; '
            f'"TYPE:" + [string]$kind '
            f'}} catch {{ echo "NOTFOUND" }}'
        )
        result = await self.run(cmd, silent=True)
        output = result.stdout.strip()

        if 'NOTFOUND' in output:
            return False, None, None

        value = None
        type_name = None
        for line in output.splitlines():
            if line.startswith('VALUE:'):
                value = line[6:]
            elif line.startswith('TYPE:'):
                type_name = line[5:]

        return True, value, type_name

    async def get_file_permissions(self, guest_path: str) -> dict:
        """Get file permission details from guest.

        Args:
            guest_path: Path to file on guest

        Returns:
            Dict with keys: permissions (octal str), owner, group
        """
        if self.is_windows:
            cmd = (
                f'$acl = Get-Acl -LiteralPath "{guest_path}"; '
                f'"OWNER:" + $acl.Owner; '
                f'"GROUP:" + $acl.Group'
            )
        else:
            cmd = f"stat -c 'PERM:%a OWNER:%U GROUP:%G' '{guest_path}'"

        result = await self.run(cmd, silent=True)
        info = {}
        if result.returncode != 0:
            log.warning(f"GuestCommandProxy: get_file_permissions failed for {guest_path}: {result.stderr}")
            return info

        for part in result.stdout.strip().replace('\n', ' ').split():
            if ':' not in part:
                continue
            key, _, value = part.partition(':')
            key = key.upper()
            if key == 'PERM':
                info['permissions'] = value
            elif key == 'OWNER':
                info['owner'] = value
            elif key == 'GROUP':
                info['group'] = value

        return info

    async def get_file_timestamps(self, guest_path: str) -> dict:
        """Get file timestamp information from guest.

        Args:
            guest_path: Path to file on guest

        Returns:
            Dict with keys: mtime, atime, ctime (as float epoch seconds)
        """
        if self.is_windows:
            cmd = (
                f'$f = Get-Item -LiteralPath "{guest_path}" -Force; '
                f'"MTIME:" + (Get-Date $f.LastWriteTimeUtc -UFormat "%s"); '
                f'"ATIME:" + (Get-Date $f.LastAccessTimeUtc -UFormat "%s"); '
                f'"CTIME:" + (Get-Date $f.CreationTimeUtc -UFormat "%s")'
            )
        else:
            cmd = f"stat -c 'MTIME:%Y ATIME:%X CTIME:%Z' '{guest_path}'"

        result = await self.run(cmd, silent=True)
        timestamps = {}
        if result.returncode != 0:
            log.warning(f"GuestCommandProxy: get_file_timestamps failed for {guest_path}: {result.stderr}")
            return timestamps

        for part in result.stdout.strip().replace('\n', ' ').split():
            if ':' not in part:
                continue
            key, _, value = part.partition(':')
            key = key.lower()
            if key in ('mtime', 'atime', 'ctime'):
                with contextlib.suppress(ValueError):
                    timestamps[key] = float(value)

        return timestamps

    @staticmethod
    def _to_powershell_registry_path(key_path: str) -> str:
        """Convert a registry key path to PowerShell-compatible format.

        Handles both short (HKLM) and long (HKEY_LOCAL_MACHINE) hive names.
        """
        normalized = key_path.replace('/', '\\')
        parts = normalized.split('\\', 1)
        if len(parts) < 2:
            return normalized

        hive = parts[0].upper()
        subkey = parts[1]

        hive_mapping = {
            'HKCR': 'HKEY_CLASSES_ROOT',
            'HKCU': 'HKEY_CURRENT_USER',
            'HKLM': 'HKEY_LOCAL_MACHINE',
            'HKU': 'HKEY_USERS',
            'HKCC': 'HKEY_CURRENT_CONFIG',
        }
        full_hive = hive_mapping.get(hive, hive)
        return f'{full_hive}\\{subkey}'

"""
Guest Command Proxy for Host-Mode Test Execution.

Wraps vm.run_command() (QGA guest-exec) with convenience methods for
common system-state queries used by testfunctions.
"""

import contextlib
import json
import logging
import shlex
from dataclasses import dataclass

from adare.hypervisor.base.models import CommandResult
from adare.hypervisor.qemu.guest_clock import GuestClockError, read_guest_time, read_guest_utc_offset

from .guest_file_proxy import is_not_found_error
from .vm_operation_proxy import VMOperationProxy

log = logging.getLogger(__name__)


def _ps_quote(value: str) -> str:
    """PowerShell single-quoted string literal (no expansion; ``'`` is doubled)."""
    return "'" + value.replace("'", "''") + "'"


# .NET RegistryValueKind -> the canonical REG_* names the guest agent reports.
_REGISTRY_KINDS = {
    'string': 'REG_SZ',
    'expandstring': 'REG_EXPAND_SZ',
    'binary': 'REG_BINARY',
    'dword': 'REG_DWORD',
    'multistring': 'REG_MULTI_SZ',
    'qword': 'REG_QWORD',
}


def _typed_registry_value(kind: str, data):
    """JSON ``data`` of a registry value of .NET kind ``kind`` as the Python value ``winreg`` gives."""
    kind = kind.lower()
    if kind == 'binary':
        return bytes(data) if isinstance(data, list) else b''
    if kind == 'multistring':
        return list(data) if isinstance(data, list) else [data]
    if kind in ('dword', 'qword') and isinstance(data, int):
        # .NET reads the data signed; winreg returns it unsigned
        return data & (0xFFFFFFFF if kind == 'dword' else 0xFFFFFFFFFFFFFFFF)
    return data


@dataclass(frozen=True)
class GuestClock:
    """The guest's wall clock: epoch seconds now, and its UTC offset in seconds (``None`` = unknown)."""

    now: float
    utc_offset_seconds: int | None = None


def raise_for_stat_failure(guest_path: str, result: CommandResult) -> None:
    """Raise for a failed ``stat``: ``FileNotFoundError`` when the guest says the path is absent,
    ``RuntimeError`` for anything else (permission denied, I/O error): that says nothing about absence."""
    message = (result.stderr or result.stdout or '').strip()
    if is_not_found_error(message):
        raise FileNotFoundError(f'{guest_path} does not exist on guest: {message}')
    raise RuntimeError(f'cannot examine {guest_path} on guest: {message or f"exit code {result.returncode}"}')


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

    async def run(
        self, command: str, silent: bool = False, admin: bool = False, cwd: str | None = None
    ) -> CommandResult:
        """Execute a command on the guest via QGA.

        Args:
            command: Command string to execute
            silent: Suppress log output
            admin: Run with elevated privileges
            cwd: Working directory for command

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        return await self.vm.run_command(command, silent=silent, admin=admin, cwd=cwd)

    async def list_processes(self, process_name: str) -> list[str]:
        """PIDs of the processes matching ``process_name`` on the guest.

        Linux: ``pgrep -f`` like the guest agent, so the name is an extended regex matched against
        the full command line. The shell running this command carries the pattern in its own command
        line and would match itself, so its PID is left out. Windows: ``Get-Process -Name``.

        Raises:
            RuntimeError: the guest could not run the command
        """
        if self.is_windows:
            quoted = _ps_quote(process_name)
            cmd = f'(Get-Process -Name {quoted} -ErrorAction SilentlyContinue).Id'
            result = await self.run(cmd, silent=True)
            return [line.strip() for line in result.stdout.splitlines() if line.strip().isdigit()]
        cmd = f'echo "SELF:$$"; pgrep -f -- {shlex.quote(process_name)}'
        result = await self.run(cmd, silent=True)
        if result.returncode not in (0, 1):
            # 1 = no match; anything else (2: invalid regex, 3: fatal) is not "not running"
            raise RuntimeError(f'pgrep failed (exit {result.returncode}): {(result.stderr or "").strip()}')
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        own = next((line[5:] for line in lines if line.startswith('SELF:')), None)
        return [line for line in lines if line.isdigit() and line != own]

    async def is_process_running(self, process_name: str) -> bool:
        """True if at least one process matches ``process_name`` (see :meth:`list_processes`)."""
        return bool(await self.list_processes(process_name))

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

    async def get_user_info(self, username: str) -> dict | None:
        """The account ``username`` as ``{'uid': int, 'home': str}``, or ``None`` if there is none.

        Linux: ``getent passwd``, the same user database as ``pwd.getpwnam`` (NSS sources count).
        Windows has no UID/home in ``Get-LocalUser``: ``{}`` when the account exists.

        Raises:
            RuntimeError: the answer could not be read
        """
        if self.is_windows:
            cmd = (
                f'if (Get-LocalUser -Name {_ps_quote(username)} -ErrorAction SilentlyContinue) '
                f'{{ echo "EXISTS" }} else {{ echo "MISSING" }}'
            )
            result = await self.run(cmd, silent=True)
            return {} if 'EXISTS' in result.stdout else None
        result = await self.run(f'getent passwd -- {shlex.quote(username)}', silent=True)
        if result.returncode == 2:  # key not found
            return None
        fields = result.stdout.strip().split(':')
        if result.returncode != 0 or len(fields) < 6 or not fields[2].isdigit():
            raise RuntimeError(f'getent passwd failed (exit {result.returncode}): {(result.stderr or "").strip()}')
        return {'uid': int(fields[2]), 'home': fields[5]}

    async def user_exists(self, username: str) -> bool:
        """True if the account exists on the guest."""
        return await self.get_user_info(username) is not None

    async def get_guest_clock(self) -> GuestClock | None:
        """The guest's clock through QGA, or ``None`` when the guest agent cannot tell."""
        try:
            now = await read_guest_time(self.vm)
        except (GuestClockError, AttributeError, KeyError, ValueError) as e:
            log.warning(f"GuestCommandProxy: guest clock unavailable: {e}")
            return None
        offset = None
        try:
            text = await read_guest_utc_offset(self.vm)
            sign = -1 if text.startswith('-') else 1
            hours, minutes = text[1:].split(':')
            offset = sign * (int(hours) * 3600 + int(minutes) * 60)
        except (GuestClockError, KeyError, ValueError) as e:  # older qemu-ga lacks guest-get-timezone
            log.debug(f"GuestCommandProxy: guest timezone unavailable: {e}")
        return GuestClock(now, offset)

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

    async def registry_value_get(self, key_path: str, value_name: str) -> tuple[bool, object, str | None]:
        """Get a Windows registry value with its Python type, as ``winreg`` would return it.

        The data comes back as JSON (``ConvertTo-Json``) and is typed by the value kind:
        DWORD/QWORD -> ``int``, String/ExpandString -> ``str`` (variables NOT expanded, as
        ``winreg``), Binary -> ``bytes``, MultiString -> ``list[str]``.

        Args:
            key_path: Full registry key path
            value_name: Value name within the key (``''`` is the default value)

        Returns:
            ``(exists, typed value or None, canonical type name or None)``; the type name is
            ``REG_SZ``, ``REG_EXPAND_SZ``, ``REG_BINARY``, ``REG_DWORD``, ``REG_MULTI_SZ``,
            ``REG_QWORD`` (``REG_NONE`` for others)

        Raises:
            RuntimeError: the guest's answer could not be read
        """
        ps_path = self._to_powershell_registry_path(key_path)
        cmd = (
            f'try {{ '
            f'$key = Get-Item -LiteralPath "Registry::{ps_path}" -ErrorAction Stop; '
            f'if ($key.GetValueNames() -notcontains {_ps_quote(value_name)}) {{ echo "NOTFOUND" }} else {{ '
            f'$kind = $key.GetValueKind({_ps_quote(value_name)}); '
            f'$raw = $key.GetValue({_ps_quote(value_name)}, $null, '
            f'[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames); '
            f'"TYPE:" + [string]$kind; '
            f'"VALUE:" + (ConvertTo-Json -Compress -InputObject $raw) }} '
            f'}} catch {{ echo "NOTFOUND" }}'
        )
        result = await self.run(cmd, silent=True)
        output = result.stdout.strip()

        if 'NOTFOUND' in output.splitlines():
            return False, None, None

        kind = None
        encoded = None
        for line in output.splitlines():
            if line.startswith('TYPE:'):
                kind = line[5:].strip()
            elif line.startswith('VALUE:'):
                encoded = line[6:]
        if kind is None or encoded is None:
            raise RuntimeError(f'unreadable registry answer for {key_path}\\{value_name}: {output[:200]!r}')
        try:
            data = json.loads(encoded)
        except ValueError as e:
            raise RuntimeError(f'unreadable registry data for {key_path}\\{value_name}: {e}') from e
        return True, _typed_registry_value(kind, data), _REGISTRY_KINDS.get(kind.lower(), 'REG_NONE')

    async def get_file_permissions(self, guest_path: str) -> dict:
        """Get file permission details from guest.

        Args:
            guest_path: Path to file on guest

        Returns:
            Dict with keys: permissions (octal str), owner, group

        Raises:
            FileNotFoundError: the guest says the path does not exist
            RuntimeError: the path could not be examined for another reason
        """
        if self.is_windows:
            cmd = f'$acl = Get-Acl -LiteralPath "{guest_path}"; "OWNER:" + $acl.Owner; "GROUP:" + $acl.Group'
        else:
            cmd = f"stat -c 'PERM:%a OWNER:%U GROUP:%G' '{guest_path}'"

        result = await self.run(cmd, silent=True)
        info = {}
        if result.returncode != 0:
            log.warning(f"GuestCommandProxy: get_file_permissions failed for {guest_path}: {result.stderr}")
            raise_for_stat_failure(guest_path, result)

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

        Raises:
            FileNotFoundError: the guest says the path does not exist
            RuntimeError: the path could not be examined for another reason
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
            raise_for_stat_failure(guest_path, result)

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

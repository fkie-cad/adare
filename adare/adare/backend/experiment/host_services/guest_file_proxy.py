"""
Guest File Proxy for Host-Mode Test Execution.

Wraps QGAFileTransfer to pull files from guest VM to a local temp directory,
with caching to avoid re-downloading the same file multiple times.
"""

import contextlib
import logging
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .vm_operation_proxy import VMOperationProxy

log = logging.getLogger(__name__)


#: Error texts QGA returns when the path does not exist (Linux errno / Windows Win32 message)
_NOT_FOUND_MARKERS = ('no such file', 'cannot find the file', 'cannot find the path', 'not found', 'does not exist')


def shell_glob_word(pattern: str) -> str:
    """``pattern`` as one POSIX shell word: ``*``, ``?`` and ``[...]`` stay glob characters,
    everything else is quoted (spaces, quotes, ``;``, ``$`` are literal, never shell syntax)."""
    parts: list[str] = []
    literal = ''
    i = 0
    while i < len(pattern):
        char = pattern[i]
        closing = _bracket_end(pattern, i) if char == '[' else -1
        if char in '*?' or closing > 0:
            if literal:
                parts.append(shlex.quote(literal))
                literal = ''
            if char in '*?':
                parts.append(char)
                i += 1
                continue
            body = pattern[i + 1 : closing]
            negate = '!' if body[:1] in ('!', '^') else ''
            body = body[1:] if negate else body
            parts.append(f'[{negate}{shlex.quote(body)}]')
            i = closing + 1
            continue
        literal += char
        i += 1
    if literal:
        parts.append(shlex.quote(literal))
    return ''.join(parts) or "''"


def _bracket_end(pattern: str, start: int) -> int:
    """Index of the ``]`` closing the bracket expression at ``start``, or -1 (a literal ``[``)."""
    i = start + 1
    if i < len(pattern) and pattern[i] in '!^':
        i += 1
    if i < len(pattern) and pattern[i] == ']':  # a leading ] is a member
        i += 1
    return pattern.find(']', i)


def glob_base(pattern: str) -> str:
    """The deepest directory of ``pattern`` before its first glob component (for a plain path: its
    parent); ``''`` when there is none (a relative pattern)."""
    first = next(
        (i for i, c in enumerate(pattern) if c in '*?' or (c == '[' and _bracket_end(pattern, i) > 0)), len(pattern)
    )
    prefix = pattern[:first]
    cut = max(prefix.rfind('/'), prefix.rfind('\\'))
    if cut < 0:
        return ''
    base = prefix[:cut] or prefix[: cut + 1]  # '/x*' -> '/'
    return base + prefix[cut] if base.endswith(':') else base  # 'C:\\*' -> 'C:\\', not 'C:'


#: exit code of a listing whose base directory exists but cannot be read
UNREADABLE_BASE_EXIT = 3


def _posix_base_guard(pattern: str) -> str:
    """Shell prefix that fails (exit 3) when the glob's base directory exists but cannot be listed:
    the shell would expand the glob to nothing, which reads as "no match"."""
    base = glob_base(pattern)
    if not base:
        return ''
    q = shlex.quote(base)
    return (
        f'if [ -d {q} ] && ! {{ [ -r {q} ] && [ -x {q} ]; }}; then '
        f'echo "cannot read directory "{q} >&2; exit {UNREADABLE_BASE_EXIT}; fi; '
    )


#: PowerShell suffix: an access-denied error while listing is a failure, not "no match"
_POWERSHELL_DENIED_EXIT = (
    '; if ($globErr | Where-Object { $_.Exception -is [System.UnauthorizedAccessException] }) '
    f'{{ exit {UNREADABLE_BASE_EXIT} }}'
)


def powershell_literal(text: str) -> str:
    """``text`` as a single-quoted PowerShell string: no variable or subexpression expansion."""
    return "'" + text.replace("'", "''") + "'"


def is_not_found_error(message: str) -> bool:
    """True if a QGA error message says the path does not exist (not a transport failure)."""
    lowered = message.lower()
    return any(marker in lowered for marker in _NOT_FOUND_MARKERS)


@dataclass
class FileMetadata:
    """Metadata collected from guest file via QGA stat."""

    permissions: str | None = None  # e.g. '0644'
    owner: str | None = None
    group: str | None = None
    size: int | None = None
    mtime: float | None = None  # modification time (epoch)
    atime: float | None = None  # access time (epoch)
    ctime: float | None = None  # change time (epoch)


class GuestFileProxy(VMOperationProxy):
    """
    Proxy for guest file operations via QGA.

    Pulls files from the guest VM to a local temp directory, maintaining
    a cache to avoid redundant transfers. Also provides guest-side glob
    resolution and metadata collection.
    """

    def __init__(self, vm, guest_os: str):
        """
        Initialize guest file proxy.

        Args:
            vm: QEMU VM instance with QGA support (run_command, qga_file_transfer)
            guest_os: Guest OS identifier (e.g. 'linux', 'windows')
        """
        super().__init__(vm, guest_os)
        self._temp_root = Path(tempfile.mkdtemp(prefix='adare_host_test_'))
        self._cache: dict[str, Path] = {}  # guest_path → local_path
        self._metadata_cache: dict[str, FileMetadata] = {}
        log.debug(f"GuestFileProxy: temp root at {self._temp_root}")

    def _guest_path_to_local(self, guest_path: str) -> Path:
        """Map a guest path to a local path under the temp root.

        Examples:
            /etc/hosts         → {temp_root}/etc/hosts
            C:\\Users\\file.txt → {temp_root}/C_/Users/file.txt
        """
        if self.is_windows:
            # C:\Users\file.txt → C_/Users/file.txt
            normalized = guest_path.replace('\\', '/')
            if len(normalized) >= 2 and normalized[1] == ':':
                normalized = normalized[0] + '_' + normalized[2:]
        else:
            # /etc/hosts → etc/hosts (strip leading /)
            normalized = guest_path.lstrip('/')

        return self._temp_root / normalized

    async def pull_file(self, guest_path: str, force: bool = False) -> Path:
        """Pull a single file from guest to local temp directory.

        Args:
            guest_path: Absolute path on guest
            force: If True, re-download even if cached

        Returns:
            Path to local copy of the file

        Raises:
            FileNotFoundError: If the guest reports that the file doesn't exist
            RuntimeError: If the download fails for any other reason (transport, permission)
        """
        if not force and guest_path in self._cache:
            log.debug(f"GuestFileProxy: cache hit for {guest_path}")
            return self._cache[guest_path]

        local_path = self._guest_path_to_local(guest_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        from adare.hypervisor.exceptions import HypervisorException

        try:
            from adare.hypervisor.qemu.qga_file_transfer import QGAFileTransfer

            transfer = QGAFileTransfer(self.vm)
            await transfer.download_file(guest_path, local_path)
        except HypervisorException as e:
            # Only a "no such file" answer from the guest means absent; anything else
            # (agent unreachable, timeout, permission) says nothing about the file.
            if is_not_found_error(str(e)):
                raise FileNotFoundError(f"{guest_path} does not exist on guest: {e}") from e
            raise RuntimeError(f"Failed to pull {guest_path} from guest: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to pull {guest_path} from guest: {e}") from e

        if not local_path.exists():
            raise FileNotFoundError(f"Download completed but file not found at {local_path}")

        self._cache[guest_path] = local_path
        log.debug(f"GuestFileProxy: pulled {guest_path} → {local_path} ({local_path.stat().st_size} bytes)")
        return local_path

    async def pull_directory(self, guest_path: str, force: bool = False) -> Path:
        """Pull a directory from guest to local temp directory.

        Args:
            guest_path: Absolute directory path on guest
            force: If True, re-download even if cached

        Returns:
            Path to local copy of the directory
        """
        if not force and guest_path in self._cache:
            log.debug(f"GuestFileProxy: cache hit for directory {guest_path}")
            return self._cache[guest_path]

        local_path = self._guest_path_to_local(guest_path)
        local_path.mkdir(parents=True, exist_ok=True)

        try:
            from adare.hypervisor.qemu.qga_file_transfer import QGAFileTransfer

            transfer = QGAFileTransfer(self.vm)
            await transfer.download_directory(guest_path, local_path)
        except Exception as e:
            raise RuntimeError(f"Failed to pull directory {guest_path} from guest: {e}") from e

        self._cache[guest_path] = local_path
        log.debug(f"GuestFileProxy: pulled directory {guest_path} → {local_path}")
        return local_path

    async def resolve_guest_glob(self, pattern: str) -> list[str]:
        """Resolve a glob/wildcard pattern on the guest side.

        Args:
            pattern: Glob pattern (e.g. '/var/log/*.log' or 'C:\\Users\\*\\Desktop')

        Returns:
            List of matching absolute paths on guest

        Raises:
            RuntimeError: the guest command failed, or the glob's base directory exists but cannot
                be read (an empty list always means "no match"). Only the base directory is
                checked: an unreadable directory *inside* the glob is skipped, as the shell does.
                QGA usually runs as root/SYSTEM, where this does not happen.
        """
        if self.is_windows:
            cmd = (
                f'Get-ChildItem -Path {powershell_literal(pattern)} -ErrorAction SilentlyContinue '
                f'-ErrorVariable globErr | ForEach-Object {{ $_.FullName }}' + _POWERSHELL_DENIED_EXIT
            )
        else:
            # no `ls`: its exit code is the same for "no match" and "cannot read"
            cmd = _posix_base_guard(pattern) + (
                f'for p in {shell_glob_word(pattern)}; do '
                'if [ -e "$p" ] || [ -L "$p" ]; then printf \'%s\\n\' "$p"; fi; done'
            )

        result = await self.vm.run_command(cmd, silent=True)
        if result.returncode != 0:
            raise RuntimeError(f"glob resolution failed for '{pattern}' (exit {result.returncode}): {result.stderr}")

        paths = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        log.debug(f"GuestFileProxy: glob '{pattern}' resolved to {len(paths)} paths")
        return paths

    async def path_kinds(self, pattern: str) -> list[tuple[str, str]]:
        """Existing guest paths matching ``pattern`` (glob or plain path) with their kind.

        Kinds: ``file`` (regular file, also through a symlink), ``dir`` (also through a
        symlink), ``other`` (broken symlink, device, socket, ...). Like
        :meth:`resolve_guest_glob`, a failed command raises instead of looking like no match,
        so a count can never pass on a transport error.

        :raises RuntimeError: the guest command failed
        """
        has_glob = any(c in pattern for c in '*?[')
        if self.is_windows:
            path_arg = '-Path' if has_glob else '-LiteralPath'
            cmd = (
                f'Get-Item {path_arg} {powershell_literal(pattern)} -Force -ErrorAction SilentlyContinue '
                '-ErrorVariable globErr | ForEach-Object { '
                'if ($_.PSIsContainer) { "D:" + $_.FullName } else { "F:" + $_.FullName } }' + _POWERSHELL_DENIED_EXIT
            )
        else:
            words = shell_glob_word(pattern) if has_glob else shlex.quote(pattern)
            cmd = _posix_base_guard(pattern) + (
                f'for p in {words}; do if [ -d "$p" ]; then echo "D:$p"; elif [ -f "$p" ]; then echo "F:$p"; '
                f'elif [ -L "$p" ] || [ -e "$p" ]; then echo "O:$p"; fi; done'
            )
        result = await self.vm.run_command(cmd, silent=True)
        if result.returncode != 0:
            raise RuntimeError(f'listing {pattern} on the guest failed: {result.stderr}')
        kinds = {'F': 'file', 'D': 'dir', 'O': 'other'}
        found = []
        for line in result.stdout.splitlines():
            tag, sep, path = line.strip().partition(':')
            if sep and tag in kinds and path:
                found.append((path, kinds[tag]))
        return found

    async def get_file_metadata(self, guest_path: str) -> FileMetadata:
        """Collect file metadata from guest via QGA stat command.

        This is important for tests that check permissions, timestamps, etc.
        since pulled files have host metadata, not guest metadata.

        Args:
            guest_path: Absolute path on guest

        Returns:
            FileMetadata with guest-side file attributes
        """
        if guest_path in self._metadata_cache:
            return self._metadata_cache[guest_path]

        metadata = FileMetadata()

        if self.is_windows:
            cmd = (
                f'$f = Get-Item -LiteralPath {powershell_literal(guest_path)} -Force; '
                f'"PERM:NA"; '
                f'"OWNER:" + (Get-Acl $f.FullName).Owner; '
                f'"SIZE:" + $f.Length; '
                f'"MTIME:" + (Get-Date $f.LastWriteTimeUtc -UFormat "%s"); '
                f'"ATIME:" + (Get-Date $f.LastAccessTimeUtc -UFormat "%s"); '
                f'"CTIME:" + (Get-Date $f.CreationTimeUtc -UFormat "%s")'
            )
        else:
            cmd = f"stat -c 'PERM:%a OWNER:%U GROUP:%G SIZE:%s MTIME:%Y ATIME:%X CTIME:%Z' -- {shlex.quote(guest_path)}"

        result = await self.vm.run_command(cmd, silent=True)
        if result.returncode != 0:
            log.warning(f"GuestFileProxy: stat failed for {guest_path}: {result.stderr}")
            return metadata

        output = result.stdout.strip()

        if self.is_windows:
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('OWNER:'):
                    metadata.owner = line[6:]
                elif line.startswith('SIZE:'):
                    with contextlib.suppress(ValueError):
                        metadata.size = int(line[5:])
                elif line.startswith('MTIME:'):
                    with contextlib.suppress(ValueError):
                        metadata.mtime = float(line[6:])
                elif line.startswith('ATIME:'):
                    with contextlib.suppress(ValueError):
                        metadata.atime = float(line[6:])
                elif line.startswith('CTIME:'):
                    with contextlib.suppress(ValueError):
                        metadata.ctime = float(line[6:])
        else:
            # Parse: PERM:644 OWNER:root GROUP:root SIZE:1234 MTIME:... ATIME:... CTIME:...
            for part in output.split():
                if ':' not in part:
                    continue
                key, _, value = part.partition(':')
                if key == 'PERM':
                    metadata.permissions = value
                elif key == 'OWNER':
                    metadata.owner = value
                elif key == 'GROUP':
                    metadata.group = value
                elif key == 'SIZE':
                    with contextlib.suppress(ValueError):
                        metadata.size = int(value)
                elif key == 'MTIME':
                    with contextlib.suppress(ValueError):
                        metadata.mtime = float(value)
                elif key == 'ATIME':
                    with contextlib.suppress(ValueError):
                        metadata.atime = float(value)
                elif key == 'CTIME':
                    with contextlib.suppress(ValueError):
                        metadata.ctime = float(value)

        self._metadata_cache[guest_path] = metadata
        log.debug(f"GuestFileProxy: collected metadata for {guest_path}: {metadata}")
        return metadata

    async def file_exists(self, guest_path: str) -> bool:
        """Check if a file exists on the guest.

        Args:
            guest_path: Absolute path to check

        Returns:
            True if file exists
        """
        from adare.hypervisor.qemu.qga_file_transfer import QGAFileTransfer

        transfer = QGAFileTransfer(self.vm)
        return await transfer.file_exists(guest_path)

    def get_cached_path(self, guest_path: str) -> Path | None:
        """Get the local cached path for a guest file, if already pulled.

        Args:
            guest_path: Guest file path

        Returns:
            Local path if cached, None otherwise
        """
        return self._cache.get(guest_path)

    def cleanup(self):
        """Remove the temp directory and all cached files."""
        if self._temp_root.exists():
            shutil.rmtree(self._temp_root, ignore_errors=True)
            log.debug(f"GuestFileProxy: cleaned up {self._temp_root}")
        self._cache.clear()
        self._metadata_cache.clear()

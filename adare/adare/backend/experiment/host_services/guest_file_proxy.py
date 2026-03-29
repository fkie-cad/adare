"""
Guest File Proxy for Host-Mode Test Execution.

Wraps QGAFileTransfer to pull files from guest VM to a local temp directory,
with caching to avoid re-downloading the same file multiple times.
"""

import logging
import tempfile
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .vm_operation_proxy import VMOperationProxy

log = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata collected from guest file via QGA stat."""
    permissions: Optional[str] = None  # e.g. '0644'
    owner: Optional[str] = None
    group: Optional[str] = None
    size: Optional[int] = None
    mtime: Optional[float] = None  # modification time (epoch)
    atime: Optional[float] = None  # access time (epoch)
    ctime: Optional[float] = None  # change time (epoch)


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
        self._cache: Dict[str, Path] = {}  # guest_path → local_path
        self._metadata_cache: Dict[str, FileMetadata] = {}
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
            FileNotFoundError: If file doesn't exist on guest
            RuntimeError: If download fails
        """
        if not force and guest_path in self._cache:
            log.debug(f"GuestFileProxy: cache hit for {guest_path}")
            return self._cache[guest_path]

        local_path = self._guest_path_to_local(guest_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from adare.hypervisor.qemu.qga_file_transfer import QGAFileTransfer
            transfer = QGAFileTransfer(self.vm)
            await transfer.download_file(guest_path, local_path)
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

    async def resolve_guest_glob(self, pattern: str) -> List[str]:
        """Resolve a glob/wildcard pattern on the guest side.

        Args:
            pattern: Glob pattern (e.g. '/var/log/*.log' or 'C:\\Users\\*\\Desktop')

        Returns:
            List of matching absolute paths on guest
        """
        if self.is_windows:
            cmd = (
                f'Get-ChildItem -Path "{pattern}" -ErrorAction SilentlyContinue '
                f'| ForEach-Object {{ $_.FullName }}'
            )
        else:
            # Use find with -path for glob-like behavior, or ls for simple globs
            cmd = f"ls -d {pattern} 2>/dev/null || true"

        result = await self.vm.run_command(cmd, silent=True)
        if result.returncode != 0:
            log.warning(f"GuestFileProxy: glob resolution failed for '{pattern}': {result.stderr}")
            return []

        paths = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        log.debug(f"GuestFileProxy: glob '{pattern}' resolved to {len(paths)} paths")
        return paths

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
                f'$f = Get-Item -LiteralPath "{guest_path}" -Force; '
                f'"PERM:NA"; '
                f'"OWNER:" + (Get-Acl $f.FullName).Owner; '
                f'"SIZE:" + $f.Length; '
                f'"MTIME:" + (Get-Date $f.LastWriteTimeUtc -UFormat "%s"); '
                f'"ATIME:" + (Get-Date $f.LastAccessTimeUtc -UFormat "%s"); '
                f'"CTIME:" + (Get-Date $f.CreationTimeUtc -UFormat "%s")'
            )
        else:
            cmd = f"stat -c 'PERM:%a OWNER:%U GROUP:%G SIZE:%s MTIME:%Y ATIME:%X CTIME:%Z' '{guest_path}'"

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
                    try:
                        metadata.size = int(line[5:])
                    except ValueError:
                        pass
                elif line.startswith('MTIME:'):
                    try:
                        metadata.mtime = float(line[6:])
                    except ValueError:
                        pass
                elif line.startswith('ATIME:'):
                    try:
                        metadata.atime = float(line[6:])
                    except ValueError:
                        pass
                elif line.startswith('CTIME:'):
                    try:
                        metadata.ctime = float(line[6:])
                    except ValueError:
                        pass
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
                    try:
                        metadata.size = int(value)
                    except ValueError:
                        pass
                elif key == 'MTIME':
                    try:
                        metadata.mtime = float(value)
                    except ValueError:
                        pass
                elif key == 'ATIME':
                    try:
                        metadata.atime = float(value)
                    except ValueError:
                        pass
                elif key == 'CTIME':
                    try:
                        metadata.ctime = float(value)
                    except ValueError:
                        pass

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

    def get_cached_path(self, guest_path: str) -> Optional[Path]:
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

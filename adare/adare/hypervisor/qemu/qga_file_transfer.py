"""
QGA-based file transfer for QEMU guests.

Transfers files to/from running QEMU guests via QGA guest-file-* operations.
Used on macOS where virtiofsd and libguestfs are unavailable.

QGA Protocol Commands Used:
    guest-file-open   - opens file on guest, returns handle
    guest-file-write  - writes base64 data to handle (chunked)
    guest-file-read   - reads base64 from handle (chunked)
    guest-file-close  - closes handle
    guest-exec        - for mkdir/ls (via existing run_command infrastructure)
"""
from pathlib import Path, PurePosixPath, PureWindowsPath
import asyncio
import base64
import logging

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)

# Retry configuration for QGA operations
QGA_MAX_RETRIES = 3
QGA_INITIAL_BACKOFF = 2.0  # seconds
QGA_BACKOFF_MULTIPLIER = 2.0
QGA_FILE_OP_TIMEOUT = 60  # seconds per operation (up from 30)


class QGAFileTransfer:
    """Transfer files to/from QEMU guest via QGA guest-file-* operations.

    Used on macOS where virtiofsd and libguestfs are unavailable.
    All methods require the VM to be running with QGA responsive.
    Includes retry logic with exponential backoff for resilience against
    transient guest agent unresponsiveness (common right after boot).
    """

    CHUNK_SIZE = 4 * 1024  # 4KB chunks — smaller base64 payloads reduce transport errors

    def __init__(self, vm):
        self.vm = vm
        self.is_windows = 'windows' in vm.guest_os.lower()

    async def _send_qga_with_retry(self, cmd: dict, operation_desc: str) -> dict:
        """Send a QGA command with retry and exponential backoff.

        Args:
            cmd: QGA command dictionary
            operation_desc: Human-readable description for log messages

        Returns:
            Successful QGA response dictionary

        Raises:
            HypervisorException: If all retries are exhausted
        """
        last_error = ""
        backoff = QGA_INITIAL_BACKOFF

        for attempt in range(1, QGA_MAX_RETRIES + 1):
            response = await self.vm._send_qga_command_via_libvirt(
                cmd, timeout=QGA_FILE_OP_TIMEOUT
            )

            if 'error' not in response:
                if attempt > 1:
                    log.info(f"QGA {operation_desc} succeeded on attempt {attempt}")
                return response

            last_error = response['error'].get('desc', 'Unknown error')
            error_lower = last_error.lower()

            permanent_errors = ('not found', 'no such file', 'permission denied',
                                'invalid argument', 'access denied')
            is_permanent = any(pe in error_lower for pe in permanent_errors)

            if attempt < QGA_MAX_RETRIES and not is_permanent:
                log.warning(
                    f"QGA {operation_desc} failed (attempt {attempt}/{QGA_MAX_RETRIES}): "
                    f"{last_error}, retrying in {backoff:.0f}s..."
                )
                await asyncio.sleep(backoff)
                backoff *= QGA_BACKOFF_MULTIPLIER
            else:
                break

        raise HypervisorException(f"QGA {operation_desc} failed: {last_error}")

    async def _guest_file_open(self, path: str, mode: str = 'r') -> int:
        """Open file on guest via QGA. Returns handle."""
        cmd = {
            "execute": "guest-file-open",
            "arguments": {"path": path, "mode": mode}
        }
        response = await self._send_qga_with_retry(
            cmd, f"file-open '{path}' (mode={mode})"
        )

        handle = response.get('return')
        if handle is None:
            raise HypervisorException(
                f"No handle returned for guest-file-open on '{path}'"
            )
        return handle

    async def _guest_file_write(self, handle: int, data: bytes) -> int:
        """Write chunk to open guest file handle."""
        encoded = base64.b64encode(data).decode('ascii')
        cmd = {
            "execute": "guest-file-write",
            "arguments": {"handle": handle, "buf-b64": encoded}
        }
        response = await self._send_qga_with_retry(
            cmd, f"file-write (handle={handle}, {len(data)} bytes)"
        )
        return response.get('return', {}).get('count', 0)

    async def _guest_file_read(self, handle: int, count: int) -> tuple[bytes, bool]:
        """Read chunk from open guest file handle."""
        cmd = {
            "execute": "guest-file-read",
            "arguments": {"handle": handle, "count": count}
        }
        response = await self._send_qga_with_retry(
            cmd, f"file-read (handle={handle}, {count} bytes)"
        )

        result = response.get('return', {})
        encoded = result.get('buf-b64', '')
        eof = result.get('eof', False)
        data = base64.b64decode(encoded) if encoded else b''
        return data, eof

    async def _guest_file_close(self, handle: int) -> None:
        """Close guest file handle."""
        cmd = {
            "execute": "guest-file-close",
            "arguments": {"handle": handle}
        }
        try:
            await self._send_qga_with_retry(cmd, f"file-close (handle={handle})")
        except HypervisorException as e:
            log.warning(f"Failed to close guest file handle {handle}: {e}")

    async def mkdir_p(self, guest_path: str) -> None:
        """Create directory tree on guest via guest-exec.

        Args:
            guest_path: Directory path to create on guest
        """
        if self.is_windows:
            cmd = f'New-Item -ItemType Directory -Path "{guest_path}" -Force | Out-Null'
        else:
            cmd = f"sudo mkdir -p '{guest_path}' && sudo chmod 755 '{guest_path}'"

        result = await self.vm.run_command(cmd, silent=True)
        if result.returncode != 0:
            raise HypervisorException(
                f"Failed to create directory '{guest_path}' on guest: {result.stderr}"
            )

    async def upload_file(self, host_path: Path, guest_path: str) -> None:
        """Upload single file from host to guest.

        Reads host file, opens guest file for writing, writes in chunks, closes.
        If a chunk write fails, closes the handle and retries the entire file
        upload from scratch (the old handle is unusable after a timeout).

        Args:
            host_path: Path on host to read from
            guest_path: Path on guest to write to

        Raises:
            HypervisorException: If transfer fails after all retries
        """
        if not host_path.exists():
            raise HypervisorException(f"Source file not found: {host_path}")

        file_size = host_path.stat().st_size
        log.debug(f"Uploading {host_path.name} ({file_size} bytes) -> {guest_path}")

        last_error = None
        for attempt in range(1, QGA_MAX_RETRIES + 1):
            handle = None
            try:
                handle = await self._guest_file_open(guest_path, mode='wb')
                with open(host_path, 'rb') as f:
                    bytes_written = 0
                    while True:
                        chunk = f.read(self.CHUNK_SIZE)
                        if not chunk:
                            break
                        written = await self._guest_file_write(handle, chunk)
                        bytes_written += written
                        await asyncio.sleep(0.05)

                log.debug(f"Uploaded {bytes_written} bytes to {guest_path}")
                await self._guest_file_close(handle)
                return  # success

            except HypervisorException as e:
                last_error = e
                log.warning(
                    f"Upload of {host_path.name} failed on attempt {attempt}/{QGA_MAX_RETRIES}: {e}"
                )
                # Try to close the broken handle (best-effort)
                if handle is not None:
                    try:
                        await self._guest_file_close(handle)
                    except HypervisorException:
                        pass

                if attempt < QGA_MAX_RETRIES:
                    backoff = QGA_INITIAL_BACKOFF * (QGA_BACKOFF_MULTIPLIER ** (attempt - 1))
                    log.info(f"Retrying upload of {host_path.name} in {backoff:.0f}s...")
                    await asyncio.sleep(backoff)

        raise HypervisorException(
            f"Failed to upload {host_path.name} after {QGA_MAX_RETRIES} attempts: {last_error}"
        )

    async def upload_directory(self, host_path: Path, guest_path: str) -> None:
        """Recursively upload directory from host to guest.

        Creates directory structure on guest, then uploads each file.

        Args:
            host_path: Directory on host to upload
            guest_path: Destination directory on guest
        """
        if not host_path.is_dir():
            raise HypervisorException(f"Source directory not found: {host_path}")

        await self.mkdir_p(guest_path)

        for item in sorted(host_path.rglob('*')):
            relative = item.relative_to(host_path)

            if self.is_windows:
                dest = f"{guest_path}\\{str(relative).replace('/', '\\')}"
            else:
                dest = f"{guest_path}/{relative}"

            if item.is_dir():
                await self.mkdir_p(dest)
            elif item.is_file():
                # Ensure parent exists
                if self.is_windows:
                    parent = str(PureWindowsPath(dest).parent)
                else:
                    parent = str(PurePosixPath(dest).parent)
                await self.mkdir_p(parent)
                await self.upload_file(item, dest)

    async def download_file(self, guest_path: str, host_path: Path) -> None:
        """Download single file from guest to host.

        Opens guest file for reading, reads in chunks, writes to host.

        Args:
            guest_path: Path on guest to read from
            host_path: Path on host to write to

        Raises:
            HypervisorException: If transfer fails
        """
        host_path.parent.mkdir(parents=True, exist_ok=True)

        handle = await self._guest_file_open(guest_path, mode='rb')
        try:
            with open(host_path, 'wb') as f:
                while True:
                    data, eof = await self._guest_file_read(handle, self.CHUNK_SIZE)
                    if data:
                        f.write(data)
                    if eof:
                        break

            log.debug(f"Downloaded {guest_path} -> {host_path} ({host_path.stat().st_size} bytes)")
        finally:
            await self._guest_file_close(handle)

    async def download_directory(self, guest_path: str, host_path: Path) -> None:
        """Download directory from guest to host.

        Lists guest directory contents via guest-exec, then recursively downloads.

        Args:
            guest_path: Directory on guest to download
            host_path: Destination directory on host
        """
        host_path.mkdir(parents=True, exist_ok=True)

        # List directory contents on guest
        if self.is_windows:
            cmd = (
                f'Get-ChildItem -Path "{guest_path}" -Recurse -File '
                f'| ForEach-Object {{ $_.FullName.Substring({len(guest_path) + 1}) }}'
            )
        else:
            cmd = f"find '{guest_path}' -type f -printf '%P\\n'"

        result = await self.vm.run_command(cmd, silent=True)
        if result.returncode != 0:
            log.warning(f"Failed to list guest directory '{guest_path}': {result.stderr}")
            return

        # Download each file
        for relative_path in result.stdout.strip().split('\n'):
            relative_path = relative_path.strip()
            if not relative_path:
                continue

            if self.is_windows:
                guest_file = f"{guest_path}\\{relative_path}"
            else:
                guest_file = f"{guest_path}/{relative_path}"

            host_file = host_path / relative_path.replace('\\', '/')
            host_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                await self.download_file(guest_file, host_file)
            except HypervisorException as e:
                log.warning(f"Failed to download {guest_file}: {e}")

    async def file_exists(self, guest_path: str) -> bool:
        """Check if path exists on guest via guest-exec.

        Args:
            guest_path: Path to check on guest

        Returns:
            True if path exists
        """
        if self.is_windows:
            cmd = f'if (Test-Path "{guest_path}") {{ echo "EXISTS" }} else {{ echo "MISSING" }}'
        else:
            cmd = f"test -e '{guest_path}' && echo EXISTS || echo MISSING"

        result = await self.vm.run_command(cmd, silent=True)
        return 'EXISTS' in result.stdout

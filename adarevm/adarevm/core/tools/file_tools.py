"""
File tool methods for AdareVMServer.

Provides file transfer (chunked pull) and filesystem snapshot capabilities
for the VM guest agent.
"""

from __future__ import annotations

import base64
import logging
import platform
import time as time_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from adarelib.websocket.protocol import EventType

log = logging.getLogger(__name__)


class FileToolsMixin:
    """Mixin providing file-related tool methods."""

    async def _pull_file_chunk(self, websocket, guest_path: str, chunk_index: int,
                              chunk_size: int = 1048576):
        """
        Read and send a file chunk from guest to host.

        Args:
            websocket: Client websocket connection
            guest_path: Path to file on guest
            chunk_index: Zero-based chunk index
            chunk_size: Bytes per chunk (default 1MB)

        Returns:
            Dict with chunk data, metadata, and progress info
        """
        import stat

        try:
            file_path = Path(guest_path)

            # Validate file exists
            if not file_path.exists():
                return {
                    "status": "error",
                    "error": f"File not found: {guest_path}"
                }

            # Check if directory
            if file_path.is_dir():
                return {
                    "status": "error",
                    "error": f"Path is a directory: {guest_path}. Use hypervisor mode for directories.",
                    "is_directory": True
                }

            # Get file size and calculate chunks
            file_size = file_path.stat().st_size
            total_chunks = (file_size + chunk_size - 1) // chunk_size

            # Validate chunk index
            if chunk_index >= total_chunks:
                return {
                    "status": "error",
                    "error": f"Chunk index {chunk_index} out of range (total: {total_chunks})"
                }

            # Read chunk
            offset = chunk_index * chunk_size
            with open(file_path, 'rb') as f:
                f.seek(offset)
                chunk_data = f.read(chunk_size)

            # Encode chunk as base64
            encoded_chunk = base64.b64encode(chunk_data).decode('utf-8')

            result = {
                "status": "success",
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
                "chunk_data": encoded_chunk,
                "file_size": file_size,
                "is_directory": False
            }

            # Include metadata only in first chunk
            if chunk_index == 0:
                file_stat = file_path.stat()
                result["file_metadata"] = {
                    "filename": file_path.name,
                    "permissions": oct(stat.S_IMODE(file_stat.st_mode)),
                    "modified_time": file_stat.st_mtime,
                    "is_symlink": file_path.is_symlink()
                }

            # Send progress event
            percent = ((chunk_index + 1) / total_chunks) * 100
            await self.send_event(websocket, EventType.PROGRESS, {
                "operation": "file_transfer",
                "file_path": str(guest_path),
                "bytes_transferred": offset + len(chunk_data),
                "total_bytes": file_size,
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
                "percent_complete": percent
            })

            return result

        except PermissionError as e:
            log.error(f"Permission denied reading {guest_path}: {e}")
            return {"status": "error", "error": f"Permission denied: {e}"}
        except OSError as e:
            log.error(f"OS error reading {guest_path}: {e}")
            return {"status": "error", "error": f"OS error: {e}"}
        except Exception as e:
            log.error(f"Unexpected error in pull_file_chunk: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def _get_filesystem_snapshot(self, websocket, root_path: str = '/', timeout: float = 600.0):
        """
        Get filesystem snapshot directly without shelling out to Python.

        Captures file metadata using platform-specific approaches:
        - Windows: MFT reader for NTFS timestamps
        - Linux: find command via LinuxFSSnapshot

        Args:
            root_path: Root directory to scan (default: '/')
            timeout: Timeout in seconds (default: 600)

        Returns:
            Dict with snapshot data or error
        """
        platform_name = platform.system().lower()
        collection_start = time_module.time()

        log.info(f"Starting filesystem snapshot from {root_path} on {platform_name}")

        try:
            await self.send_event(websocket, EventType.LOG, {
                "message": f"Starting filesystem snapshot from {root_path}"
            })

            if platform_name == 'windows':
                from adarevm.platforms.mft_reader import MFTReader, MFTReaderException
                try:
                    snapshot_data = MFTReader.get_mft_snapshot(volume='C:', root_path=root_path)
                except MFTReaderException as e:
                    log.error(f"MFT snapshot failed: {e}")
                    await self.send_event(websocket, EventType.ERROR, {
                        "message": f"MFT snapshot failed: {e}"
                    })
                    return {"status": "error", "message": str(e)}

            elif platform_name == 'linux':
                from adarevm.platforms.linux_fs_snapshot import LinuxFSSnapshot, LinuxFSSnapshotException
                try:
                    snapshot_data = LinuxFSSnapshot.get_snapshot(root_path=root_path)
                except LinuxFSSnapshotException as e:
                    log.error(f"Linux filesystem snapshot failed: {e}")
                    await self.send_event(websocket, EventType.ERROR, {
                        "message": f"Filesystem snapshot failed: {e}"
                    })
                    return {"status": "error", "message": str(e)}
            else:
                error_msg = f"Unsupported platform: {platform_name}"
                log.error(error_msg)
                return {"status": "error", "message": error_msg}

            collection_time = time_module.time() - collection_start

            log.info(f"Filesystem snapshot complete: {len(snapshot_data)} files in {collection_time:.2f}s")

            await self.send_event(websocket, EventType.LOG, {
                "message": f"Snapshot complete: {len(snapshot_data)} files in {collection_time:.2f}s"
            })

            return {
                "status": "success",
                "snapshot": snapshot_data,
                "file_count": len(snapshot_data),
                "collection_time": collection_time
            }

        except ImportError as e:
            error_msg = f"Snapshot module not available: {e}"
            log.error(error_msg)
            await self.send_event(websocket, EventType.ERROR, {
                "message": error_msg
            })
            return {"status": "error", "message": error_msg}

"""
Mixin for filesystem-related playbook actions.

Includes: snapshot_filesystem, pull_changed_files, and related helpers.
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any

from adare.types.playbook import (
    SnapshotFilesystemAction, PullChangedFilesAction,
)
from adare.backend.experiment.filesystem_snapshot import (
    FilesystemSnapshot, calculate_diff,
)
from .base import ActionResult

log = logging.getLogger(__name__)


class FilesystemActionsMixin:
    """Mixin providing filesystem action execution methods for SimpleActionsExecutor."""

    async def execute_snapshot_filesystem(self, action: SnapshotFilesystemAction,
                                          parent_event_id: str = None,
                                          event_emitter = None) -> ActionResult:
        """
        Execute filesystem snapshot action.

        Captures filesystem state (file list + timestamps) and stores in variable.
        Uses native WebSocket tool instead of shelling out to Python.
        """
        from datetime import datetime, timezone

        try:
            # Determine OS type from VM
            os_type = None
            if self.vm and hasattr(self.vm, 'guest_os'):
                os_type = self.vm.guest_os

            if not os_type:
                return ActionResult(
                    success=False,
                    message="Cannot determine VM OS type for filesystem snapshot"
                )

            log.info(f"Capturing filesystem snapshot for {os_type} (variable: {action.variable})")

            # Set appropriate timeout for snapshot (can take several minutes for large drives)
            snapshot_timeout = action.timeout if action.timeout else 600.0  # Default 10 minutes

            # Use native WebSocket tool instead of shell command
            result = await self.client.get_filesystem_snapshot(
                root_path=action.root_path or '/',
                timeout=snapshot_timeout + 60  # Add buffer for WebSocket timeout
            )

            # Check result status
            if result.get('status') != 'success':
                error_msg = result.get('message', 'Unknown error')

                # Enhanced error handling for MFT privilege issues
                if 'Administrator privileges required' in error_msg:
                    return ActionResult(
                        success=False,
                        message=(
                            "MFT snapshot requires Administrator privileges. "
                            "Please ensure adarevm is running as Administrator in the VM."
                        )
                    )

                return ActionResult(
                    success=False,
                    message=f"Snapshot failed: {error_msg}"
                )

            # Extract files directly from result (already parsed JSON)
            files = result.get('snapshot', {})
            log.info(f"Snapshot captured {len(files)} files")

            # Create snapshot object
            snapshot = FilesystemSnapshot(
                files=files,
                timestamp=datetime.now(timezone.utc).isoformat(),
                os_type=os_type
            )

            # Store in execution context
            self.execution_context[action.variable] = snapshot

            # Also store in variable registry if available
            if hasattr(self.playbook, 'variables') and self.playbook.variables:
                from adarelib.common.variables import Variable
                snapshot_var = Variable(value=snapshot, type='object')
                self.playbook.variables.add(action.variable, snapshot_var)
                log.info(f"Stored snapshot in variable '{action.variable}'")

            return ActionResult(
                success=True,
                message=f"Captured filesystem snapshot ({len(files)} files) in variable '{action.variable}'",
                data={
                    'variable': action.variable,
                    'file_count': len(files),
                    'os_type': os_type
                }
            )

        except Exception as e:
            log.error(f"Error executing snapshot_filesystem action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_pull_changed_files(self, action: PullChangedFilesAction,
                                        parent_event_id: str = None,
                                        event_emitter = None) -> ActionResult:
        """
        Execute pull_changed_files action.

        Retrieves two snapshots from variable registry, calculates diff,
        and pulls all changed/added files in batch.
        """
        try:
            # 1. Retrieve snapshots from execution context
            snapshot_before = self.execution_context.get(action.snapshot_before)
            snapshot_after = self.execution_context.get(action.snapshot_after)

            # Validate snapshots exist
            if snapshot_before is None:
                return ActionResult(
                    success=False,
                    message=f"Snapshot variable '{action.snapshot_before}' not found in execution context"
                )

            if snapshot_after is None:
                return ActionResult(
                    success=False,
                    message=f"Snapshot variable '{action.snapshot_after}' not found in execution context"
                )

            # Validate snapshot types
            if not isinstance(snapshot_before, FilesystemSnapshot):
                return ActionResult(
                    success=False,
                    message=f"Variable '{action.snapshot_before}' is not a FilesystemSnapshot object"
                )

            if not isinstance(snapshot_after, FilesystemSnapshot):
                return ActionResult(
                    success=False,
                    message=f"Variable '{action.snapshot_after}' is not a FilesystemSnapshot object"
                )

            log.info(
                f"Computing diff between snapshots: "
                f"{action.snapshot_before} ({len(snapshot_before.files)} files) -> "
                f"{action.snapshot_after} ({len(snapshot_after.files)} files)"
            )

            # 2. Calculate diff
            diff = calculate_diff(snapshot_before, snapshot_after)

            # 3. Build file list based on include flags
            files_to_pull = []

            if action.include_modified:
                modified_paths = [item['path'] for item in diff['modified']]
                files_to_pull.extend(modified_paths)
                log.info(f"Including {len(modified_paths)} modified files")

            if action.include_added:
                added_paths = [item['path'] for item in diff['added']]
                files_to_pull.extend(added_paths)
                log.info(f"Including {len(added_paths)} added files")

            # Check if there are files to pull
            if not files_to_pull:
                log.info("No changed files to pull")
                return ActionResult(
                    success=True,
                    message="No changed files found between snapshots",
                    data={
                        'modified_count': len(diff['modified']),
                        'added_count': len(diff['added']),
                        'files_pulled': 0
                    }
                )

            log.info(f"Total files to pull: {len(files_to_pull)}")

            # 4. Ensure experiment run directory exists
            if not self.experiment_run_directory:
                return ActionResult(
                    success=False,
                    message="Experiment run directory not available"
                )

            # Create destination directory
            dest_dir = Path(self.experiment_run_directory) / "artifacts" / action.dst
            dest_dir.mkdir(parents=True, exist_ok=True)

            log.info(f"Destination directory: {dest_dir}")

            # 5. Execute transfer based on mode
            start_time = time.time()
            effective_mode = self._resolve_pull_mode(action.mode)

            if effective_mode == 'websocket':
                # Use batch chunked transfer
                result = await self._pull_changed_files_websocket(
                    files_to_pull, dest_dir, event_emitter
                )
            else:  # hypervisor mode
                result = await self._pull_changed_files_hypervisor(
                    files_to_pull, dest_dir
                )

            execution_time = time.time() - start_time

            # 6. Prepare result
            success = result['success_count'] > 0

            if result['failed_count'] == 0:
                message = (
                    f"Successfully pulled {result['success_count']} changed files "
                    f"via {effective_mode} ({result['total_bytes']} bytes)"
                )
            else:
                message = (
                    f"Pulled {result['success_count']}/{len(files_to_pull)} files "
                    f"({result['failed_count']} failed)"
                )

            return ActionResult(
                success=success,
                message=message,
                execution_time=execution_time,
                data={
                    'mode': effective_mode,
                    'snapshot_before': action.snapshot_before,
                    'snapshot_after': action.snapshot_after,
                    'total_files': len(files_to_pull),
                    'success_count': result['success_count'],
                    'failed_count': result['failed_count'],
                    'total_bytes': result['total_bytes'],
                    'failures': result['failures'],
                    'modified_count': len(diff['modified']) if action.include_modified else 0,
                    'added_count': len(diff['added']) if action.include_added else 0,
                    'destination': str(dest_dir)
                }
            )

        except Exception as e:
            log.error(f"Error executing pull_changed_files action: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def _pull_changed_files_websocket(self, file_paths: list, dest_dir: Path,
                                           event_emitter) -> Dict[str, Any]:
        """Pull changed files via WebSocket with batch chunked transfer."""
        try:
            # Progress callback for logging
            def progress_callback(file_idx, total_files, file_path,
                                chunk_idx, total_chunks, bytes_xfer, file_size):
                # Calculate overall progress percentage
                overall_progress = (file_idx - 1) / total_files * 100
                file_progress = bytes_xfer / file_size * 100 if file_size > 0 else 0

                log.info(
                    f"Transfer progress: file {file_idx}/{total_files} "
                    f"({overall_progress:.1f}% overall) - "
                    f"chunk {chunk_idx + 1}/{total_chunks} "
                    f"({bytes_xfer}/{file_size} bytes, {file_progress:.1f}%)"
                )

            # Call batch pull method
            result = await self.client.pull_multiple_files_chunked(
                guest_paths=file_paths,
                host_dest_dir=dest_dir,
                progress_callback=progress_callback
            )

            return result

        except Exception as e:
            log.error(f"WebSocket batch pull failed: {e}")
            return {
                'success_count': 0,
                'failed_count': len(file_paths),
                'total_files': len(file_paths),
                'total_bytes': 0,
                'failures': [{'path': p, 'error': str(e)} for p in file_paths],
                'file_results': []
            }

    async def _pull_changed_files_hypervisor(self, file_paths: list, dest_dir: Path) -> Dict[str, Any]:
        """Pull changed files via VBoxManage (hypervisor mode)."""
        if not self.vm:
            return {
                'success_count': 0,
                'failed_count': len(file_paths),
                'total_files': len(file_paths),
                'total_bytes': 0,
                'failures': [{'path': p, 'error': 'VM instance not available'} for p in file_paths],
                'file_results': []
            }

        success_count = 0
        failed_count = 0
        total_bytes = 0
        failures = []
        file_results = []

        for file_idx, guest_path in enumerate(file_paths, start=1):
            try:
                log.info(f"Pulling file {file_idx}/{len(file_paths)}: {guest_path}")

                # Preserve directory structure
                if ':' in guest_path:  # Windows path
                    guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
                    relative_path = guest_path_cleaned.replace('\\', '/')
                else:  # Unix path
                    relative_path = guest_path.lstrip('/')

                host_path = dest_dir / relative_path
                host_path.parent.mkdir(parents=True, exist_ok=True)

                # Use VBoxManage to copy file
                success = await self.vm.copy_from_guest(
                    guest_path=guest_path,
                    host_path=str(host_path),
                    recursive=False
                )

                if success:
                    file_size = host_path.stat().st_size if host_path.is_file() else 0
                    success_count += 1
                    total_bytes += file_size

                    file_results.append({
                        'path': guest_path,
                        'success': True,
                        'destination': str(host_path),
                        'file_size': file_size
                    })

                    log.info(f"Successfully pulled {guest_path} ({file_size} bytes)")
                else:
                    failed_count += 1
                    error_msg = "VBoxManage copy_from_guest returned False"
                    failures.append({'path': guest_path, 'error': error_msg})
                    file_results.append({'path': guest_path, 'success': False, 'error': error_msg})

            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                log.error(f"Hypervisor pull failed for {guest_path}: {error_msg}")
                failures.append({'path': guest_path, 'error': error_msg})
                file_results.append({'path': guest_path, 'success': False, 'error': error_msg})

        return {
            'success_count': success_count,
            'failed_count': failed_count,
            'total_files': len(file_paths),
            'total_bytes': total_bytes,
            'failures': failures,
            'file_results': file_results
        }

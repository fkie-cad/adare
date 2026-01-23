"""
Disk Management Mixin - Base disks, overlays, and cleanup operations.
"""
import asyncio
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from adare.hypervisor.exceptions import HypervisorException

if TYPE_CHECKING:
    from adare.hypervisor.qemu.vm import QEMUVM

log = logging.getLogger(__name__)


class DiskManagementMixin:
    """
    Mixin for disk management operations.

    Handles base disk resolution, overlay creation/cleanup, and disk path management.
    Prevents overlay chaining by always using the true base disk as backing file.
    """

    def get_base_disk_path(self: 'QEMUVM') -> str:
        """
        Get path for immutable base disk.

        The base disk is never modified after creation. It serves as the
        backing file for experiment-specific overlays.

        For external VMs: Returns the external path directly (original IS the base)
        For managed VMs: Returns path with -base suffix

        Returns:
            Path to base disk
        """
        # External qcow2: the original file IS the base (no -base suffix needed)
        if self._external_disk_path:
            return self._external_disk_path

        # Managed VM: add -base suffix
        current_disk = Path(self.config.disk_path)
        return str(current_disk.parent / f"{current_disk.stem}-base{current_disk.suffix}")

    def _get_true_base_disk(self: 'QEMUVM') -> str:
        """
        Get the TRUE base disk path, ignoring any overlay paths in config.

        This method ensures we ALWAYS use the original base disk (never an overlay)
        when creating new overlays. This prevents overlay chaining which causes
        logs/data from previous runs to accumulate.

        Priority:
        1. For external qcow2 (--no-copy mode): Use the original external path
        2. For managed VMs: Use the -base.qcow2 file

        Returns:
            Absolute path to the true base disk

        Raises:
            HypervisorException: If no valid base disk can be found
        """
        # Priority 1: External qcow2 (--no-copy mode)
        # self._external_disk_path is set at init and NEVER changes
        if self._external_disk_path:
            external_path = Path(self._external_disk_path)
            if external_path.exists():
                log.debug(f"CLAUDE: True base disk (external): {external_path}")
                return str(external_path)
            else:
                raise HypervisorException(
                    f"External disk not found: {external_path}\n"
                    f"The original qcow2 file may have been moved or deleted."
                )

        # Priority 2: Managed VM with -base suffix
        # Look for the base disk that was created during import/conversion
        base_disk_path = self.get_base_disk_path()
        if Path(base_disk_path).exists():
            log.debug(f"CLAUDE: True base disk (managed): {base_disk_path}")
            return base_disk_path

        # Fallback: Try to find base by stripping overlay suffixes from config path
        # This handles edge cases where config.disk_path might be an overlay
        current_disk = Path(self.config.disk_path)
        stripped_stem = self._strip_overlay_suffixes(current_disk.stem)
        stripped_stem = stripped_stem.replace('-base', '')  # Also strip -base if present

        # Look for base disk with stripped name
        potential_base = current_disk.parent / f"{stripped_stem}-base{current_disk.suffix}"
        if potential_base.exists():
            log.debug(f"CLAUDE: True base disk (fallback): {potential_base}")
            return str(potential_base)

        # Last resort: check if stripped path exists as standalone qcow2
        potential_standalone = current_disk.parent / f"{stripped_stem}{current_disk.suffix}"
        if potential_standalone.exists() and '-overlay-' not in str(potential_standalone):
            log.debug(f"CLAUDE: True base disk (standalone): {potential_standalone}")
            return str(potential_standalone)

        raise HypervisorException(
            f"Cannot find base disk for VM '{self.vm_name}'.\n"
            f"Checked:\n"
            f"  - External path: {self._external_disk_path}\n"
            f"  - Base disk path: {base_disk_path}\n"
            f"  - Fallback base: {potential_base}\n"
            f"Please ensure the VM has been properly imported."
        )

    @staticmethod
    def _strip_overlay_suffixes(filename_stem: str) -> str:
        """
        Strip all -overlay-{ULID} patterns from a filename stem.

        This prevents filename length explosion when overlays are chained.
        Each ULID is 26 uppercase alphanumeric characters.

        Args:
            filename_stem: Filename without extension (e.g., "VM-name-overlay-01ABC...")

        Returns:
            Cleaned filename stem with all overlay suffixes removed

        Examples:
            >>> _strip_overlay_suffixes("VM-name-overlay-01KDK1XEYYBCSSS33BFD72Q3VV")
            "VM-name"
            >>> _strip_overlay_suffixes("VM-name-overlay-01ABC...-overlay-01DEF...")
            "VM-name"
        """
        # Strip all -overlay-{ULID} patterns (ULID = 26 uppercase alphanumeric chars)
        cleaned = re.sub(r'-overlay-[0-9A-Z]{26}', '', filename_stem)
        log.debug(f"CLAUDE: Stripped overlay suffixes: '{filename_stem}' => '{cleaned}'")
        return cleaned

    def get_overlay_disk_path(self: 'QEMUVM', experiment_id: str) -> str:
        """
        Get path for experiment-specific overlay disk.

        Always derives overlay name from the base VM name by stripping ALL
        -overlay-{ULID} suffixes to prevent filename length explosion from
        chaining overlay names.

        This ensures overlays remain under the ext4 255-character filename limit
        by using a regex pattern to strip all overlay suffixes: -overlay-[0-9A-Z]{26}

        Args:
            experiment_id: Unique experiment ID (ULID - 26 alphanumeric characters)

        Returns:
            Path like: /path/to/VM-name-overlay-{exp_id}.qcow2

        Raises:
            HypervisorException: If generated filename exceeds 255 characters

        Examples:
            Base: ADARE-Ubuntu-24.04_exp_01KDK1XE-base.qcow2
            Overlay: ADARE-Ubuntu-24.04_exp_01KDK1XE-overlay-01KDKGR211GPRRSC0NGX8GWZMH.qcow2
            (72 characters - well within 255 limit)
        """
        # First, try to get the base disk path (normal case)
        base_disk_path = self.get_base_disk_path()
        base_disk = Path(base_disk_path)

        # Check if base disk exists (managed/converted case)
        if base_disk.exists():
            # Base disk format: VM-name-base.qcow2
            # Extract VM name by removing -base suffix
            vm_name_part = base_disk.stem.replace('-base', '')

            # Strip any overlay suffixes that may have leaked into base name
            # This handles edge cases where base disk was created from overlay
            vm_name_part = self._strip_overlay_suffixes(vm_name_part)

            overlay_name = f"{vm_name_part}-overlay-{experiment_id}{base_disk.suffix}"

            # Validate filename length (ext4 limit: 255 characters)
            if len(overlay_name) > 255:
                raise HypervisorException(
                    f"Overlay filename exceeds 255 character limit: {len(overlay_name)} chars\n"
                    f"Filename: {overlay_name}\n"
                    f"This should not happen with ULID-based naming. Please report this bug."
                )

            log.debug(f"CLAUDE: Generated overlay name (managed case): {overlay_name}")
            return str(base_disk.parent / overlay_name)

        # External qcow2 case: base disk doesn't exist, use config.disk_path directly
        # This handles --no-copy mode where source qcow2 is used without conversion
        current_disk = Path(self.config.disk_path)
        if current_disk.exists() and current_disk.suffix == '.qcow2':
            # Use the original disk name (without -overlay or -base suffix)
            # Strip ALL -overlay-{ULID} patterns to get clean VM name
            vm_name_part = current_disk.stem

            # First strip all overlay suffixes (handles chained overlays)
            vm_name_part = self._strip_overlay_suffixes(vm_name_part)

            # Then strip -base suffix if present
            if '-base' in vm_name_part:
                vm_name_part = vm_name_part.replace('-base', '')

            overlay_name = f"{vm_name_part}-overlay-{experiment_id}{current_disk.suffix}"

            # Validate filename length (ext4 limit: 255 characters)
            if len(overlay_name) > 255:
                raise HypervisorException(
                    f"Overlay filename exceeds 255 character limit: {len(overlay_name)} chars\n"
                    f"Filename: {overlay_name}\n"
                    f"Base VM name may be too long. Consider using a shorter VM name."
                )

            # For external VMs, store overlays in managed storage (not next to original file)
            if self._external_disk_path:
                overlay_dir = Path.home() / '.adare' / 'qemu' / 'disks'
                overlay_dir.mkdir(parents=True, exist_ok=True)
                log.debug(f"CLAUDE: Using managed storage for external VM overlay: {overlay_dir}")
                return str(overlay_dir / overlay_name)
            else:
                # Managed VM - store overlay next to base disk
                log.debug(f"CLAUDE: Generated overlay name (external case): {overlay_name}")
                return str(current_disk.parent / overlay_name)

        # Fallback: should not reach here, but use safe overlay generation
        # This maintains backward compatibility if we missed an edge case
        vm_name_part = self._strip_overlay_suffixes(current_disk.stem)
        vm_name_part = vm_name_part.replace('-base', '')  # Also strip base if present
        overlay_name = f"{vm_name_part}-overlay-{experiment_id}{current_disk.suffix}"

        # Validate filename length (ext4 limit: 255 characters)
        if len(overlay_name) > 255:
            log.warning(
                f"CLAUDE: Fallback overlay name exceeds 255 chars ({len(overlay_name)}): {overlay_name}"
            )
            # Truncate base name to fit within limit
            # 255 - len("-overlay-{26-char-ULID}.qcow2") = 255 - 36 = 219
            max_base_length = 219  # 255 - 36
            if len(vm_name_part) > max_base_length:
                vm_name_part = vm_name_part[:max_base_length]
                overlay_name = f"{vm_name_part}-overlay-{experiment_id}{current_disk.suffix}"
                log.warning(f"CLAUDE: Truncated base name to: {vm_name_part}")

        log.debug(f"CLAUDE: Generated overlay name (fallback case): {overlay_name}")
        return str(current_disk.parent / overlay_name)

    async def create_overlay_disk(self: 'QEMUVM', experiment_id: str) -> str:
        """
        Create qcow2 overlay backed by immutable base disk.

        This creates a new overlay that captures all modifications while
        leaving the base disk untouched. The overlay is deleted after
        experiment completion.

        IMPORTANT: This method always uses the TRUE base disk (via _get_true_base_disk()),
        never an existing overlay. This prevents overlay chaining where logs/data from
        previous runs accumulate.

        Args:
            experiment_id: Unique ID for this experiment

        Returns:
            Path to created overlay disk

        Raises:
            HypervisorException: If overlay creation fails
        """
        # CRITICAL: Always use the TRUE base disk, never an overlay
        # This prevents overlay chaining which causes logs to accumulate
        base_disk = self._get_true_base_disk()
        log.debug(f"CLAUDE: Using true base disk for overlay: {base_disk}")

        # Clean up orphaned overlays from previous crashed runs BEFORE creating new one
        # This ensures we don't leave stale overlays that could confuse the system
        await self._cleanup_orphaned_overlays(experiment_id)

        # Create overlay path with experiment ID
        overlay_path = self.get_overlay_disk_path(experiment_id)

        # Calculate backing file path (absolute for external VMs, relative for managed VMs)
        # External VMs: Use absolute path since overlay is in different directory than base
        # Managed VMs: Use relative path for libguestfs compatibility
        overlay_dir = Path(overlay_path).parent
        base_path = Path(base_disk)

        if self._external_disk_path:
            # External VM - use absolute path (cross-directory backing file)
            backing_file = str(base_path.resolve())
            log.debug(f"CLAUDE: Using absolute backing path for external VM: {backing_file}")
        elif overlay_dir == base_path.parent:
            # Same directory - use just filename (most common case)
            backing_file = base_path.name
        else:
            # Different directories - use relative path
            backing_file = os.path.relpath(base_disk, overlay_dir)

        log.debug(f"CLAUDE: Base disk absolute path: {base_disk}")
        log.debug(f"CLAUDE: Backing file path: {backing_file}")

        # Check available disk space before creating overlay
        import shutil
        stat = shutil.disk_usage(overlay_dir)
        min_required_space = 10 * 1024 * 1024 * 1024  # 10GB minimum
        if stat.free < min_required_space:
            raise HypervisorException(
                f"Insufficient disk space for overlay creation.\n"
                f"Location: {overlay_dir}\n"
                f"Available: {stat.free / (1024**3):.2f} GB\n"
                f"Required: ~10 GB minimum\n"
                f"Please free up disk space and try again."
            )
        log.debug(f"CLAUDE: Disk space check passed: {stat.free / (1024**3):.2f} GB available")

        # Build qemu-img command to create backing file
        qemu_img = self.executables.qemu_img
        args = [
            qemu_img,
            'create',
            '-f', 'qcow2',
            '-F', 'qcow2',  # Backing file format
            '-b', backing_file,  # Backing file (relative path for libguestfs compatibility)
            overlay_path      # New overlay
        ]

        log.debug(f"CLAUDE: Creating overlay disk backed by {backing_file}")
        log.debug(f"CLAUDE: Command: {' '.join(args)}")

        # Execute qemu-img create
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise HypervisorException(
                f"Failed to create overlay disk: {stderr.decode()}"
            )

        log.debug(f"CLAUDE: Successfully created overlay: {overlay_path}")
        return overlay_path

    async def _cleanup_orphaned_overlays(self: 'QEMUVM', current_experiment_id: str) -> None:
        """
        Clean up orphaned overlay disks from previous crashed runs.

        This method finds and deletes overlay files that were left behind when
        previous experiment runs crashed before cleanup could occur.

        Only deletes overlays that:
        1. Match this VM's naming pattern (VM-name-overlay-*.qcow2)
        2. Are NOT the current experiment's overlay
        3. Are NOT the base disk

        Args:
            current_experiment_id: ID of current experiment (will NOT be deleted)
        """
        try:
            # Get the base disk to determine the overlay directory and naming pattern
            base_disk = self._get_true_base_disk()
            base_path = Path(base_disk)

            # Determine overlay directory based on VM type
            if self._external_disk_path:
                # External VM: overlays are in managed storage, not next to base
                overlay_dir = Path.home() / '.adare' / 'qemu' / 'disks'
                # External qcow2: use the original filename stem
                vm_name_stem = Path(self._external_disk_path).stem
                log.debug(f"CLAUDE: Cleaning external VM overlays from managed storage: {overlay_dir}")
            else:
                # Managed VM: overlays are next to base disk
                overlay_dir = base_path.parent
                # Managed VM: strip -base suffix
                vm_name_stem = base_path.stem.replace('-base', '')

            # Strip any overlay suffixes that might have leaked into the stem
            vm_name_stem = self._strip_overlay_suffixes(vm_name_stem)

            # Find all overlays matching this VM's pattern
            overlay_pattern = f"{vm_name_stem}-overlay-*.qcow2"
            orphan_overlays = list(overlay_dir.glob(overlay_pattern))

            # Get the path for current experiment's overlay (should NOT be deleted)
            current_overlay_path = Path(self.get_overlay_disk_path(current_experiment_id))

            # Delete orphaned overlays
            deleted_count = 0
            for overlay in orphan_overlays:
                # Skip current experiment's overlay
                if overlay == current_overlay_path:
                    continue

                # Skip the base disk (shouldn't match pattern, but be safe)
                if overlay == base_path:
                    continue

                # Delete orphaned overlay
                try:
                    overlay.unlink()
                    deleted_count += 1
                    log.info(f"CLAUDE: Deleted orphaned overlay: {overlay.name}")
                except OSError as e:
                    log.warning(f"CLAUDE: Failed to delete orphaned overlay {overlay}: {e}")

            if deleted_count > 0:
                log.info(f"CLAUDE: Cleaned up {deleted_count} orphaned overlay(s)")

        except HypervisorException as e:
            # If we can't determine base disk, log warning but don't fail
            log.warning(f"CLAUDE: Could not clean orphaned overlays: {e}")

    async def cleanup_overlay_disk(self: 'QEMUVM', experiment_id: str) -> None:
        """
        Delete experiment overlay disk.

        This removes the overlay file, leaving the base disk intact.
        The next experiment will create a fresh overlay from the base.

        Args:
            experiment_id: Unique ID for this experiment
        """
        overlay_path = self.get_overlay_disk_path(experiment_id)

        if Path(overlay_path).exists():
            try:
                os.remove(overlay_path)
                log.debug(f"CLAUDE: Deleted overlay disk: {overlay_path}")
            except OSError as e:
                log.warning(f"CLAUDE: Failed to delete overlay {overlay_path}: {e}")
        else:
            log.debug(f"CLAUDE: Overlay already deleted: {overlay_path}")

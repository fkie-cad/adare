"""
SMB file transfer strategy using QEMU SLIRP built-in SMB sharing.

Uses QEMU's user-mode networking SMB support to serve a host directory
to the guest as a CIFS/SMB mount. Requires smbd on the host (e.g.
``brew install samba`` on macOS). Both Linux and Windows guests have
native SMB/CIFS client support.

The strategy creates a temporary directory with copies of each share's
host content (not symlinks — Samba 4.x blocks symlinks outside the share
root), then tells QEMU to serve it via SLIRP SMB. The guest mounts
``//10.0.2.4/qemu`` at ``/adare`` (Linux) or maps it as a network drive
and creates junctions (Windows). Read-write shares are copied back to
the host during artifact retrieval and cleanup.
"""
import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy
from adare.hypervisor.qemu.file_transfer.shares import build_config_json, build_share_list

log = logging.getLogger(__name__)

# QEMU SLIRP SMB gateway address (fixed by QEMU)
SMB_GATEWAY = '10.0.2.4'
SMB_SHARE_NAME = 'qemu'


def _ignore_host_generated_files(directory: str, contents: list[str]) -> set[str]:
    """Skip host-generated files during SMB writeback.

    The SMB temp directory contains stale copies of host-written files
    (notably adare.log). Writing them back would overwrite the live
    versions and erase data written since the share was created.
    """
    if Path(directory).name == 'logs':
        return {'adare.log'}
    return set()


class SMBStrategy(FileTransferStrategy):
    """File transfer via QEMU SLIRP built-in SMB sharing.

    Creates a temp directory with copies of each share's host content,
    configures QEMU to serve it via SLIRP SMB, then mounts it inside
    the guest after boot. Read-write shares are copied back to the host
    during artifact retrieval and cleanup.
    """

    def __init__(self):
        self._smb_dir: Path | None = None
        self._shares: List[Dict[str, Any]] = []
        self._writeback_dirs: Dict[str, Path] = {}  # tag -> original host path (for read-write shares)

    @property
    def setup_description(self) -> str:
        return "Configuring SMB shares"

    @property
    def post_boot_description(self) -> str:
        return "Mounting SMB shares"

    @property
    def retrieval_description(self) -> str:
        return "Verifying SMB shared files"

    async def setup(self, context: Any) -> None:
        """Create shared directory with copies and configure VM for QEMU SLIRP SMB.

        1. Build share list (same as virtiofs)
        2. Create temp dir with copies of each share's host content
        3. Set smb_share_path on VM config so XML builder adds smb= arg
        4. Disable virtiofs (mutually exclusive)

        Uses copytree instead of symlinks because Samba 4.x defaults to
        ``wide links = no``, blocking symlinks whose targets are outside
        the share root. QEMU's auto-generated smb.conf does not override this.

        Args:
            context: ExperimentRunCtx containing directories and VM
        """
        log.info("Using SMB mode for file transfer (QEMU SLIRP SMB)")
        is_windows = 'windows' in context.guest_platform.lower()
        base_mount = 'C:\\adare' if is_windows else '/adare'

        self._shares = build_share_list(context, is_windows, base_mount)

        # Write config.json to run directory
        run_dir = context.experiment_run_directory.path
        config_data = build_config_json(
            is_windows=is_windows,
            installation_mode=context.config.installation_mode,
        )
        with open(run_dir / 'config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        log.debug(f"Wrote config.json to {run_dir / 'config.json'}")

        # Create temp directory with real file copies (not symlinks)
        vm_name = context.vm.config.vm_name
        smb_dir = Path(tempfile.mkdtemp(prefix=f'adare_smb_{vm_name}_'))
        self._smb_dir = smb_dir
        self._writeback_dirs = {}

        for i, share in enumerate(self._shares, 1):
            tag = share['tag']
            host_path = share['host_path']
            target_path = smb_dir / tag

            # Ensure host path exists
            Path(host_path).mkdir(parents=True, exist_ok=True)

            # Count files/size before copying for diagnostics
            src = Path(host_path)
            file_count = sum(1 for _ in src.rglob('*') if _.is_file())
            log.info(
                f"Copying share {i}/{len(self._shares)} '{tag}': "
                f"{host_path} -> {target_path} ({file_count} files)"
            )

            shutil.copytree(host_path, target_path, dirs_exist_ok=True)
            log.info(f"Finished copying share '{tag}'")

            if not share.get('readonly', True):
                self._writeback_dirs[tag] = Path(host_path)

        # Configure VM for SMB (XML builder reads this)
        context.vm.config.smb_share_path = str(smb_dir)
        context.vm.config.virtiofs_enabled = False
        context.vm.config.virtiofs_shares = []
        context.vm._save_vm_config()

        # Store shares on context for post-boot mounting
        context.smb_shares = self._shares

        log.info(
            f"Configured SMB share directory at {smb_dir} "
            f"with {len(self._shares)} shares:"
        )
        for share in self._shares:
            rw = "rw" if not share.get('readonly', True) else "ro"
            log.debug(f"  {share['tag']} ({rw}): {share['host_path']} -> {share['guest_mount']}")

    async def post_boot_transfer(self, context: Any) -> None:
        """Mount SMB share inside the guest after boot.

        Linux: ``mount -t cifs //10.0.2.4/qemu /adare``
        Windows: ``net use Z: \\\\10.0.2.4\\qemu`` + junctions

        Falls back to QGA file-by-file transfer if mount fails.

        Args:
            context: ExperimentRunCtx containing VM
        """
        # Wait for guest OS to stabilize
        stabilization_delay = 5
        log.info(
            f"Waiting {stabilization_delay}s for guest OS to stabilize "
            f"before SMB mount..."
        )
        await asyncio.sleep(stabilization_delay)

        is_windows = 'windows' in context.guest_platform.lower()

        try:
            if is_windows:
                await self._mount_smb_windows(context)
            else:
                await self._mount_smb_linux(context)
        except HypervisorException:
            log.warning("SMB mount failed, falling back to QGA file transfer")
            await self._fallback_to_qga(context)

    async def retrieve_artifacts(self, context: Any) -> None:
        """Copy guest-written files back to host and verify artifacts.

        Since SMB uses copies (not symlinks), read-write shares must be
        copied back to their original host directories so that artifacts,
        logs, and other guest-written files land where the host expects them.

        Args:
            context: ExperimentRunCtx
        """
        log.info("Retrieving artifacts from SMB shared directory")

        # Copy read-write shares back to their original host directories
        self._writeback_to_host()

        run_dir = context.experiment_run_directory.path
        retrieved = []
        missing = []

        # Check artifacts directory
        artifacts_dir = run_dir / 'artifacts'
        if artifacts_dir.exists() and any(artifacts_dir.iterdir()):
            artifact_count = len(list(artifacts_dir.iterdir()))
            retrieved.append(f'artifacts ({artifact_count} items)')
        else:
            missing.append('artifacts')

        # Check log files
        logs_dir = run_dir / 'logs'
        log_files = ['adarevm.log', 'adarevmstartup.log', 'scheduled_task_error.log']

        for log_file in log_files:
            log_path = logs_dir / log_file
            if log_path.exists():
                log_dest = context.experiment_run_directory.log_directory
                if log_dest != logs_dir:
                    import shutil as _shutil
                    _shutil.copy2(log_path, log_dest / log_file)
                    log.debug(f"Copied {log_file} to {log_dest}")
                retrieved.append(log_file)
            else:
                missing.append(log_file)

        if retrieved:
            log.info(f"Found in SMB run share: {', '.join(retrieved)}")
        if missing:
            log.debug(f"Not found in SMB run share (skipped): {', '.join(missing)}")

    def requires_vm_stop_for_retrieval(self) -> bool:
        """SMB does not require VM stop -- artifacts are copied back during retrieval."""
        return False

    def cleanup(self) -> None:
        """Copy back any unwritten read-write shares, then remove the temp directory."""
        # Safety writeback in case retrieve_artifacts() was skipped (e.g. crash)
        self._writeback_to_host()

        if self._smb_dir and self._smb_dir.exists():
            shutil.rmtree(self._smb_dir, ignore_errors=True)
            log.debug(f"Cleaned up SMB directory: {self._smb_dir}")
            self._smb_dir = None

    # ---------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------

    def _writeback_to_host(self) -> None:
        """Copy read-write shares from the temp SMB dir back to their original host paths.

        Clears ``_writeback_dirs`` after copying so that repeated calls
        (e.g. retrieve_artifacts then cleanup) are idempotent.
        """
        if not self._writeback_dirs or not self._smb_dir:
            return

        for tag, host_path in list(self._writeback_dirs.items()):
            smb_copy = self._smb_dir / tag
            if not smb_copy.exists():
                log.debug(f"Writeback skipped for '{tag}': {smb_copy} does not exist")
                continue
            log.info(f"Writing back SMB share '{tag}': {smb_copy} -> {host_path}")
            shutil.copytree(
                smb_copy, host_path, dirs_exist_ok=True,
                ignore=_ignore_host_generated_files,
            )

        self._writeback_dirs.clear()

    async def _mount_smb_linux(self, context: Any) -> None:
        """Mount QEMU SLIRP SMB share on Linux guest."""
        log.info("Mounting SMB share on Linux guest")

        # Create mount point and mount
        mount_cmd = (
            'sudo mkdir -p /adare && '
            f'sudo mount -t cifs //{SMB_GATEWAY}/{SMB_SHARE_NAME} /adare '
            f'-o guest,vers=2.0,uid=0,gid=0'
        )

        result = await context.vm.run_command(
            mount_cmd,
            stop_event=context.user_interrupt_event,
        )

        if result.returncode != 0:
            raise HypervisorException(
                f"Failed to mount SMB share on Linux guest: {result.stderr}"
            )

        # Verify mount
        verify = await context.vm.run_command(
            'mount | grep cifs',
            stop_event=context.user_interrupt_event,
        )

        if 'cifs' in verify.stdout:
            log.info("SMB share mounted successfully on Linux guest at /adare")
        else:
            raise HypervisorException("SMB mount verification failed: mount not found")

    async def _mount_smb_windows(self, context: Any) -> None:
        """Mount QEMU SLIRP SMB share on Windows guest via net use + junctions."""
        log.info("Mounting SMB share on Windows guest")

        # Enable insecure guest auth (Win10+ blocks by default; QEMU smbd uses guest auth)
        await context.vm.run_command(
            'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services'
            '\\LanmanWorkstation\\Parameters" '
            '/v AllowInsecureGuestAuth /t REG_DWORD /d 1 /f',
            stop_event=context.user_interrupt_event,
        )
        log.info("Enabled AllowInsecureGuestAuth registry key")

        # Disable SMB signing requirement (Win11 24H2+ enforces by default;
        # QEMU SLIRP SMB doesn't support signing)
        await context.vm.run_command(
            'Set-SmbClientConfiguration -RequireSecuritySignature $false -Force',
            stop_event=context.user_interrupt_event,
        )
        log.info("Disabled SMB client signing requirement")

        # Map network drive
        map_cmd = (
            f'net use Z: \\\\{SMB_GATEWAY}\\{SMB_SHARE_NAME} /persistent:no'
        )
        result = await context.vm.run_command(
            map_cmd,
            stop_event=context.user_interrupt_event,
        )

        if result.returncode != 0:
            raise HypervisorException(
                f"Failed to map SMB network drive: {result.stderr}"
            )

        # Create base directory and junctions for each subdirectory
        # Use UNC paths directly so junctions work regardless of which user
        # session accesses them (Z: drive is session-scoped)
        junction_cmd = (
            'New-Item -ItemType Directory -Path "C:\\adare" -Force | Out-Null; '
            '$errors = @(); '
            'foreach ($dir in (Get-ChildItem Z:\\ -Directory)) { '
            '  $target = "C:\\adare\\$($dir.Name)"; '
            '  if (-not (Test-Path $target)) { '
            f'    $out = cmd /c mklink /D "$target" "\\\\{SMB_GATEWAY}\\{SMB_SHARE_NAME}\\$($dir.Name)" 2>&1; '
            '    if ($LASTEXITCODE -ne 0) { $errors += "mklink $target failed: $out" } '
            '  } '
            '}; '
            'if ($errors.Count -gt 0) { '
            '  [Console]::Error.WriteLine(($errors -join "; ")); exit 1 '
            '}'
        )

        result = await context.vm.run_command(
            junction_cmd,
            stop_event=context.user_interrupt_event,
        )

        if result.returncode != 0:
            raise HypervisorException(
                f"Failed to create directory junctions: {result.stderr}"
            )

        # Copy tools locally — Windows CreateProcess cannot execute .exe files
        # through directory junctions that point to SMB/UNC paths.
        # Prepend local paths in config.json so the agent finds local copies first.
        local_copy_cmd = (
            '$localBase = "C:\\adare_local"; '
            'foreach ($name in @("shared", "project_shared")) { '
            '  $src = "C:\\adare\\$name\\tools"; '
            '  $dst = "$localBase\\$name\\tools"; '
            '  if (Test-Path $src) { '
            '    New-Item -ItemType Directory -Path $dst -Force | Out-Null; '
            '    Copy-Item "$src\\*" $dst -Recurse -Force -ErrorAction SilentlyContinue '
            '  } '
            '}; '
            '$cfgPath = "C:\\adare\\run\\config.json"; '
            'if (Test-Path $cfgPath) { '
            '  $cfg = Get-Content $cfgPath | ConvertFrom-Json; '
            '  $localPaths = @("C:\\adare_local\\project_shared\\tools", '
            '                  "C:\\adare_local\\shared\\tools"); '
            '  $cfg.tools_paths = $localPaths + @($cfg.tools_paths); '
            '  $cfg | ConvertTo-Json -Depth 10 | Set-Content $cfgPath '
            '}'
        )
        await context.vm.run_command(
            local_copy_cmd,
            stop_event=context.user_interrupt_event,
        )
        log.info("Copied tools locally to C:\\adare_local and updated config.json tools_paths")

        log.info("SMB share mounted successfully on Windows guest at C:\\adare")

    async def _fallback_to_qga(self, context: Any) -> None:
        """Fall back to QGA file-by-file transfer when SMB mount fails."""
        from adare.hypervisor.qemu.file_transfer.qga_strategy import QGAStrategy

        log.warning("Falling back to QGA file transfer strategy")
        qga = QGAStrategy()
        await qga.setup(context)
        await qga.post_boot_transfer(context)

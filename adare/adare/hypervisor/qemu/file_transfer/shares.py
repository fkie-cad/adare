"""
Shared utilities for file transfer strategies.

Contains the share list builder (host→guest directory mappings) and
config.json builder, used by all four strategies (VirtioFS, SMB,
Libguestfs, QGA).
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)

# Stop counting here so a huge data share doesn't stall VM setup
_FILE_COUNT_CAP = 10_000


def _count_files(path: Path) -> str:
    """Count regular files below path, capped at _FILE_COUNT_CAP."""
    count = 0
    for entry in path.rglob('*'):
        if entry.is_file():
            count += 1
            if count >= _FILE_COUNT_CAP:
                return f'{_FILE_COUNT_CAP}+'
    return str(count)


def check_shared_dir(host_path: Path, guest_name: str) -> bool:
    """Log whether a project/experiment shared dir will reach the guest.

    config.json always lists tools/data paths under both shared mounts, so a
    missing host dir means adarevm looks in a path that will not exist. Without
    this warning the share is skipped silently and the guest just lacks it.

    Args:
        host_path: Shared directory on the host
        guest_name: Mount name under the guest base dir (e.g. 'project_shared')

    Returns:
        True if host_path exists and should be shared
    """
    if not host_path.exists():
        log.warning(f"Shared directory {host_path} not found -- the guest will have no '{guest_name}' directory")
        return False
    log.info(f"Sharing {host_path} as guest '{guest_name}' ({_count_files(host_path)} files)")
    return True


def build_share_list(
    context: Any,
    is_windows: bool,
    base_mount: str,
) -> list[dict[str, Any]]:
    """Build the list of share specifications for host→guest directory mapping.

    Used by VirtioFS (virtio-fs tags) and SMB (symlink dirs) strategies.

    Args:
        context: ExperimentRunCtx
        is_windows: True for Windows guests
        base_mount: Base mount path in guest (e.g. /adare or C:\\adare)

    Returns:
        List of share dicts with tag, host_path, guest_mount, readonly keys
    """
    shares: list[dict[str, Any]] = []

    # 1. Run directory -- experiment run artifacts and logs
    run_dir = context.experiment_run_directory.path
    (run_dir / 'logs').mkdir(parents=True, exist_ok=True)
    (run_dir / 'artifacts').mkdir(parents=True, exist_ok=True)

    # Copy playbook.yml to run directory for easy guest access
    if context.experiment_directory:
        shutil.copy2(
            context.experiment_directory.playbookfile,
            run_dir / 'playbook.yml',
        )
        log.debug(f"Copied playbook to {run_dir / 'playbook.yml'}")

    shares.append(
        {
            'tag': 'run',
            'host_path': str(run_dir),
            'guest_mount': f'{base_mount}\\run' if is_windows else f'{base_mount}/run',
            'readonly': False,
        }
    )

    # 2. VM runtime -- adarevm/adarelib wheels or source
    vm_runtime_dir = context.project_directory.vm_runtime
    if not vm_runtime_dir.exists():
        raise HypervisorException(
            f"VM runtime directory not found at {vm_runtime_dir}. Run 'adare experiment load' first."
        )
    shares.append(
        {
            'tag': 'vm',
            'host_path': str(vm_runtime_dir),
            'guest_mount': f'{base_mount}\\vm' if is_windows else f'{base_mount}/vm',
            'readonly': True,
        }
    )

    # 3. Experiment directory (optional)
    if context.experiment_directory:
        experiment_dir = context.experiment_directory.path
        shares.append(
            {
                'tag': 'experiment',
                'host_path': str(experiment_dir),
                'guest_mount': (f'{base_mount}\\experiment' if is_windows else f'{base_mount}/experiment'),
                'readonly': True,
            }
        )

    # 4. Project shared directory (optional)
    if check_shared_dir(context.project_directory.shared, 'project_shared'):
        shares.append(
            {
                'tag': 'project_shared',
                'host_path': str(context.project_directory.shared),
                'guest_mount': (f'{base_mount}\\project_shared' if is_windows else f'{base_mount}/project_shared'),
                'readonly': True,
            }
        )

    # 5. Experiment shared directory (optional)
    if context.experiment_directory and check_shared_dir(context.experiment_directory.shared, 'shared'):
        shares.append(
            {
                'tag': 'shared',
                'host_path': str(context.experiment_directory.shared),
                'guest_mount': (f'{base_mount}\\shared' if is_windows else f'{base_mount}/shared'),
                'readonly': True,
            }
        )

    # 6. User-defined shared directories
    if hasattr(context.config, 'shared_directories') and context.config.shared_directories:
        log.info(f"Configuring {len(context.config.shared_directories)} user-defined shared directories")
        for name, details in context.config.shared_directories.items():
            host_path = details.get('host')
            vm_path = details.get('vm')
            if host_path and vm_path:
                shares.append(
                    {
                        'tag': name,
                        'host_path': str(host_path),
                        'guest_mount': str(vm_path),
                        'readonly': False,
                    }
                )

    return shares


def build_config_json(
    is_windows: bool,
    file_transfer_mode: str,
    installation_mode: str = "wheel",
) -> dict[str, Any]:
    """Build config.json content for adarevm with mount paths.

    This file tells adarevm where to find tools, data, and where to write
    logs. Without it, tools placed in shared directories are not discoverable.

    Args:
        is_windows: True if guest is Windows
        file_transfer_mode: 'virtiofs', 'smb', 'libguestfs' or 'qga'; only
            logged by adarevm so guest logs show how /adare was populated
        installation_mode: "wheel" (pip) or "editable" (Poetry)

    Returns:
        Dictionary with config.json contents
    """
    if is_windows:
        return {
            "tools_paths": [
                "C:\\adare\\project_shared\\tools",
                "C:\\adare\\shared\\tools",
            ],
            "data_paths": [
                "C:\\adare\\project_shared\\data",
                "C:\\adare\\shared\\data",
            ],
            "logfile": "C:\\adare\\run\\logs\\adarevm.log",
            "installation_mode": installation_mode,
            "file_transfer_mode": file_transfer_mode,
        }
    return {
        "tools_paths": [
            "/adare/project_shared/tools",
            "/adare/shared/tools",
        ],
        "data_paths": [
            "/adare/project_shared/data",
            "/adare/shared/data",
        ],
        "logfile": "/adare/run/logs/adarevm.log",
        "installation_mode": installation_mode,
        "file_transfer_mode": file_transfer_mode,
    }

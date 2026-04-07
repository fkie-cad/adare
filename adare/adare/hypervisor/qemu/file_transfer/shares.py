"""
Shared utilities for file transfer strategies.

Contains the share list builder (host→guest directory mappings) and
config.json builder, used by all four strategies (VirtioFS, SMB,
Libguestfs, QGA).
"""
import logging
import shutil
from typing import Any, Dict, List

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


def build_share_list(
    context: Any,
    is_windows: bool,
    base_mount: str,
) -> List[Dict[str, Any]]:
    """Build the list of share specifications for host→guest directory mapping.

    Used by VirtioFS (virtio-fs tags) and SMB (symlink dirs) strategies.

    Args:
        context: ExperimentRunCtx
        is_windows: True for Windows guests
        base_mount: Base mount path in guest (e.g. /adare or C:\\adare)

    Returns:
        List of share dicts with tag, host_path, guest_mount, readonly keys
    """
    shares: List[Dict[str, Any]] = []

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

    shares.append({
        'tag': 'run',
        'host_path': str(run_dir),
        'guest_mount': f'{base_mount}\\run' if is_windows else f'{base_mount}/run',
        'readonly': False,
    })

    # 2. VM runtime -- adarevm/adarelib wheels or source
    vm_runtime_dir = context.project_directory.vm_runtime
    if not vm_runtime_dir.exists():
        raise HypervisorException(
            f"VM runtime directory not found at {vm_runtime_dir}. "
            f"Run 'adare experiment load' first."
        )
    shares.append({
        'tag': 'vm',
        'host_path': str(vm_runtime_dir),
        'guest_mount': f'{base_mount}\\vm' if is_windows else f'{base_mount}/vm',
        'readonly': True,
    })

    # 3. Experiment directory (optional)
    if context.experiment_directory:
        experiment_dir = context.experiment_directory.path
        shares.append({
            'tag': 'experiment',
            'host_path': str(experiment_dir),
            'guest_mount': (
                f'{base_mount}\\experiment' if is_windows
                else f'{base_mount}/experiment'
            ),
            'readonly': True,
        })

    # 4. Project shared directory (optional)
    if context.project_directory.shared.exists():
        shares.append({
            'tag': 'project_shared',
            'host_path': str(context.project_directory.shared),
            'guest_mount': (
                f'{base_mount}\\project_shared' if is_windows
                else f'{base_mount}/project_shared'
            ),
            'readonly': True,
        })

    # 5. Experiment shared directory (optional)
    if (
        context.experiment_directory
        and context.experiment_directory.shared.exists()
    ):
        shares.append({
            'tag': 'shared',
            'host_path': str(context.experiment_directory.shared),
            'guest_mount': (
                f'{base_mount}\\shared' if is_windows
                else f'{base_mount}/shared'
            ),
            'readonly': True,
        })

    # 6. User-defined shared directories
    if (
        hasattr(context.config, 'shared_directories')
        and context.config.shared_directories
    ):
        log.info(
            f"Configuring {len(context.config.shared_directories)} "
            f"user-defined shared directories"
        )
        for name, details in context.config.shared_directories.items():
            host_path = details.get('host')
            vm_path = details.get('vm')
            if host_path and vm_path:
                shares.append({
                    'tag': name,
                    'host_path': str(host_path),
                    'guest_mount': str(vm_path),
                    'readonly': False,
                })

    return shares


def build_config_json(
    is_windows: bool,
    installation_mode: str = "wheel",
) -> Dict[str, Any]:
    """Build config.json content for adarevm with mount paths.

    This file tells adarevm where to find tools, data, and where to write
    logs. Without it, tools placed in shared directories are not discoverable.

    Args:
        is_windows: True if guest is Windows
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
    }

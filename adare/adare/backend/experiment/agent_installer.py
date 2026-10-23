"""
AdareVM Agent Installation Module

Handles version detection and intelligent installation of adarevm and adarelib packages
in guest VMs. Optimizes experiment runs by skipping installation when correct versions
are already present.
"""

import logging
import threading
from pathlib import Path

from adare.backend.experiment.agent_wheels import AGENT_PACKAGES, wheel_versions

log = logging.getLogger(__name__)


async def check_installed_version(
    package_name: str,
    vm,  # VirtualBoxVM instance
    use_conda: bool,
    platform: str,
    stop_event: threading.Event,
    wheels_available: bool = False,
    inject_user_path: bool = False,
) -> str | None:
    """Check if package is installed in VM and return its version.

    Executes 'pip show <package>' in the VM and parses the output to extract
    the installed version. Handles both Conda and Poetry/pip environments.

    Args:
        package_name: Package name to check (e.g., "adarevm", "adarelib")
        vm: VirtualBoxVM instance for command execution
        use_conda: True if using Conda environment, False for Poetry/pip
        platform: Guest OS platform ("windows" or "linux")
        stop_event: Threading event for cancellation
        wheels_available: True if wheels were installed, False for editable install
        inject_user_path: If True, inject user's PATH into the command execution environment
                          (Only supported on QEMU Windows VMs)

    Returns:
        Version string if package is installed (e.g., "0.1.0")
        None if package not installed or check fails

    Example:
        >>> await check_installed_version("adarevm", vm, True, "linux", stop_event, wheels_available=True)
        "0.1.0"
    """
    # Build platform-specific command
    if platform == 'windows':
        if use_conda:
            cmd = f'C:\\Users\\adare\\.miniforge3\\envs\\pyadare\\Scripts\\python.exe -m pip show {package_name}'
        else:
            # Wheels: pip is in PATH; Editable: needs uv context
            cmd = f'pip show {package_name}' if wheels_available else f'uv run pip show {package_name}'
    else:  # linux
        if use_conda:
            cmd = f'/home/adare/.miniforge3/envs/pyadare/bin/python -m pip show {package_name}'
        else:
            # Wheels: pip3 is in PATH; Editable: needs uv context
            cmd = f'pip3 show {package_name}' if wheels_available else f'uv run pip show {package_name}'

    try:
        # Prepare run_command kwargs
        run_kwargs = {}

        # Safely pass inject_user_path only to QEMU VMs which support it
        # We use a local import to avoid circular dependencies and proper type checking
        if inject_user_path and platform == 'windows':
            try:
                from adare.hypervisor.qemu.vm import QEMUVM

                if isinstance(vm, QEMUVM):
                    run_kwargs['inject_user_path'] = True
                    log.debug(f"Checking {package_name} version with inject_user_path=True")
            except ImportError:
                # If QEMUVM cannot be imported (e.g. not using QEMU), skip this check
                pass

        # Execute command silently (avoid cluttering logs with routine checks)
        result = await vm.run_command(cmd, stop_event=stop_event, **run_kwargs)

        if result.returncode != 0:
            log.debug(f"Package {package_name} not installed (pip show returned {result.returncode})")
            return None

        # Parse version from pip show output
        # Expected format:
        # Name: adarevm
        # Version: 0.1.0
        # ...
        for line in result.stdout.split('\n'):
            if line.startswith('Version:'):
                version = line.split(':', 1)[1].strip()
                log.debug(f"Found installed {package_name} version: {version}")
                return version

        log.debug(f"Could not parse version from pip show output for {package_name}")
        return None

    except (OSError, TimeoutError, RuntimeError, ValueError) as e:
        log.debug(f"Error checking {package_name} version: {e}")
        return None


async def should_skip_installation(
    wheels_dir: Path,
    vm,  # VirtualBoxVM instance
    use_conda: bool,
    platform: str,
    stop_event: threading.Event,
) -> bool:
    """Determine if agent installation can be skipped.

    Wheels carry a content-hash version (see ``agent_wheels``), so a guest is up
    to date only if each package's installed version equals the version of its
    own wheel. Guests installed before content hashing report a plain version
    (``0.1.1``) and therefore reinstall once.

    Args:
        wheels_dir: Path to wheels directory
        vm: VM instance for version checking
        use_conda: True if using Conda environment
        platform: Guest OS platform ("windows" or "linux")
        stop_event: Threading event for cancellation

    Returns:
        True if installation can be safely skipped
        False if installation must be performed
    """
    expected = wheel_versions(wheels_dir)
    missing = [pkg for pkg in AGENT_PACKAGES if pkg not in expected]
    if missing:
        log.debug(f"No wheel for {', '.join(missing)}, cannot verify version - must install")
        return False

    log.info(f"Checking for preinstalled agent (expected: {expected})...")

    # Windows QEMU: adarevm may live in a user-local path that is not on the
    # system PATH, so try with the user's PATH injected first.
    vm_is_qemu = False
    try:
        from adare.hypervisor.qemu.vm import QEMUVM

        vm_is_qemu = isinstance(vm, QEMUVM)
    except ImportError:
        pass

    for pkg in AGENT_PACKAGES:
        installed = None
        if platform == 'windows' and vm_is_qemu:
            installed = await check_installed_version(
                pkg, vm, use_conda, platform, stop_event, wheels_available=True, inject_user_path=True
            )
        if installed is None:
            installed = await check_installed_version(pkg, vm, use_conda, platform, stop_event, wheels_available=True)

        if installed is None:
            log.info(f"{pkg} not installed, will install")
            return False
        if installed != expected[pkg]:
            log.info(f"Version mismatch - {pkg} installed: {installed}, expected: {expected[pkg]}, will reinstall")
            return False

    log.info(f"✓ Agent already installed with current versions {expected}, skipping installation")
    return True

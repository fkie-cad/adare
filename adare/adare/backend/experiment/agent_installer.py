"""
AdareVM Agent Installation Module

Handles version detection and intelligent installation of adarevm and adarelib packages
in guest VMs. Optimizes experiment runs by skipping installation when correct versions
are already present.
"""

from pathlib import Path
from typing import Optional
import threading
import logging
import re

log = logging.getLogger(__name__)


def get_expected_version_from_wheels(wheels_dir: Path) -> Optional[str]:
    """Extract expected version from adarevm wheel filename.

    Parses the version number from wheel files in the format:
    adarevm-X.Y.Z-py3-none-any.whl

    Args:
        wheels_dir: Path to directory containing wheel files

    Returns:
        Version string (e.g., "0.1.0") if found, None otherwise

    Example:
        >>> get_expected_version_from_wheels(Path("/project/vm_runtime/wheels"))
        "0.1.0"
    """
    if not wheels_dir.exists():
        log.debug(f"Wheels directory does not exist: {wheels_dir}")
        return None

    adarevm_wheels = list(wheels_dir.glob('adarevm-*.whl'))
    if not adarevm_wheels:
        log.debug(f"No adarevm wheels found in {wheels_dir}")
        return None

    # Parse version from filename: adarevm-0.1.0-py3-none-any.whl
    match = re.match(r'adarevm-(\d+\.\d+\.\d+)', adarevm_wheels[0].name)
    if match:
        version = match.group(1)
        log.debug(f"Expected version from wheel: {version}")
        return version

    log.warning(f"Could not parse version from wheel filename: {adarevm_wheels[0].name}")
    return None


async def check_installed_version(
    package_name: str,
    vm,  # VirtualBoxVM instance
    use_conda: bool,
    platform: str,
    stop_event: threading.Event,
    wheels_available: bool = False,
    inject_user_path: bool = False
) -> Optional[str]:
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
            cmd = f'C:\\Users\\adare\\.miniforge3\\Scripts\\conda.exe run -n pyadare pip show {package_name}'
        else:
            if wheels_available:
                # Wheels: pip is in PATH
                cmd = f'pip show {package_name}'
            else:
                # Editable: needs uv context
                cmd = f'uv run pip show {package_name}'
    else:  # linux
        if use_conda:
            cmd = f'/home/adare/.miniforge3/bin/conda run -n pyadare pip show {package_name}'
        else:
            if wheels_available:
                # Wheels: pip3 is in PATH
                cmd = f'pip3 show {package_name}'
            else:
                # Editable: needs uv context
                cmd = f'uv run pip show {package_name}'

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

    except Exception as e:
        log.debug(f"Error checking {package_name} version: {e}")
        return None


async def should_skip_installation(
    wheels_dir: Path,
    vm,  # VirtualBoxVM instance
    use_conda: bool,
    platform: str,
    stop_event: threading.Event
) -> bool:
    """Determine if agent installation can be skipped.

    Checks if both adarevm and adarelib are installed with the expected versions.
    Returns True only if both packages are present with matching versions.

    Decision logic:
    1. If wheels not available → cannot verify, must install
    2. If expected version cannot be determined → must install
    3. If either package not installed → must install
    4. If versions don't match expected → must reinstall
    5. If both packages match expected version → can skip

    Args:
        wheels_dir: Path to wheels directory
        vm: VirtualBoxVM instance for version checking
        use_conda: True if using Conda environment
        platform: Guest OS platform ("windows" or "linux")
        stop_event: Threading event for cancellation

    Returns:
        True if installation can be safely skipped
        False if installation must be performed

    Example:
        >>> await should_skip_installation(Path("/wheels"), vm, True, "linux", event)
        True  # Agent already installed with correct version
    """
    # Check if wheels are available
    if not wheels_dir.exists() or not list(wheels_dir.glob('*.whl')):
        log.debug("No wheels available, cannot verify version - must install")
        return False

    # Get expected version from wheels
    expected_version = get_expected_version_from_wheels(wheels_dir)
    if not expected_version:
        log.debug("Could not determine expected version, cannot skip installation")
        return False

    log.info(f"Checking for preinstalled agent (expected version: {expected_version})...")

    # Check installed versions of both packages
    # Pass wheels_available=True since this function already verified wheels exist (line 155)
    
    # Special case for Windows QEMU: Try to check adarevm with inject_user_path
    # This helps find adarevm when it's in a user-local path not in system PATH
    vm_is_qemu = False
    try:
        from adare.hypervisor.qemu.vm import QEMUVM
        vm_is_qemu = isinstance(vm, QEMUVM)
    except ImportError:
        pass
    
    adarevm_version = None
    if platform == 'windows' and vm_is_qemu:
        log.debug("Using injected user PATH to check adarevm version on Windows QEMU")
        adarevm_version = await check_installed_version(
            'adarevm', vm, use_conda, platform, stop_event, 
            wheels_available=True, inject_user_path=True
        )
        adarelib_version = await check_installed_version(
            'adarelib', vm, use_conda, platform, stop_event, 
            wheels_available=True, inject_user_path=True
        )
        
    # Standard check (fallback or non-Windows-QEMU)
    if adarevm_version is None:
        adarevm_version = await check_installed_version('adarevm', vm, use_conda, platform, stop_event, wheels_available=True)
    if adarelib_version is None:
        adarelib_version = await check_installed_version('adarelib', vm, use_conda, platform, stop_event, wheels_available=True)

    # Log findings for debugging
    log.debug(f"Installed versions - adarevm: {adarevm_version}, adarelib: {adarelib_version}")

    # Decision logic with clear logging
    if adarevm_version is None:
        log.info("adarevm not installed, will install")
        return False

    if adarelib_version is None:
        log.info("adarelib not installed (partial installation detected), will reinstall both")
        return False

    if adarevm_version != expected_version:
        log.info(f"Version mismatch - adarevm installed: {adarevm_version}, expected: {expected_version}, will reinstall")
        return False

    if adarelib_version != expected_version:
        log.info(f"Version mismatch - adarelib installed: {adarelib_version}, expected: {expected_version}, will reinstall")
        return False

    # Both packages installed with correct versions - can skip!
    log.info(f"✓ Agent already installed with correct version {expected_version}, skipping installation")
    log.info("PERFORMANCE: Saved ~10-30s by skipping agent installation")
    return True

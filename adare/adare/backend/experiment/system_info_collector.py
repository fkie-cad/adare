"""
System information collection for experiment runs.

Collects OS information and installed software/packages from guest VMs
using either WebSocket (agent mode) or QGA guest-exec (host mode).
Saves the data to system-info.yml in the run directory.
"""

import logging
import time
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


def _save_system_info(system_info: dict, output_file: Path) -> None:
    """Save system info dict to YAML file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(system_info, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    log.info(f"System info saved to {output_file}")


async def collect_system_info(websocket_client, guest_platform: str, output_file: Path) -> bool:
    """
    Collect system information from the guest VM using dedicated WebSocket command.

    Args:
        websocket_client: WebSocket client for communicating with guest VM
        guest_platform: Platform type ('windows' or 'linux') - used for logging only
        output_file: Path where to save the system-info.yml file

    Returns:
        bool: True if collection was successful, False otherwise
    """
    log.info(f"Starting system info collection for {guest_platform}")

    try:
        result = await websocket_client.collect_system_info(timeout=120.0)

        if result.get('status') == 'success':
            system_info = result.get('system_info', {})
            collection_time = result.get('collection_time', 0)

            log.info(f"System info collected successfully in {collection_time:.2f} seconds")
            _save_system_info(system_info, output_file)

            os_name = system_info.get('os_info', {}).get('name', 'Unknown')
            package_count = len(system_info.get('installed_packages', []))
            log.info(f"Collection summary - OS: {os_name}, Packages: {package_count}")

            return True

        error_msg = result.get('message', 'Unknown error')
        log.warning(f"System info collection failed: {error_msg}")
        return False

    except (OSError, ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
        log.warning(f"System info collection failed with exception: {e}", exc_info=True)
        return False


async def collect_system_info_via_qga(vm, guest_platform: str, output_file: Path) -> bool:
    """
    Collect system information from the guest VM via QGA guest-exec commands.

    Used in host mode when no WebSocket agent is available.

    Args:
        vm: QEMU VM instance with run_command() support
        guest_platform: Platform type ('windows' or 'linux')
        output_file: Path where to save the system-info.yml file

    Returns:
        bool: True if collection was successful, False otherwise
    """
    log.info(f"Starting QGA-based system info collection for {guest_platform}")
    start_time = time.time()

    system_info = {
        'collection_method': 'qga',
    }

    is_windows = 'windows' in guest_platform.lower()

    try:
        if is_windows:
            system_info['os_info'] = await _collect_windows_os_info(vm)
            system_info['installed_packages'] = await _collect_windows_packages(vm)
        else:
            system_info['os_info'] = await _collect_linux_os_info(vm)
            system_info['installed_packages'] = await _collect_linux_packages(vm)

        collection_time = time.time() - start_time
        log.info(f"QGA system info collected in {collection_time:.2f} seconds")

        _save_system_info(system_info, output_file)

        os_name = system_info.get('os_info', {}).get('name', 'Unknown')
        package_count = len(system_info.get('installed_packages', []))
        log.info(f"QGA collection summary - OS: {os_name}, Packages: {package_count}")

        return True

    except (OSError, ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
        log.warning(f"QGA system info collection failed: {e}", exc_info=True)
        return False


async def _collect_linux_os_info(vm) -> dict:
    """Collect Linux OS information via QGA."""
    os_info = {}

    # uname -a
    result = await vm.run_command("uname -a", silent=True)
    if result.returncode == 0:
        os_info['uname'] = result.stdout.strip()

    # /etc/os-release
    result = await vm.run_command("cat /etc/os-release 2>/dev/null || true", silent=True)
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, _, value = line.partition('=')
                value = value.strip('"').strip("'")
                key = key.strip().lower()
                if key == 'pretty_name':
                    os_info['name'] = value
                elif key == 'version_id':
                    os_info['version'] = value
                elif key == 'id':
                    os_info['id'] = value

    # Hostname
    result = await vm.run_command("hostname", silent=True)
    if result.returncode == 0:
        os_info['hostname'] = result.stdout.strip()

    # Kernel version
    result = await vm.run_command("uname -r", silent=True)
    if result.returncode == 0:
        os_info['kernel'] = result.stdout.strip()

    return os_info


async def _collect_linux_packages(vm) -> list:
    """Collect installed packages on Linux via QGA."""
    packages = []

    # Try dpkg first (Debian/Ubuntu)
    result = await vm.run_command(
        "dpkg-query -W -f='${Package} ${Version}\\n' 2>/dev/null | head -500",
        silent=True
    )
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split(' ', 1)
            if len(parts) == 2:
                packages.append({'name': parts[0], 'version': parts[1]})
            elif parts[0]:
                packages.append({'name': parts[0]})
        return packages

    # Try rpm (RHEL/Fedora/SUSE)
    result = await vm.run_command(
        "rpm -qa --queryformat '%{NAME} %{VERSION}-%{RELEASE}\\n' 2>/dev/null | head -500",
        silent=True
    )
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split(' ', 1)
            if len(parts) == 2:
                packages.append({'name': parts[0], 'version': parts[1]})
            elif parts[0]:
                packages.append({'name': parts[0]})

    return packages


async def _collect_windows_os_info(vm) -> dict:
    """Collect Windows OS information via QGA."""
    os_info = {}

    result = await vm.run_command(
        '(Get-CimInstance Win32_OperatingSystem).Caption; '
        '(Get-CimInstance Win32_OperatingSystem).Version; '
        '(Get-CimInstance Win32_OperatingSystem).BuildNumber; '
        '$env:COMPUTERNAME',
        silent=True
    )
    if result.returncode == 0 and result.stdout.strip():
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 1:
            os_info['name'] = lines[0].strip()
        if len(lines) >= 2:
            os_info['version'] = lines[1].strip()
        if len(lines) >= 3:
            os_info['build'] = lines[2].strip()
        if len(lines) >= 4:
            os_info['hostname'] = lines[3].strip()

    return os_info


async def _collect_windows_packages(vm) -> list:
    """Collect installed software on Windows via QGA."""
    packages = []

    result = await vm.run_command(
        'Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* '
        '| Where-Object { $_.DisplayName } '
        '| Select-Object -First 500 DisplayName, DisplayVersion '
        '| ForEach-Object { "$($_.DisplayName)|$($_.DisplayVersion)" }',
        silent=True
    )
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split('|', 1)
            if len(parts) == 2:
                packages.append({'name': parts[0], 'version': parts[1]})
            elif parts[0]:
                packages.append({'name': parts[0]})

    return packages

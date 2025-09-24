"""
System information collection for experiment runs.

Collects OS information and installed software/packages from guest VMs
using a dedicated WebSocket command and saves the data to system-info.yml in the run directory.
"""

from pathlib import Path
import yaml

import logging
log = logging.getLogger(__name__)


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
    log.info(f"CLAUDE: Starting system info collection for {guest_platform}")

    try:
        # Use the new dedicated WebSocket command
        result = await websocket_client.collect_system_info(timeout=120.0)

        if result.get('status') == 'success':
            system_info = result.get('system_info', {})
            collection_time = result.get('collection_time', 0)

            log.info(f"CLAUDE: System info collected successfully in {collection_time:.2f} seconds")

            # Save to YAML file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(system_info, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

            log.info(f"CLAUDE: System info saved to {output_file}")

            # Log summary for debugging
            os_name = system_info.get('os_info', {}).get('name', 'Unknown')
            package_count = len(system_info.get('installed_packages', []))
            log.info(f"CLAUDE: Collection summary - OS: {os_name}, Packages: {package_count}")

            return True

        else:
            # Command failed
            error_msg = result.get('message', 'Unknown error')
            log.warning(f"CLAUDE: System info collection failed: {error_msg}")
            return False

    except Exception as e:
        log.warning(f"CLAUDE: System info collection failed with exception: {e}", exc_info=True)
        return False
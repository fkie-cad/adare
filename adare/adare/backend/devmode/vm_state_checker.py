"""
VM state checking utilities for dev mode.

This module provides centralized VM state checking across different hypervisors
to validate whether VMs are actually running before attempting session restoration.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


def is_vm_running(vm_name: str, hypervisor_type: str) -> bool:
    """
    Check if a VM is actually running via hypervisor API.

    Args:
        vm_name: Name of the VM to check
        hypervisor_type: Type of hypervisor ('qemu' or 'virtualbox')

    Returns:
        True if VM is running, False otherwise
    """
    try:
        if hypervisor_type == 'qemu':
            return _check_qemu_vm(vm_name)
        elif hypervisor_type == 'virtualbox':
            return _check_virtualbox_vm(vm_name)
        else:
            log.warning(f"Unknown hypervisor type: {hypervisor_type}")
            return False
    except Exception as e:
        log.error(f"Error checking VM state for {vm_name}: {e}", exc_info=True)
        return False


def _check_qemu_vm(vm_name: str) -> bool:
    """
    Check if a QEMU/libvirt VM is running.

    Uses libvirt lookupByName() to check if domain exists and is active.
    Follows the established codebase pattern for libvirt integration.

    Args:
        vm_name: Name of the VM domain

    Returns:
        True if VM is running, False otherwise
    """
    try:
        import libvirt  # Import inside try block (codebase pattern)
        from adare.config import HYPERVISOR_CONFIGS
        from adare.hypervisor.qemu.libvirt_stderr_redirect import (
            LibvirtStderrRedirect,
            get_experiment_log_file
        )

        # Get libvirt connection using config pattern (not temp VM)
        qemu_config = HYPERVISOR_CONFIGS.get('qemu', {})
        libvirt_uri = qemu_config.get('libvirt_uri', 'qemu:///session')

        conn = libvirt.open(libvirt_uri)
        if not conn:
            log.debug(f"CLAUDE: Could not open libvirt connection for {vm_name}")
            return False

        log_file = get_experiment_log_file()

        try:
            # Try to lookup domain by name with stderr redirect
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                domain = conn.lookupByName(vm_name)

            # Check if domain is active (running)
            is_active = domain.isActive()

            if is_active:
                log.debug(f"CLAUDE: QEMU VM '{vm_name}' is running")
            else:
                log.debug(f"CLAUDE: QEMU VM '{vm_name}' exists but is not running")

            conn.close()  # Clean up connection
            return is_active

        except libvirt.libvirtError as e:
            # Domain not found or other libvirt error
            log.debug(f"CLAUDE: QEMU VM '{vm_name}' not found: {e}")
            conn.close()
            return False

    except ImportError:
        log.error("CLAUDE: libvirt-python not installed. Install with: pip install libvirt-python")
        return False
    except Exception as e:
        log.error(f"CLAUDE: Error checking QEMU VM state: {e}", exc_info=True)
        return False


def _check_virtualbox_vm(vm_name: str) -> bool:
    """
    Check if a VirtualBox VM is running.

    Uses VirtualBox API to check VM state.

    Args:
        vm_name: Name of the VM

    Returns:
        True if VM is running, False otherwise
    """
    try:
        import virtualbox

        vbox = virtualbox.VirtualBox()

        try:
            # Find machine by name
            machine = vbox.find_machine(vm_name)

            # Check state
            state = machine.state

            # VirtualBox states: Running, Paused, PoweredOff, Saved, etc.
            # We consider "Running" and "Paused" as "running" for restoration purposes
            if state == virtualbox.library.MachineState.running:
                log.debug(f"VirtualBox VM '{vm_name}' is running")
                return True
            elif state == virtualbox.library.MachineState.paused:
                log.debug(f"VirtualBox VM '{vm_name}' is paused (considered running)")
                return True
            else:
                log.debug(f"VirtualBox VM '{vm_name}' is in state: {state}")
                return False

        except Exception as e:
            log.debug(f"VirtualBox VM '{vm_name}' not found or error: {e}")
            return False

    except ImportError:
        log.error("virtualbox module not available")
        return False
    except Exception as e:
        log.error(f"Error checking VirtualBox VM state: {e}", exc_info=True)
        return False

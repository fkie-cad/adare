"""
Simple database-driven port allocation for VM instances.

Eliminates in-memory state synchronization issues by using the database
as the single source of truth for port allocations.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Port range for websocket allocation
PORT_RANGE_START = 18765
PORT_RANGE_END = 18799


def find_available_port() -> Optional[int]:
    """
    Find the next available websocket port by querying the database.

    Returns:
        Available port number, or None if no ports available
    """
    try:
        # Import here to avoid circular imports
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            # Get all active VM instances with allocated ports
            active_instances = api.get_all_vm_instances()
            used_ports = set()

            for instance in active_instances:
                # Only consider active instances with allocated ports in our range
                if (instance.status == 'active' and
                    instance.websocket_port is not None and
                    PORT_RANGE_START <= instance.websocket_port <= PORT_RANGE_END):
                    used_ports.add(instance.websocket_port)

            # Find first available port
            for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
                if port not in used_ports:
                    log.info(f"Found available websocket port: {port}")
                    return port

            log.error(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")
            return None

    except Exception as e:
        log.error(f"Error finding available port: {e}")
        return None


def reserve_port_atomically(api_session, vm_id: str, instance_name: str, experiment_run_id: str) -> Optional[int]:
    """
    Atomically reserve a websocket port within an existing database transaction.

    This function must be called within an active VmApi session/transaction to ensure
    atomicity. It finds an available port and immediately creates a VmInstance record
    to reserve it, preventing race conditions.

    Args:
        api_session: Active VmApi session with transaction
        vm_id: Source VM ID
        instance_name: Unique name for the VM instance
        experiment_run_id: Experiment run ID

    Returns:
        Reserved port number, or None if no ports available

    Raises:
        ValueError: If port conflicts are detected during reservation
    """
    try:
        # Get all currently allocated ports within this transaction
        active_instances = api_session.get_all_vm_instances()
        used_ports = set()

        for instance in active_instances:
            if (instance.status == 'active' and
                instance.websocket_port is not None and
                PORT_RANGE_START <= instance.websocket_port <= PORT_RANGE_END):
                used_ports.add(instance.websocket_port)

        # Find first available port
        for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            if port not in used_ports:
                log.debug(f"Attempting to reserve port {port} for instance {instance_name}")

                # Immediately create VmInstance record to reserve the port atomically
                try:
                    instance = api_session.create_vm_instance(
                        vm_id=vm_id,
                        instance_name=instance_name,
                        experiment_run_id=experiment_run_id,
                        websocket_port=port,
                        status='active'
                    )

                    log.info(f"Successfully reserved port {port} for instance {instance_name}")
                    return port

                except Exception as db_error:
                    # If database constraint fails (e.g., duplicate port), try next port
                    log.debug(f"Port {port} reservation failed, trying next port: {db_error}")
                    continue

        log.error(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")
        return None

    except Exception as e:
        log.error(f"Error during atomic port reservation: {e}")
        # If there was an error, clean up any orphaned allocations and retry once
        log.info("Attempting to clean up orphaned ports and retry allocation...")
        cleaned = cleanup_orphaned_ports()
        if cleaned > 0:
            log.info(f"Cleaned up {cleaned} orphaned ports, retrying allocation...")
            # Retry once after cleanup
            try:
                return _retry_port_reservation(api_session, vm_id, instance_name, experiment_run_id)
            except Exception as retry_error:
                log.error(f"Retry after cleanup also failed: {retry_error}")
        return None


def _retry_port_reservation(api_session, vm_id: str, instance_name: str, experiment_run_id: str) -> Optional[int]:
    """
    Helper function to retry port reservation after cleanup.

    This is separated to avoid infinite recursion.
    """
    try:
        # Get all currently allocated ports within this transaction
        active_instances = api_session.get_all_vm_instances()
        used_ports = set()

        for instance in active_instances:
            if (instance.status == 'active' and
                instance.websocket_port is not None and
                PORT_RANGE_START <= instance.websocket_port <= PORT_RANGE_END):
                used_ports.add(instance.websocket_port)

        # Find first available port
        for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            if port not in used_ports:
                log.debug(f"Retry: Attempting to reserve port {port} for instance {instance_name}")

                # Create VmInstance record to reserve the port atomically
                try:
                    instance = api_session.create_vm_instance(
                        vm_id=vm_id,
                        instance_name=instance_name,
                        experiment_run_id=experiment_run_id,
                        websocket_port=port,
                        status='active'
                    )

                    log.info(f"Retry successful: Reserved port {port} for instance {instance_name}")
                    return port

                except Exception as db_error:
                    # If still failing, give up
                    log.debug(f"Retry: Port {port} reservation still failed: {db_error}")
                    continue

        log.error("Retry: Still no available ports after cleanup")
        return None

    except Exception as e:
        log.error(f"Error during port reservation retry: {e}")
        return None


def is_port_available(port: int) -> bool:
    """
    Check if a specific port is available by querying the database.

    Args:
        port: Port number to check

    Returns:
        True if port is available, False if in use or on error
    """
    if not (PORT_RANGE_START <= port <= PORT_RANGE_END):
        return False

    try:
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            active_instances = api.get_all_vm_instances()

            for instance in active_instances:
                if (instance.status == 'active' and
                    instance.websocket_port == port):
                    return False

            return True

    except Exception as e:
        log.error(f"Error checking port availability: {e}")
        return False


def get_port_usage_stats() -> dict:
    """
    Get statistics about port usage from the database.

    Returns:
        Dictionary with port usage information
    """
    try:
        from adare.database.api.vm import VmApi

        with VmApi() as api:
            active_instances = api.get_all_vm_instances()
            allocated_ports = []

            for instance in active_instances:
                if (instance.status == 'active' and
                    instance.websocket_port is not None and
                    PORT_RANGE_START <= instance.websocket_port <= PORT_RANGE_END):
                    allocated_ports.append(instance.websocket_port)

            total_ports = PORT_RANGE_END - PORT_RANGE_START + 1
            allocated_count = len(allocated_ports)

            return {
                'total_ports': total_ports,
                'allocated_ports': sorted(allocated_ports),
                'allocated_count': allocated_count,
                'available_count': total_ports - allocated_count,
                'port_range': f"{PORT_RANGE_START}-{PORT_RANGE_END}"
            }

    except Exception as e:
        log.error(f"Error getting port usage stats: {e}")
        return {
            'total_ports': 0,
            'allocated_ports': [],
            'allocated_count': 0,
            'available_count': 0,
            'port_range': f"{PORT_RANGE_START}-{PORT_RANGE_END}",
            'error': str(e)
        }


# Backward compatibility functions (now just call the simple database functions)
def allocate_websocket_port() -> Optional[int]:
    """
    Allocate a websocket port for a new experiment.

    DEPRECATED: This function is deprecated and only finds a port without reserving it.
    Use reserve_port_atomically() within a database transaction instead to prevent
    race conditions.

    Returns:
        Available port number, or None if no ports available
    """
    log.warning("allocate_websocket_port() is deprecated. Use reserve_port_atomically() instead.")
    return find_available_port()


def deallocate_websocket_port(port: int) -> bool:
    """
    Release a websocket port when experiment completes.

    Note: Port deallocation now happens automatically when VmInstance
    status changes from 'active' to 'available' or when deleted.

    Args:
        port: Port number to release (ignored)

    Returns:
        True (for backward compatibility)
    """
    log.debug(f"Port {port} deallocation handled by database cleanup")
    return True


def is_websocket_port_allocated(port: int) -> bool:
    """
    Check if a websocket port is currently in use.

    Args:
        port: Port number to check

    Returns:
        True if port is allocated
    """
    return not is_port_available(port)


def cleanup_orphaned_ports() -> int:
    """
    Clean up orphaned port allocations where VmInstance has websocket_port
    but status is not 'active'.

    Returns:
        Number of orphaned ports cleaned up
    """
    try:
        from adare.database.api.vm import VmApi

        cleaned_count = 0
        with VmApi() as api:
            all_instances = api.get_all_vm_instances()

            for instance in all_instances:
                # Clean up instances that have ports but are not active
                if (instance.websocket_port is not None and
                    instance.status != 'active' and
                    PORT_RANGE_START <= instance.websocket_port <= PORT_RANGE_END):

                    log.info(f"Cleaning up orphaned port {instance.websocket_port} from instance {instance.instance_name} (status: {instance.status})")

                    # Clear the port from non-active instances
                    instance.websocket_port = None
                    api.session.commit()
                    cleaned_count += 1

            if cleaned_count > 0:
                log.info(f"Cleaned up {cleaned_count} orphaned port allocations")
            else:
                log.debug("No orphaned port allocations found")

            return cleaned_count

    except Exception as e:
        log.error(f"Error cleaning up orphaned ports: {e}")
        return 0


def detect_port_conflicts() -> dict:
    """
    Detect and report port conflicts where multiple active instances
    have the same websocket_port.

    Returns:
        Dictionary with conflict information
    """
    try:
        from adare.database.api.vm import VmApi
        from collections import defaultdict

        conflicts = defaultdict(list)
        with VmApi() as api:
            active_instances = api.get_all_vm_instances()

            # Group by port for active instances
            port_instances = defaultdict(list)
            for instance in active_instances:
                if (instance.status == 'active' and
                    instance.websocket_port is not None and
                    PORT_RANGE_START <= instance.websocket_port <= PORT_RANGE_END):
                    port_instances[instance.websocket_port].append(instance)

            # Find conflicts (ports used by multiple active instances)
            for port, instances in port_instances.items():
                if len(instances) > 1:
                    conflicts[port] = [{
                        'id': inst.id,
                        'name': inst.instance_name,
                        'experiment_id': inst.current_experiment_run_id,
                        'created_at': inst.created_at.isoformat() if inst.created_at else None
                    } for inst in instances]

            result = {
                'conflicts_found': len(conflicts) > 0,
                'conflict_count': len(conflicts),
                'conflicted_ports': dict(conflicts)
            }

            if conflicts:
                log.warning(f"Found {len(conflicts)} port conflicts involving {sum(len(instances) for instances in conflicts.values())} instances")
                for port, instances in conflicts.items():
                    log.warning(f"Port {port} is used by {len(instances)} active instances: {[i['name'] for i in instances]}")
            else:
                log.debug("No port conflicts detected")

            return result

    except Exception as e:
        log.error(f"Error detecting port conflicts: {e}")
        return {'conflicts_found': False, 'error': str(e)}


def reset_all_port_allocations():
    """
    Reset all port allocations by cleaning up orphaned ports and detecting conflicts.

    This function now performs active cleanup instead of being a no-op.
    """
    log.info("Performing port allocation cleanup...")

    # Clean up orphaned ports
    cleaned = cleanup_orphaned_ports()

    # Detect remaining conflicts
    conflicts = detect_port_conflicts()

    if conflicts['conflicts_found']:
        log.warning(f"After cleanup, {conflicts['conflict_count']} port conflicts remain and need manual resolution")
    else:
        log.info("Port allocation cleanup completed successfully")

    return {
        'orphaned_cleaned': cleaned,
        'conflicts': conflicts
    }
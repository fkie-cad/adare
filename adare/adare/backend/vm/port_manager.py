"""
Simple database-driven port allocation for VM instances.

Eliminates in-memory state synchronization issues by using the database
as the single source of truth for port allocations.

Uses Unit of Work pattern for atomic port reservation within database transactions.
"""

import logging
from typing import Optional
from sqlalchemy.exc import IntegrityError, OperationalError

from adare.hypervisor.exceptions import PortAllocationException

log = logging.getLogger(__name__)

# Port range for websocket allocation
PORT_RANGE_START = 18765
PORT_RANGE_END = 18799


def find_available_port() -> Optional[int]:
    """
    Find the next available websocket port by querying the database.

    Returns:
        Available port number, or None if no ports available

    Raises:
        PortAllocationException: If database query fails
    """
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


def reserve_port_atomically(api_session, vm_id: str, instance_name: str, experiment_run_id: str) -> Optional[int]:
    """
    Atomically reserve a websocket port within an existing database transaction.

    This function implements the Unit of Work pattern: it finds an available port
    and immediately creates a VmInstance record to reserve it, all within the same
    database transaction to prevent race conditions.

    Args:
        api_session: Active VmApi session with transaction
        vm_id: Source VM ID
        instance_name: Unique name for the VM instance
        experiment_run_id: Experiment run ID

    Returns:
        Reserved port number, or None if no ports available

    Raises:
        PortAllocationException: If port reservation fails due to database errors
    """
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

            except IntegrityError as db_error:
                # If database constraint fails (e.g., duplicate port or instance name), try next port
                log.debug(f"Port {port} reservation failed due to constraint violation, trying next port: {db_error}")
                api_session.session.rollback()  # Rollback the failed insert
                continue
            except OperationalError as db_error:
                # Database operational error (connection, timeout, etc.)
                log.error(f"Database operational error during port reservation: {db_error}")
                raise PortAllocationException(
                    f"Database error during port reservation: {db_error}",
                    port_range=(PORT_RANGE_START, PORT_RANGE_END)
                )

    log.error(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")
    return None


def is_port_available(port: int) -> bool:
    """
    Check if a specific port is available by querying the database.

    Args:
        port: Port number to check

    Returns:
        True if port is available, False if in use

    Raises:
        PortAllocationException: If database query fails
    """
    if not (PORT_RANGE_START <= port <= PORT_RANGE_END):
        return False

    from adare.database.api.vm import VmApi

    with VmApi() as api:
        active_instances = api.get_all_vm_instances()

        for instance in active_instances:
            if (instance.status == 'active' and
                instance.websocket_port == port):
                return False

        return True


def get_port_usage_stats() -> dict:
    """
    Get statistics about port usage from the database.

    Returns:
        Dictionary with port usage information

    Raises:
        OperationalError: If database connection fails
    """
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

    Raises:
        OperationalError: If database operation fails
    """
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


def detect_port_conflicts() -> dict:
    """
    Detect and report port conflicts where multiple active instances
    have the same websocket_port.

    Returns:
        Dictionary with conflict information

    Raises:
        OperationalError: If database query fails
    """
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
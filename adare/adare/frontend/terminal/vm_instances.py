"""
Terminal frontend for VM instance management.

Provides terminal output formatting for VM instance information,
statistics, and management operations.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from adare.backend.vm.instance_manager import get_vm_instance_stats
from adare.backend.vm.port_manager import get_port_usage_stats
from adare.database.api.vm import VmApi

log = logging.getLogger(__name__)


def print_vm_instances_list():
    """Print a list of all VM instances in the system."""
    try:
        with VmApi() as api:
            instances = api.get_all_vm_instances()

        if not instances:
            print("No VM instances found.")
            return

        print("VM INSTANCES")
        print("=" * 80)
        print(f"{'ID':<26} {'Name':<20} {'Status':<12} {'Port':<6} {'Last Used':<20}")
        print("-" * 80)

        for instance in instances:
            last_used = instance.last_used_at.strftime("%Y-%m-%d %H:%M:%S") if instance.last_used_at else "Never"
            port = str(instance.websocket_port) if instance.websocket_port else "N/A"
            print(f"{instance.id:<26} {instance.instance_name:<20} {instance.status:<12} {port:<6} {last_used:<20}")

        print(f"\nTotal instances: {len(instances)}")

    except Exception as e:
        log.error(f"Error listing VM instances: {e}")
        print(f"Error: {e}")


def print_vm_instance_info(instance_id: str):
    """Print detailed information about a specific VM instance."""
    try:
        with VmApi() as api:
            instance = api.get_vm_instance_by_id(instance_id)

        if not instance:
            print(f"VM instance with ID '{instance_id}' not found.")
            return

        print("VM INSTANCE DETAILS")
        print("=" * 60)
        print(f"ID:                    {instance.id}")
        print(f"Name:                  {instance.instance_name}")
        print(f"Status:                {instance.status}")
        print(f"Source VM ID:          {instance.vm_id}")
        print(f"VirtualBox UUID:       {instance.vbox_uuid or 'Not assigned'}")
        print(f"Websocket Port:        {instance.websocket_port or 'Not assigned'}")
        print(f"Current Experiment:    {instance.current_experiment_run_id or 'None'}")
        print(f"Base Snapshot:         {instance.base_snapshot_name or 'Not set'}")
        print(f"Created:               {instance.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Last Used:             {instance.last_used_at.strftime('%Y-%m-%d %H:%M:%S')}")

        # Show source VM info
        source_vm = api.get_vm_by_id(instance.vm_id)
        if source_vm:
            print(f"\nSource VM Information:")
            print(f"  Name:                {source_vm.name}")
            print(f"  Description:         {source_vm.description or 'None'}")
            print(f"  File:                {source_vm.file}")

    except Exception as e:
        log.error(f"Error getting VM instance info: {e}")
        print(f"Error: {e}")


def print_vm_instance_usage():
    """Print VM instance usage statistics."""
    try:
        stats = get_vm_instance_stats()

        print("VM INSTANCE USAGE STATISTICS")
        print("=" * 60)
        print(f"Total Instances:       {stats['total_instances']}")
        print(f"Active Instances:      {stats['active_instances']}")
        print(f"Available Instances:   {stats['available_instances']}")
        print(f"Cleanup Pending:       {stats['cleanup_pending_instances']}")

        if stats['instances_by_vm']:
            print("\nPer-VM Instance Breakdown:")
            print("-" * 60)
            print(f"{'VM ID':<26} {'Total':<6} {'Active':<7} {'Available':<10} {'Cleanup':<8}")
            print("-" * 60)

            for vm_id, vm_stats in stats['instances_by_vm'].items():
                print(f"{vm_id:<26} {vm_stats['total']:<6} {vm_stats['active']:<7} {vm_stats['available']:<10} {vm_stats['cleanup_pending']:<8}")

    except Exception as e:
        log.error(f"Error getting VM instance usage: {e}")
        print(f"Error: {e}")


def print_port_usage_stats():
    """Print websocket port usage statistics."""
    try:
        stats = get_port_usage_stats()

        print("WEBSOCKET PORT USAGE STATISTICS")
        print("=" * 60)
        print(f"Port Range:            {stats['port_range']}")
        print(f"Total Ports:           {stats['total_ports']}")
        print(f"Allocated Ports:       {stats['allocated_count']}")
        print(f"Available Ports:       {stats['available_count']}")

        if stats['allocated_ports']:
            print("\nAllocated Ports:")
            print("-" * 30)
            ports_per_line = 10
            allocated_ports = stats['allocated_ports']
            for i in range(0, len(allocated_ports), ports_per_line):
                port_group = allocated_ports[i:i + ports_per_line]
                print("  " + ", ".join(map(str, port_group)))

    except Exception as e:
        log.error(f"Error getting port usage stats: {e}")
        print(f"Error: {e}")


def print_vm_instance_cleanup_results(cleaned_instances: List[str], cleanup_type: str):
    """Print results of VM instance cleanup operation."""
    if not cleaned_instances:
        print(f"No instances found for cleanup ({cleanup_type}).")
        return

    print(f"VM INSTANCE CLEANUP RESULTS ({cleanup_type})")
    print("=" * 60)
    print(f"Cleaned up {len(cleaned_instances)} instance(s):")

    for instance_id in cleaned_instances:
        print(f"  ✓ {instance_id}")

    print(f"\nTotal cleaned: {len(cleaned_instances)}")


def print_vm_instance_error(message: str, details: str = None):
    """Print VM instance error message."""
    print(f"❌ Error: {message}")
    if details:
        print(f"   Details: {details}")


def print_vm_instance_success(message: str, details: str = None):
    """Print VM instance success message."""
    print(f"✅ Success: {message}")
    if details:
        print(f"   Details: {details}")
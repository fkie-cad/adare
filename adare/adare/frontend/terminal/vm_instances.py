"""
Terminal frontend for VM instance management.

Provides terminal output formatting for VM instance information,
statistics, and management operations.
"""

import logging

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from adare.backend.vm.instance_manager import get_vm_instance_stats
from adare.backend.vm.port_manager import get_port_usage_stats
from adare.database.api.vm import VmApi
from adare.frontend.terminal.console import DefaultConsole

log = logging.getLogger(__name__)


def print_vm_instances_list():
    """Print a list of all VM instances in the system."""
    try:
        with VmApi() as api:
            instances = api.get_all_vm_instances()

        if not instances:
            console = DefaultConsole()
            console.print("No VM instances found.")
            return

        # Create Rich table
        table = Table(expand=True)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="yellow", no_wrap=True)
        table.add_column("Status", style="cyan", no_wrap=True)
        table.add_column("Port", style="cyan", no_wrap=True)
        table.add_column("Last Used", style="cyan", no_wrap=False)

        for instance in instances:
            last_used = instance.last_used_at.strftime("%Y-%m-%d %H:%M:%S") if instance.last_used_at else "Never"
            port = str(instance.websocket_port) if instance.websocket_port else "N/A"
            table.add_row(
                instance.id,
                instance.instance_name,
                instance.status,
                port,
                last_used
            )

        # Display using Rich console
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = Panel(table, title="[b gold3]VM Instances[/b gold3]", border_style="blue", title_align="left")
        layout.update(panel)
        console.print(layout)
        console.print(f"\nTotal instances: {len(instances)}")

    except Exception as e:
        log.error(f"Error listing VM instances: {e}")
        print(f"Error: {e}")


def print_vm_instance_info(instance_id: str, formatter=None, output_file=None, dual_output=False):
    """Print detailed information about a specific VM instance."""
    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    try:
        with VmApi() as api:
            instance = api.get_vm_instance_by_id(instance_id)

            if not instance:
                console = DefaultConsole()
                console.print(f"VM instance with ID '{instance_id}' not found.")
                return

            # Get source VM info
            source_vm = api.get_vm_by_id(instance.vm_id)

            # Check if structured output is needed
            if dual_output or formatter.format_type.value != 'rich':
                structured_data = {
                    'type': 'instance',
                    'id': instance.id,
                    'instance_name': instance.instance_name,
                    'status': instance.status,
                    'vm_id': instance.vm_id,
                    'vbox_uuid': instance.vbox_uuid,
                    'websocket_port': instance.websocket_port,
                    'current_experiment_run_id': instance.current_experiment_run_id,
                    'base_snapshot_name': instance.base_snapshot_name,
                    'created_at': instance.created_at.isoformat(),
                    'last_used_at': instance.last_used_at.isoformat(),
                    'source_vm': {
                        'name': source_vm.name if source_vm else None,
                        'description': source_vm.description if source_vm else None,
                        'file': source_vm.file if source_vm else None
                    } if source_vm else None
                }
                formatter.print_or_save(structured_data, output_file, dual_output)

                if not dual_output:
                    return

            # Create Rich table for instance details
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value", style="yellow")

            table.add_row("ID:", instance.id)
            table.add_row("Name:", instance.instance_name)
            table.add_row("Status:", instance.status)
            table.add_row("Source VM ID:", instance.vm_id)
            table.add_row("VirtualBox UUID:", instance.vbox_uuid or 'Not assigned')
            table.add_row("Websocket Port:", str(instance.websocket_port) if instance.websocket_port else 'Not assigned')
            table.add_row("Current Experiment:", instance.current_experiment_run_id or 'None')
            table.add_row("Base Snapshot:", instance.base_snapshot_name or 'Not set')
            table.add_row("Created:", instance.created_at.strftime('%Y-%m-%d %H:%M:%S'))
            table.add_row("Last Used:", instance.last_used_at.strftime('%Y-%m-%d %H:%M:%S'))

            # Show source VM info
            if source_vm:
                table.add_row("", "")  # Empty row for spacing
                table.add_row("[b]Source VM Information[/b]", "")
                table.add_row("  Name:", source_vm.name)
                table.add_row("  Description:", source_vm.description or 'None')
                table.add_row("  File:", source_vm.file)

        # Display using Rich console
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = Panel(table, title="[b gold3]VM Instance Details[/b gold3]", border_style="blue", title_align="left")
        layout.update(panel)
        console.print(layout)

    except Exception as e:
        log.error(f"Error getting VM instance info: {e}")
        print(f"Error: {e}")


def print_vm_instance_usage(formatter=None, output_file=None, dual_output=False):
    """Print VM instance usage statistics."""
    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    try:
        stats = get_vm_instance_stats()
        console = DefaultConsole()

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            formatter.print_or_save(stats, output_file, dual_output)

            if not dual_output:
                return

        # Create summary table
        summary_table = Table(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column("Metric", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="yellow")

        summary_table.add_row("Total Instances:", str(stats['total_instances']))
        summary_table.add_row("Total Disk Usage:", f"{stats['total_disk_gb']:.2f} GB")
        summary_table.add_row("Running:", str(stats['running_instances']))
        summary_table.add_row("Stopped:", str(stats['stopped_instances']))

        # Display summary panel
        summary_panel = Panel(summary_table, title="[b gold3]VM Instance Usage Statistics[/b gold3]", border_style="blue", title_align="left")
        console.print(summary_panel)

        # Show top disk consumers if any exist
        if stats['top_disk_consumers'] and any(c['disk_gb'] > 0 for c in stats['top_disk_consumers']):
            consumers_table = Table(expand=True)
            consumers_table.add_column("Instance Name", style="cyan", no_wrap=True)
            consumers_table.add_column("Disk Usage", style="yellow", justify="right")
            consumers_table.add_column("Status", style="green", justify="center")

            for consumer in stats['top_disk_consumers']:
                if consumer['disk_gb'] > 0:  # Only show instances with actual disk usage
                    status = "🟢 Running" if consumer['is_running'] else "⚫ Stopped"
                    consumers_table.add_row(
                        consumer['name'],
                        f"{consumer['disk_gb']:.2f} GB",
                        status
                    )

            # Display consumers panel
            consumers_panel = Panel(consumers_table, title="[b gold3]Top Disk Consumers[/b gold3]", border_style="blue", title_align="left")
            console.print(consumers_panel)

    except Exception as e:
        log.error(f"Error getting VM instance usage: {e}")
        print(f"Error: {e}")


def print_port_usage_stats():
    """Print websocket port usage statistics."""
    try:
        stats = get_port_usage_stats()
        console = DefaultConsole()

        # Create summary table
        summary_table = Table(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column("Metric", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="yellow")

        summary_table.add_row("Port Range:", stats['port_range'])
        summary_table.add_row("Total Ports:", str(stats['total_ports']))
        summary_table.add_row("Allocated Ports:", str(stats['allocated_count']))
        summary_table.add_row("Available Ports:", str(stats['available_count']))

        # Display summary panel
        summary_panel = Panel(summary_table, title="[b gold3]WebSocket Port Usage Statistics[/b gold3]", border_style="blue", title_align="left")
        console.print(summary_panel)

        # Display allocated ports if any
        if stats['allocated_ports']:
            ports_per_line = 10
            allocated_ports = stats['allocated_ports']
            port_lines = []

            for i in range(0, len(allocated_ports), ports_per_line):
                port_group = allocated_ports[i:i + ports_per_line]
                port_lines.append("  " + ", ".join(map(str, port_group)))

            port_display = "\n".join(port_lines)

            # Display allocated ports panel
            ports_panel = Panel(port_display, title="[b gold3]Allocated Ports[/b gold3]", border_style="blue", title_align="left")
            console.print(ports_panel)

    except Exception as e:
        log.error(f"Error getting port usage stats: {e}")
        print(f"Error: {e}")


def print_vm_instance_cleanup_results(cleaned_instances: list[str], cleanup_type: str):
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

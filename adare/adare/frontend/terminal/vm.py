# external imports
from rich.layout import Layout
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# internal imports
from adare.backend.vm.commands import get_vm_info
from adare.frontend.terminal.console import DefaultConsole

import logging
log = logging.getLogger(__name__)


class VMInfoPanel:
    def __init__(self, vm_info: dict):
        self.vm_info = vm_info

    def __rich__(self) -> Panel:
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Property", style="cyan", width=20)
        table.add_column("Value", style="white")

        # Basic VM information
        table.add_row("Name:", self.vm_info['name'])
        table.add_row("ID:", self.vm_info['id'])
        table.add_row("Description:", self.vm_info.get('description', 'N/A'))
        table.add_row("File Path:", self.vm_info['file'])
        table.add_row("Hash:", self.vm_info['hash'][:16] + "...")
        
        # Note: VirtualBox UUID and base_snapshot are now tracked per-instance
        # This is an abstract VM template, not a concrete VirtualBox VM
        
        uses_snapshots = self.vm_info.get('use_snapshots', False)
        snapshot_status = Text("✅ Enabled", style="green") if uses_snapshots else Text("❌ Disabled", style="red")
        table.add_row("Snapshots:", snapshot_status)
        
        # Snapshot details
        snapshots = self.vm_info.get('snapshots', {})
        if snapshots:
            total_snapshots = snapshots.get('total_snapshots', 0)
            table.add_row("Total Snapshots:", str(total_snapshots))
            
            base_snap = snapshots.get('base_snapshot', {})
            if base_snap.get('exists'):
                base_status = Text(f"✅ {base_snap.get('name', 'Unknown')}", style="green")
            else:
                base_status = Text("❌ Missing", style="red")
            table.add_row("Base Snapshot:", base_status)
            
            exp_snapshots = snapshots.get('experiment_snapshots', [])
            if exp_snapshots:
                table.add_row("Experiment Snapshots:", f"{len(exp_snapshots)} found")
                
                # Show first few experiment snapshots
                for i, snap in enumerate(exp_snapshots[:3]):
                    created_at = snap.get('created_at', 'Unknown')
                    if isinstance(created_at, str) and len(created_at) > 16:
                        created_at = created_at[:16] + "..."
                    table.add_row(f"  Snapshot {i+1}:", f"{snap['name']} ({created_at})")
                
                if len(exp_snapshots) > 3:
                    table.add_row("", f"... and {len(exp_snapshots) - 3} more")

        title = f"[b gold3]VM: {self.vm_info['name']}[/b gold3]"
        return Panel(table, title=title, border_style="blue", title_align="left")


def print_vm_info(vm_id: str):
    """Print detailed information about a specific VM."""
    try:
        vm_info = get_vm_info(vm_id)

        console = DefaultConsole()

        if not vm_info:
            console.print(f"[red]VM with ID '{vm_id}' not found[/red]")
            return

        layout = Layout(name="root")
        panel = VMInfoPanel(vm_info)
        layout.update(panel)
        console.print(layout)

    except Exception as e:
        log.error(f"Failed to get VM info: {e}")
        console = DefaultConsole()
        console.print(f"[red]Error getting VM info: {e}[/red]")


def print_vm_or_instance_info(vm_or_instance_id: str, formatter=None, output_file=None, dual_output=False):
    """Print detailed information about a VM or instance (auto-detected)."""
    from adare.database.api.vm import VmApi
    from adare.frontend.terminal.vm_instances import print_vm_instance_info

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    console = DefaultConsole()

    try:
        # First, try as base VM
        vm_info = get_vm_info(vm_or_instance_id)
        if vm_info:
            # Check if structured output is needed
            if dual_output or formatter.format_type.value != 'rich':
                # Prepare structured data
                structured_data = {
                    'type': 'vm',
                    'name': vm_info['name'],
                    'id': vm_info['id'],
                    'description': vm_info.get('description'),
                    'file': vm_info['file'],
                    'hash': vm_info['hash'],
                    'use_snapshots': vm_info.get('use_snapshots', False),
                    'snapshots': vm_info.get('snapshots', {})
                }
                formatter.print_or_save(structured_data, output_file, dual_output)

                if not dual_output:
                    return

            layout = Layout(name="root")
            panel = VMInfoPanel(vm_info)
            layout.update(panel)
            console.print(layout)
            return

        # If not found as base VM, try as instance
        with VmApi() as api:
            instance = api.get_vm_instance_by_id(vm_or_instance_id)
            if instance:
                print_vm_instance_info(vm_or_instance_id, formatter, output_file, dual_output)
                return

        # Not found as either
        console.print(f"[red]VM or instance with ID '{vm_or_instance_id}' not found[/red]")

    except Exception as e:
        log.error(f"Failed to get VM/instance info: {e}")
        console.print(f"[red]Error getting VM/instance info: {e}[/red]")


def print_vm_instance_snapshots(instance_id: str):
    """Print all snapshots for a specific VM instance."""
    from adare.virtualbox.snapshots import list_snapshots
    from adare.database.api.vm import VmApi

    console = DefaultConsole()

    try:
        # Get VM instance record
        with VmApi() as api:
            instance = api.get_vm_instance_by_id(instance_id)
            if not instance:
                console.print(f"[red]VM instance with ID '{instance_id}' not found[/red]")
                return

            # Get the parent VM record for metadata
            vm_record = api.get_vm_by_id(instance.vm_id)
            if not vm_record:
                console.print(f"[red]Parent VM with ID '{instance.vm_id}' not found[/red]")
                return

        # Get snapshots from VirtualBox directly using the instance name
        snapshots = list_snapshots(instance.instance_name)

        # Create table
        table = Table(expand=True)
        table.add_column("Name", style="yellow", no_wrap=True)
        table.add_column("UUID", style="cyan", no_wrap=True)
        table.add_column("Description", style="dim")

        # Add each snapshot
        for snap in snapshots:
            table.add_row(
                snap.get('name', 'Unknown'),
                snap.get('uuid', 'Unknown')[:16] + "...",
                snap.get('description', '')
            )

        total = len(snapshots)
        title = f"[b gold3]Snapshots for VM instance '{instance.instance_name}' ({total} total)[/b gold3]"

        if total == 0:
            console.print(Panel("[yellow]No snapshots found[/yellow]", title=title, border_style="blue"))
        else:
            panel = Panel(table, title=title, border_style="blue", title_align="left")
            console.print(panel)

    except Exception as e:
        log.error(f"Failed to get snapshots for VM instance '{instance_id}': {e}")
        console.print(f"[red]Error getting snapshots: {e}[/red]")


def print_all_snapshots(instance_id_filter: str = None, formatter=None, output_file=None, dual_output=False):
    """Print all snapshots across all VM instances, optionally filtered by instance ID."""
    from adare.virtualbox.snapshots import list_snapshots
    from adare.database.api.vm import VmApi

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    console = DefaultConsole()

    try:
        # If filter specified, just show that instance
        if instance_id_filter:
            print_vm_instance_snapshots(instance_id_filter)
            return

        # Get all VM instances and build VM name cache
        with VmApi() as api:
            instances = api.get_all_vm_instances()

            if not instances:
                console.print("[yellow]No VM instances found[/yellow]")
                return

            # Build VM name cache to avoid multiple lookups
            vm_name_cache = {}
            for instance in instances:
                if instance.vm_id not in vm_name_cache:
                    vm_record = api.get_vm_by_id(instance.vm_id)
                    vm_name_cache[instance.vm_id] = vm_record.name if vm_record else "Unknown"

        total_snapshots = 0
        structured_snapshots = []

        # Get snapshots for each instance
        for instance in instances:
            snapshots = list_snapshots(instance.instance_name)

            if snapshots:
                vm_name = vm_name_cache.get(instance.vm_id, "Unknown")

                for snap in snapshots:
                    total_snapshots += 1
                    structured_snapshots.append({
                        'instance_name': instance.instance_name,
                        'instance_id': instance.id,
                        'vm_name': vm_name,
                        'snapshot_name': snap.get('name', 'Unknown'),
                        'snapshot_uuid': snap.get('uuid', 'Unknown'),
                        'description': snap.get('description', '')
                    })

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            structured_data = {
                'snapshots': structured_snapshots,
                'total_snapshots': total_snapshots,
                'total_instances': len(instances)
            }
            formatter.print_or_save(structured_data, output_file, dual_output)

            if not dual_output:
                return

        # Create table for Rich output
        table = Table(expand=True)
        table.add_column("Instance", style="cyan", no_wrap=True)
        table.add_column("VM", style="magenta", no_wrap=True)
        table.add_column("Snapshot Name", style="yellow", no_wrap=True)
        table.add_column("UUID", style="dim", no_wrap=True)
        table.add_column("Description", style="dim")

        # Add rows to table
        for snap_data in structured_snapshots:
            table.add_row(
                snap_data['instance_name'][:30],  # Truncate long names
                snap_data['vm_name'][:20],
                snap_data['snapshot_name'],
                snap_data['snapshot_uuid'][:16] + "...",
                snap_data['description'][:50]  # Truncate long descriptions
            )

        title = f"[b gold3]All VM Snapshots ({total_snapshots} total across {len(instances)} instances)[/b gold3]"

        if total_snapshots == 0:
            console.print(Panel("[yellow]No snapshots found[/yellow]", title=title, border_style="blue"))
        else:
            panel = Panel(table, title=title, border_style="blue", title_align="left")
            console.print(panel)

    except Exception as e:
        log.error(f"Failed to get all snapshots: {e}")
        console.print(f"[red]Error getting snapshots: {e}[/red]")
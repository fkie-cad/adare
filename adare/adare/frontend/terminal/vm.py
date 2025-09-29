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
        
        # VirtualBox information
        vbox_uuid = self.vm_info.get('vbox_uuid')
        if vbox_uuid:
            vbox_status = Text("✅ Active", style="green")
            table.add_row("VBox UUID:", vbox_uuid[:16] + "...")
        else:
            vbox_status = Text("❌ Not Imported", style="red")
        table.add_row("VBox Status:", vbox_status)
        
        # Snapshot information
        base_snapshot = self.vm_info.get('base_snapshot_name', 'N/A')
        table.add_row("Base Snapshot:", base_snapshot)
        
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


def print_vm_or_instance_info(vm_or_instance_id: str):
    """Print detailed information about a VM or instance (auto-detected)."""
    from adare.database.api.vm import VmApi
    from adare.frontend.terminal.vm_instances import print_vm_instance_info

    console = DefaultConsole()

    try:
        # First, try as base VM
        vm_info = get_vm_info(vm_or_instance_id)
        if vm_info:
            layout = Layout(name="root")
            panel = VMInfoPanel(vm_info)
            layout.update(panel)
            console.print(layout)
            return

        # If not found as base VM, try as instance
        with VmApi() as api:
            instance = api.get_vm_instance_by_id(vm_or_instance_id)
            if instance:
                print_vm_instance_info(vm_or_instance_id)
                return

        # Not found as either
        console.print(f"[red]VM or instance with ID '{vm_or_instance_id}' not found[/red]")

    except Exception as e:
        log.error(f"Failed to get VM/instance info: {e}")
        console.print(f"[red]Error getting VM/instance info: {e}[/red]")


def print_vm_snapshots(vm_id: str):
    """Print all snapshots for a specific VM (abstract VM - deprecated, use instance-specific version)."""
    from adare.backend.vm.snapshot_manager import SnapshotManager
    from adare.database.api.vm import VmApi

    console = DefaultConsole()

    try:
        # Get VM record
        with VmApi() as api:
            vm_record = api.get_vm_by_id(vm_id)
            if not vm_record:
                console.print(f"[red]VM with ID '{vm_id}' not found[/red]")
                return

        # Get snapshot info
        snapshot_manager = SnapshotManager()
        snapshot_info = snapshot_manager.get_snapshot_info(vm_record)

        # Create table
        table = Table(expand=True)
        table.add_column("Type", style="cyan", no_wrap=True)
        table.add_column("Name", style="yellow", no_wrap=True)
        table.add_column("Status", style="cyan", no_wrap=True)
        table.add_column("Details", style="dim")

        # Add base snapshot
        base_snap = snapshot_info.get('base_snapshot', {})
        if base_snap.get('name'):
            status = Text("✅ Exists", style="green") if base_snap.get('exists') else Text("❌ Missing", style="red")
            table.add_row("Base", base_snap['name'], status, "")

        # Add experiment snapshots
        exp_snapshots = snapshot_info.get('experiment_snapshots', [])
        for snap in exp_snapshots:
            created_at = snap.get('created_at', 'Unknown')
            if hasattr(created_at, 'strftime'):
                created_at = created_at.strftime("%Y-%m-%d %H:%M:%S")
            details = f"Created: {created_at}"
            if snap.get('description'):
                details += f" | {snap['description']}"
            table.add_row("Experiment", snap['name'], Text("✅", style="green"), details)

        total = snapshot_info.get('total_snapshots', 0)
        title = f"[b gold3]Snapshots for VM '{vm_record.name}' ({total} total)[/b gold3]"

        if total == 0:
            console.print(Panel("[yellow]No snapshots found[/yellow]", title=title, border_style="blue"))
        else:
            panel = Panel(table, title=title, border_style="blue", title_align="left")
            console.print(panel)

    except Exception as e:
        log.error(f"Failed to get snapshots for VM '{vm_id}': {e}")
        console.print(f"[red]Error getting snapshots: {e}[/red]")


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


def print_all_snapshots(instance_id_filter: str = None):
    """Print all snapshots across all VM instances, optionally filtered by instance ID."""
    from adare.virtualbox.snapshots import list_snapshots
    from adare.database.api.vm import VmApi

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

        # Create table
        table = Table(expand=True)
        table.add_column("Instance", style="cyan", no_wrap=True)
        table.add_column("VM", style="magenta", no_wrap=True)
        table.add_column("Snapshot Name", style="yellow", no_wrap=True)
        table.add_column("UUID", style="dim", no_wrap=True)
        table.add_column("Description", style="dim")

        total_snapshots = 0

        # Get snapshots for each instance
        for instance in instances:
            snapshots = list_snapshots(instance.instance_name)

            if snapshots:
                vm_name = vm_name_cache.get(instance.vm_id, "Unknown")

                for snap in snapshots:
                    table.add_row(
                        instance.instance_name[:30],  # Truncate long names
                        vm_name[:20],
                        snap.get('name', 'Unknown'),
                        snap.get('uuid', 'Unknown')[:16] + "...",
                        snap.get('description', '')[:50]  # Truncate long descriptions
                    )
                    total_snapshots += 1

        title = f"[b gold3]All VM Snapshots ({total_snapshots} total across {len(instances)} instances)[/b gold3]"

        if total_snapshots == 0:
            console.print(Panel("[yellow]No snapshots found[/yellow]", title=title, border_style="blue"))
        else:
            panel = Panel(table, title=title, border_style="blue", title_align="left")
            console.print(panel)

    except Exception as e:
        log.error(f"Failed to get all snapshots: {e}")
        console.print(f"[red]Error getting snapshots: {e}[/red]")
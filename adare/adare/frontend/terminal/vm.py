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
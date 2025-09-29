# external imports
from rich.layout import Layout
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# internal imports
from adare.backend.vm.commands import list_all_vms
from adare.frontend.terminal.console import DefaultConsole

import logging
log = logging.getLogger(__name__)


class VMTablePanel:
    def __init__(self, vms: list):
        self.vms = vms

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("VirtualBox Status", style="cyan", no_wrap=True)
        table.add_column("Description", style="dim")

        for vm in self.vms:
            # VirtualBox status with colored indicators
            if vm.get('vbox_uuid'):
                vbox_status = Text("✅ Active", style="green")
            else:
                vbox_status = Text("❌ Not Imported", style="red")
            
            # Truncate description if too long
            description = vm.get('description', '')
            if len(description) > 40:
                description = description[:37] + "..."

            table.add_row(
                vm['name'],
                vm['id'],
                vbox_status,
                description or "No description"
            )
        
        title = f"[b gold3]VMs ({len(self.vms)} found)[/b gold3]"
        return Panel(table, title=title, border_style="blue", title_align="left")


def print_vm_list():
    """Print a formatted list of all VMs in the system."""
    try:
        vms = list_all_vms()

        console = DefaultConsole()

        if not vms:
            console.print(Panel("[yellow]No VMs found[/yellow]", title="[b gold3]VMs[/b gold3]", border_style="blue"))
            return

        layout = Layout(name="root")
        panel = VMTablePanel(vms)
        layout.update(panel)
        console.print(layout)

    except Exception as e:
        log.error(f"Failed to list VMs: {e}")
        console = DefaultConsole()
        console.print(f"[red]Error listing VMs: {e}[/red]")


def print_vm_and_instances_list():
    """Print a formatted list of all VMs and instances in the system."""
    from adare.database.api.vm import VmApi

    try:
        console = DefaultConsole()

        # Get base VMs
        vms = list_all_vms()

        # Get instances
        with VmApi() as api:
            instances = api.get_all_vm_instances()

        # Create VM table
        if vms:
            vm_table = Table(expand=True)
            vm_table.add_column("Name", style="cyan", no_wrap=True)
            vm_table.add_column("ID", style="dim", no_wrap=True)
            vm_table.add_column("VirtualBox Status", style="cyan", no_wrap=True)
            vm_table.add_column("Description", style="dim")

            for vm in vms:
                vbox_status = Text("✅ Active", style="green") if vm.get('vbox_uuid') else Text("❌ Not Imported", style="red")
                description = vm.get('description', '')
                if len(description) > 40:
                    description = description[:37] + "..."

                vm_table.add_row(
                    vm['name'],
                    vm['id'],
                    vbox_status,
                    description or "No description"
                )

            vm_panel = Panel(vm_table, title=f"[b gold3]Base VMs ({len(vms)} found)[/b gold3]", border_style="blue", title_align="left")
            console.print(vm_panel)
        else:
            console.print(Panel("[yellow]No base VMs found[/yellow]", title="[b gold3]Base VMs[/b gold3]", border_style="blue"))

        # Create instance table
        if instances:
            instance_table = Table(expand=True)
            instance_table.add_column("Instance Name", style="cyan", no_wrap=True)
            instance_table.add_column("ID", style="dim", no_wrap=True)
            instance_table.add_column("Status", style="cyan", no_wrap=True)
            instance_table.add_column("Port", style="cyan", no_wrap=True)
            instance_table.add_column("Last Used", style="dim", no_wrap=False)

            for instance in instances:
                last_used = instance.last_used_at.strftime("%Y-%m-%d %H:%M:%S") if instance.last_used_at else "Never"
                port = str(instance.websocket_port) if instance.websocket_port else "N/A"
                status_color = "green" if instance.status == "running" else "dim"
                instance_table.add_row(
                    instance.instance_name,
                    instance.id,
                    Text(instance.status, style=status_color),
                    port,
                    last_used
                )

            instance_panel = Panel(instance_table, title=f"[b gold3]VM Instances ({len(instances)} found)[/b gold3]", border_style="blue", title_align="left")
            console.print(instance_panel)
        else:
            console.print(Panel("[yellow]No VM instances found[/yellow]", title="[b gold3]VM Instances[/b gold3]", border_style="blue"))

    except Exception as e:
        log.error(f"Failed to list VMs and instances: {e}")
        console = DefaultConsole()
        console.print(f"[red]Error listing VMs and instances: {e}[/red]")
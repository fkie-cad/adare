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
        table.add_column("Description", style="dim")

        for vm in self.vms:
            # Truncate description if too long
            description = vm.get('description', '')
            if len(description) > 40:
                description = description[:37] + "..."

            table.add_row(
                vm['name'],
                vm['id'],
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


def print_vm_and_instances_list(formatter=None, output_file=None, dual_output=False):
    """Print a formatted list of all VMs and instances in the system."""
    from adare.database.api.vm import VmApi

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    try:
        console = DefaultConsole()

        # Get base VMs
        vms = list_all_vms()

        # Get instances
        with VmApi() as api:
            instances = api.get_all_vm_instances()

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            # Prepare structured data
            structured_vms = []
            for vm in vms:
                structured_vms.append({
                    'name': vm['name'],
                    'id': vm['id'],
                    'description': vm.get('description', ''),
                    'hypervisor': vm.get('hypervisor', '')
                })

            structured_instances = []
            for instance in instances:
                structured_instances.append({
                    'instance_name': instance.instance_name,
                    'id': instance.id,
                    'vm_id': instance.vm_id,
                    'vm_name': instance.vm.name if instance.vm else None,
                    'hypervisor': instance.vm.hypervisor if instance.vm else None,
                    'status': instance.status,
                    'websocket_port': instance.websocket_port,
                    'last_used_at': instance.last_used_at.isoformat() if instance.last_used_at else None
                })

            structured_data = {
                'vms': structured_vms,
                'instances': structured_instances,
                'vm_count': len(vms),
                'instance_count': len(instances)
            }

            formatter.print_or_save(structured_data, output_file, dual_output)

            if not dual_output:
                return

        # Create VM table
        if vms:
            vm_table = Table(expand=True)
            vm_table.add_column("Name", style="cyan", no_wrap=True)
            vm_table.add_column("ID", style="dim", no_wrap=True)
            vm_table.add_column("Hypervisor", style="cyan", no_wrap=True)
            vm_table.add_column("Description", style="dim")

            for vm in vms:
                description = vm.get('description', '')
                if len(description) > 40:
                    description = description[:37] + "..."

                vm_table.add_row(
                    vm['name'],
                    vm['id'],
                    vm.get('hypervisor', 'unknown'),
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
            instance_table.add_column("Parent VM", style="cyan", no_wrap=True)
            instance_table.add_column("Hypervisor", style="cyan", no_wrap=True)
            instance_table.add_column("Status", style="cyan", no_wrap=True)
            instance_table.add_column("Port", style="cyan", no_wrap=True)
            instance_table.add_column("Last Used", style="dim", no_wrap=False)

            for instance in instances:
                last_used = instance.last_used_at.strftime("%Y-%m-%d %H:%M:%S") if instance.last_used_at else "Never"
                port = str(instance.websocket_port) if instance.websocket_port else "N/A"
                status_color = "green" if instance.status == "running" else "dim"
                parent_vm_name = instance.vm.name if instance.vm else "Unknown"
                hypervisor = instance.vm.hypervisor if instance.vm else "unknown"
                instance_table.add_row(
                    instance.instance_name,
                    instance.id,
                    parent_vm_name,
                    hypervisor,
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
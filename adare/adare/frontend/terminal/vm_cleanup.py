# external imports
from rich.layout import Layout
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# internal imports
from adare.backend.vm.commands import clear_all_vms, clear_vms_by_environment, list_all_vms
from adare.backend.vm.database import get_vms_by_environment
from adare.frontend.terminal.console import DefaultConsole

import logging
log = logging.getLogger(__name__)


class VMConfirmationPanel:
    def __init__(self, vms: list, title: str, warning_text: str):
        self.vms = vms
        self.title = title
        self.warning_text = warning_text

    def __rich__(self) -> Panel:
        if not self.vms:
            return Panel("[yellow]No VMs found to delete[/yellow]", 
                        title=f"[b gold3]{self.title}[/b gold3]", 
                        border_style="yellow")
        
        table = Table(expand=True)
        table.add_column("Name", style="red", no_wrap=True)
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Status", style="cyan", no_wrap=True)

        for vm in self.vms[:15]:  # Show max 15 VMs
            if hasattr(vm, 'name'):  # VM object
                name = vm.name
                vm_id = vm.id
                vbox_status = "📄 Template"  # Vm is abstract template, not in VirtualBox
            else:  # Dict
                name = vm['name']
                vm_id = vm['id']
                vbox_status = "📄 Template"  # Vm is abstract template
            
            table.add_row(name, vm_id, vbox_status)
        
        if len(self.vms) > 15:
            table.add_row(f"... and {len(self.vms) - 15} more", "", "")
        
        content = f"[red bold]{self.warning_text}[/red bold]\n\n{table}\n\n[yellow]Use --force to confirm this action[/yellow]"
        
        return Panel(content, title=f"[b red]⚠️  {self.title}[/b red]", 
                    border_style="red", title_align="left")


class VMCleanupResultsPanel:
    def __init__(self, results: dict, operation_name: str):
        self.results = results
        self.operation_name = operation_name

    def __rich__(self) -> Panel:
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Result", style="white", width=20)
        table.add_column("Count", style="cyan", width=10)
        table.add_column("Details", style="dim")

        # Success count
        if self.results['deleted_count'] > 0:
            table.add_row(
                Text("✅ Successfully Deleted:", style="green"),
                str(self.results['deleted_count']),
                ""
            )
            for vm_name in self.results['deleted_vms'][:5]:  # Show first 5
                table.add_row("", "", f"• {vm_name}")
            if len(self.results['deleted_vms']) > 5:
                table.add_row("", "", f"• ... and {len(self.results['deleted_vms']) - 5} more")

        # Failure count
        if self.results['failed_count'] > 0:
            table.add_row(
                Text("❌ Failed to Delete:", style="red"),
                str(self.results['failed_count']),
                ""
            )
            for error in self.results['failed_vms'][:3]:  # Show first 3 errors
                table.add_row("", "", f"• {error}")
            if len(self.results['failed_vms']) > 3:
                table.add_row("", "", f"• ... and {len(self.results['failed_vms']) - 3} more errors")

        # Skipped count (if any)
        if self.results.get('skipped_count', 0) > 0:
            table.add_row(
                Text("⏭️  Skipped:", style="yellow"),
                str(self.results['skipped_count']),
                ""
            )

        # Summary
        if self.results['deleted_count'] == 0 and self.results['failed_count'] == 0:
            table.add_row(
                Text("ℹ️  No Action Needed", style="blue"),
                "0",
                "No VMs found to delete"
            )

        title = f"[b gold3]{self.operation_name} Results[/b gold3]"
        return Panel(table, title=title, border_style="blue", title_align="left")


def print_vm_clear_all_confirmation():
    """Print confirmation for clearing all VMs."""
    try:
        vms = list_all_vms()
        
        print(f"⚠️  This will delete ALL {len(vms)} VMs from the system!")
        
        if vms:
            print("\nVMs to be deleted:")
            for vm in vms[:10]:  # Show max 10 VMs
                if hasattr(vm, 'name'):  # VM object
                    name = vm.name
                    vm_id = vm.id
                else:  # Dict
                    name = vm['name']
                    vm_id = vm['id']
                print(f"  - {name} ({vm_id})")
            
            if len(vms) > 10:
                print(f"  ... and {len(vms) - 10} more")
        else:
            print("No VMs found to delete")
            
        print("\nUse --force to confirm this action")
        
    except Exception as e:
        log.error(f"Failed to show VM confirmation: {e}")
        print(f"Error showing confirmation: {e}")


def print_vm_clear_environment_confirmation(environment_ulid: str):
    """Print confirmation for clearing VMs by environment."""
    try:
        vms = get_vms_by_environment(environment_ulid)
        console = DefaultConsole()
        
        layout = Layout(name="root")
        panel = VMConfirmationPanel(
            vms,
            f"Clear Environment VMs",
            f"This will delete {len(vms)} VMs for environment {environment_ulid}!"
        )
        layout.update(panel)
        console.print(layout)
        
    except Exception as e:
        log.error(f"Failed to show environment VM confirmation: {e}")
        console = DefaultConsole()
        console.print(f"[red]Error showing confirmation: {e}[/red]")


def print_vm_clear_all_results(results: dict):
    """Print results of clearing all VMs."""
    try:
        console = DefaultConsole()
        
        layout = Layout(name="root")
        panel = VMCleanupResultsPanel(results, "Clear All VMs")
        layout.update(panel)
        console.print(layout)
        
    except Exception as e:
        log.error(f"Failed to show VM cleanup results: {e}")
        console = DefaultConsole()
        console.print(f"[red]Error showing results: {e}[/red]")


def print_vm_clear_environment_results(results: dict, environment_ulid: str):
    """Print results of clearing environment VMs."""
    try:
        console = DefaultConsole()
        
        layout = Layout(name="root")
        panel = VMCleanupResultsPanel(results, f"Clear Environment VMs ({environment_ulid})")
        layout.update(panel)
        console.print(layout)
        
    except Exception as e:
        log.error(f"Failed to show environment VM cleanup results: {e}")
        console = DefaultConsole()
        console.print(f"[red]Error showing results: {e}[/red]")


def print_vm_delete_success(vm_id: str):
    """Print success message for VM deletion."""
    console = DefaultConsole()
    console.print(f"[green]✅ Successfully deleted VM: {vm_id}[/green]")


def print_vm_delete_failure(vm_id: str, error: str):
    """Print failure message for VM deletion."""
    console = DefaultConsole()
    console.print(f"[red]❌ Failed to delete VM {vm_id}: {error}[/red]")
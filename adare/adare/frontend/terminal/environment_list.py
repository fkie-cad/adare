# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.models.global_models import Environment, OsInfo, Vm
from adare.frontend.terminal.console import DefaultConsole

log = logging.getLogger(__name__)


class EnvironmentTablePanel:
    def __init__(self, environments: pd.DataFrame):
        self.environments = environments

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("ulid", style="cyan", no_wrap=True)
        table.add_column("file path", style="yellow", no_wrap=False)
        table.add_column("vm", style="cyan", no_wrap=True)
        table.add_column("os", style="cyan", no_wrap=True)
        table.add_column("web status", style="cyan", no_wrap=True)

        for i, row in self.environments.iterrows():
            published = True if row['published'] == 'True' else False
            in_request = True if row['in_request'] == 'True' else False
            web_status = 'NOT published'
            if published:
                web_status = 'published'
            if in_request:
                web_status = 'in request'

            table.add_row(
                row['display_name'],
                row['id'],
                row['file'] if 'file' in row and row['file'] else 'N/A',
                row['vm_name'] if 'vm_name' in row and row['vm_name'] else 'No VM',
                row['osinfo'] if 'osinfo' in row and row['osinfo'] else 'Unknown',
                web_status,
            )
        return Panel(table, title="[b gold3]environments[/b gold3]", border_style="blue", title_align="left")


def print_environment_list(formatter=None, output_file=None, dual_output=False):
    """Print environment list in the configured output format."""

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    if dual_output or formatter.format_type.value != 'rich':
        # Use StructuredDataApi for JSON/YAML output
        from adare.database.api.structured_data import StructuredDataApi
        with StructuredDataApi() as api:
            environments_structured = api.get_environments_structured()
            environment_list = [env.to_dict() for env in environments_structured]
            formatter.print_or_save({'environments': environment_list}, output_file, dual_output)
    else:
        # Use GlobalDatabaseApi for Rich terminal output (environments are global resources)
        with GlobalDatabaseApi() as db:
            environments = db._session.query(Environment).all()

            # Build DataFrame for Rich display
            data = []
            for env in environments:
                vm = db._session.query(Vm).filter_by(id=env.vm_id).first() if env.vm_id else None
                osinfo = db._session.query(OsInfo).filter_by(id=vm.osinfo_id).first() if vm and vm.osinfo_id else None

                # Get sync status
                published = 'False'
                in_request = 'False'
                if hasattr(env, 'sync_metadata') and env.sync_metadata:
                    published = str(env.sync_metadata.is_synced)
                    in_request = str(env.sync_metadata.needs_sync)

                data.append({
                    'display_name': env.name,
                    'id': env.id,
                    'file': env.file or 'N/A',
                    'vm_name': vm.name if vm else 'No VM',
                    'osinfo': str(osinfo) if osinfo else 'Unknown',
                    'published': published,
                    'in_request': in_request,
                })

            environments_df = pd.DataFrame(data)

        console = DefaultConsole()
        layout = Layout(name="root")
        panel = EnvironmentTablePanel(environments_df)
        layout.update(panel)
        console.print(layout)

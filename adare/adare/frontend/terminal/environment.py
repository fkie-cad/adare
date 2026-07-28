# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole, TagsText, pad_string_to_length

log = logging.getLogger(__name__)


class InfoPanel:
    environment: pd.DataFrame

    def __init__(self, environment: pd.DataFrame):
        self.environment = environment

    def __rich__(self) -> Panel:
        title = '[b medium_turquoise]info[/b medium_turquoise]'
        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_row(
            f"{pad_string_to_length('name', 12)}: [b]{self.environment['name'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('ulid', 12)}: [b]{self.environment['id'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('vm', 12)}: [b]{self.environment['vm_name'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('project', 12)}: [b]{self.environment['project_name'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('file', 12)}: [b]{self.environment['file'].values[0]}[/b]",
        )
        # The disk a run would actually boot. 'file' above is the environment's YAML
        # descriptor and outlives the qcow2 it points at, so without this row an
        # environment whose disk was pruned reads as perfectly healthy here.
        if 'disk_present' in self.environment.columns:
            disk_present = self.environment['disk_present'].values[0]
            disk_path = self.environment['disk_path'].values[0]
            if disk_present is None:
                disk = f'[dim]{disk_path or "n/a"}[/dim]'
            elif disk_present:
                disk = f'[b]{disk_path}[/b] [green](present)[/green]'
            else:
                disk = f'[b]{disk_path}[/b] [bold red](MISSING)[/bold red]'
            grid.add_row(f"{pad_string_to_length('disk', 12)}: {disk}")
        grid.add_row(
            f"{pad_string_to_length('created', 12)}: [b]{self.environment['created_at'].values[0]}[/b]",
        )
        return Panel(grid, title=title, border_style="blue", title_align="left")


class OsInfoPanel:
    environment: pd.DataFrame

    def __init__(self, environment: pd.DataFrame):
        self.environment = environment

    def __rich__(self) -> Panel:
        title = '[b honeydew2]os[/b honeydew2]'
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_row(
            f"{pad_string_to_length('os', 12)}: [b]{self.environment['osinfo_os'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('distribution', 12)}: [b]{self.environment['osinfo_distribution'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('version', 12)}: [b]{self.environment['osinfo_version'].values[0]}[/b]",
        )
        if self.environment['osinfo_language'].values[0]:
            grid.add_row(
                f"{pad_string_to_length('language', 12)}: [b]{self.environment['osinfo_language'].values[0]}[/b]",
            )
        if self.environment['osinfo_architecture'].values[0]:
            grid.add_row(
                f"{pad_string_to_length('architecture', 12)}: [b]{self.environment['osinfo_architecture'].values[0]}[/b]",
            )

        return Panel(grid, title=title, border_style="blue", title_align="left")


class DescriptionPanel:
    description: str

    def __init__(self, description: str):
        self.description = description

    def __rich__(self) -> Panel:
        title = '[b light_steel_blue]description[/b light_steel_blue]'
        return Panel(Text(self.description), title=title, border_style="blue", title_align="left")


class EnvironmentPanel:
    environment: pd.DataFrame

    def __init__(self, environment: pd.DataFrame):
        self.environment = environment

    def __rich__(self) -> Panel:
        title = f'[b gold3]{self.environment["name"].values[0]}[/b gold3]'
        layout = Layout(name="env")
        layout.split(
            Layout(name="tags", size=1),
            Layout(name="content", ratio=1),
        )
        layout["content"].split(
            Layout(name="info", ratio=2),
            Layout(name="description", ratio=1),
        )
        layout["info"].split_row(
            Layout(name="general", ratio=2),
            Layout(name="osinfo", ratio=1),
        )

        layout["content"]["info"]["general"].update(
            InfoPanel(self.environment)
        )
        layout["content"]["info"]["osinfo"].update(
            OsInfoPanel(self.environment)
        )
        description = self.environment['description'].values[0]
        if description:
            layout["content"]["description"].update(
                DescriptionPanel(self.environment['description'].values[0])
            )
        else:
            layout["content"]["description"].visible = False
        layout["tags"].update(
            TagsText(self.environment['tags'].values[0])
        )

        return Panel(layout, title=title, border_style="blue", title_align="left")


def _annotate_disk_status(environment: pd.DataFrame) -> None:
    """Add 'disk_path' / 'disk_present' columns by stat'ing the registered VM's disk.

    The environment row's own 'file' is the YAML descriptor, which keeps existing after
    the qcow2 it references is pruned. Without an explicit check, such an environment
    reports as healthy everywhere and only fails once a run reaches VM setup.

    Mutates in place and stays best-effort: a lookup failure leaves the columns unset,
    which the panel renders by omitting the row rather than by claiming anything.
    """
    from pathlib import Path

    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Vm

    if environment.empty or 'vm_name' not in environment.columns:
        return

    vm_name = environment['vm_name'].values[0]
    if not vm_name:
        return

    with GlobalDatabaseApi() as db:
        vm_row = db._session.query(Vm).filter_by(name=vm_name).first()

    disk_path = (vm_row.file if vm_row else '') or ''
    # None where there is nothing local to stat (e.g. a URL-baked environment), so it is
    # reported as unknown rather than as missing.
    environment['disk_path'] = disk_path
    environment['disk_present'] = (
        Path(disk_path).is_file()
        if disk_path and '://' not in disk_path
        else None
    )


def print_environment(environment_name: str, formatter=None, output_file=None, dual_output=False):
    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    with DataRetrievalApi() as db:
        console = DefaultConsole()
        environment = db.get_environment_by_name(environment_name)
        _annotate_disk_status(environment)

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            structured_data = {
                'name': environment['name'].values[0],
                'id': environment['id'].values[0],
                'vm_name': environment['vm_name'].values[0],
                'project_name': environment['project_name'].values[0],
                'file': environment['file'].values[0],
                'disk': {
                    'path': environment['disk_path'].values[0] if 'disk_path' in environment.columns else '',
                    'present': environment['disk_present'].values[0] if 'disk_present' in environment.columns else None,
                },
                'created_at': str(environment['created_at'].values[0]),
                'description': environment['description'].values[0],
                'tags': environment['tags'].values[0] if 'tags' in environment.columns else [],
                'osinfo': {
                    'os': environment['osinfo_os'].values[0],
                    'distribution': environment['osinfo_distribution'].values[0],
                    'version': environment['osinfo_version'].values[0],
                    'language': environment['osinfo_language'].values[0],
                    'architecture': environment['osinfo_architecture'].values[0]
                }
            }
            formatter.print_or_save(structured_data, output_file, dual_output)

            if not dual_output:
                return

        # Printed directly, NOT wrapped in a Layout: a Layout crops its content to
        # the terminal height and silently drops whatever overflows, so a short
        # window hid fields without any indication they were there.
        console.print(EnvironmentPanel(environment))

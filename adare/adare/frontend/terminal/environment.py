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


def print_environment(environment_name: str, formatter=None, output_file=None, dual_output=False):
    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    with DataRetrievalApi() as db:
        console = DefaultConsole()
        environment = db.get_environment_by_name(environment_name)

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            structured_data = {
                'name': environment['name'].values[0],
                'id': environment['id'].values[0],
                'vm_name': environment['vm_name'].values[0],
                'project_name': environment['project_name'].values[0],
                'file': environment['file'].values[0],
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

        layout = Layout(name="root")
        panel = EnvironmentPanel(environment)
        layout.update(panel)
        console.print(layout)

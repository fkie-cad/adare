# external imports
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import pad_string_to_length, DefaultConsole, TagsText

import logging
log = logging.getLogger(__name__)


class InfoPanel:
    environment: pd.DataFrame

    def __init__(self, environment: pd.DataFrame):
        self.environment = environment

    def __rich__(self) -> Panel:
        title = f'[b medium_turquoise]info[/b medium_turquoise]'
        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_row(
            f"{pad_string_to_length('name', 12)}: [b]{self.environment['dotnotation'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('ulid', 12)}: [b]{self.environment['ulid'].values[0]}[/b]",
        )
        grid.add_row(
            f"{pad_string_to_length('box', 12)}: [b]{self.environment['vagrantbox'].values[0]}[/b]",
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
        title = f'[b honeydew2]os[/b honeydew2]'
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
        title = f'[b light_steel_blue]description[/b light_steel_blue]'
        return Panel(Text(self.description), title=title, border_style="blue", title_align="left")


class EnvironmentPanel:
    environment: pd.DataFrame

    def __init__(self, environment: pd.DataFrame):
        self.environment = environment

    def __rich__(self) -> Panel:
        title = f'[b gold3]{self.environment["dotnotation"].values[0]}[/b gold3]'
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


def print_environment(environment: str = None, project: str = None, ulid: str = None):
    with DataRetrievalApi() as db:
        console = DefaultConsole()
        environment = db.get_environment(environment, project, ulid)
        layout = Layout(name="root")
        panel = EnvironmentPanel(environment)
        layout.update(panel)
        console.print(layout)

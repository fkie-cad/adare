# external imports
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.helperfunctions.cli import print_df, print_dict
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole
from adare.types.output_models import ProjectInfo

import logging
log = logging.getLogger(__name__)


class ProjectTablePanel:
    def __init__(self, projects: pd.DataFrame):
        self.projects = projects

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("path", style="cyan", no_wrap=True)
        table.add_column("environments", style="cyan", no_wrap=True)

        for i, row in self.projects.iterrows():
            table.add_row(
                row['name'],
                row['path'],
                row['environments_names']
            )
        return Panel(table, title="[b gold3]projects[/b gold3]", border_style="blue", title_align="left")


def print_project_list(formatter=None, output_file=None, dual_output=False):
    """Print project list in the configured output format."""

    # Get data from database
    with DataRetrievalApi() as db:
        projects = db.get_projects()

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    if dual_output or formatter.format_type.value != 'rich':
        # Convert to structured data
        project_list = []
        for _, row in projects.iterrows():
            project_info = ProjectInfo(
                name=row['name'],
                description=row.get('description', ''),
                environment_count=len(row.get('environments_names', '').split(',')) if row.get('environments_names') else 0
            )
            project_list.append(project_info.to_dict())

        # Output structured data
        formatter.print_or_save({'projects': project_list}, output_file, dual_output)
    else:
        # Use existing Rich formatting
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = ProjectTablePanel(projects)
        layout.update(panel)
        console.print(layout)

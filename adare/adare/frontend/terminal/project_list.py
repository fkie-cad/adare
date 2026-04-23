# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

from adare.frontend.terminal.console import DefaultConsole

# internal imports

log = logging.getLogger(__name__)


class ProjectTablePanel:
    def __init__(self, projects: pd.DataFrame):
        self.projects = projects

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("path", style="cyan", no_wrap=True)

        for i, row in self.projects.iterrows():
            table.add_row(
                row['name'],
                row['path'],
            )
        return Panel(table, title="[b gold3]projects[/b gold3]", border_style="blue", title_align="left")


def print_project_list(formatter=None, output_file=None, dual_output=False):
    """Print project list in the configured output format."""

    # Get data from database - use global API directly for projects
    import pandas as pd

    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import Project
    with GlobalDatabaseApi() as db:
        projects = pd.read_sql(db._session.query(Project).statement, db._session.bind).map(str)

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    if dual_output or formatter.format_type.value != 'rich':
        # Use StructuredDataApi for JSON/YAML output
        from adare.database.api.structured_data import StructuredDataApi
        with StructuredDataApi() as api:
            projects_structured = api.get_projects_structured()
            project_list = [proj.to_dict() for proj in projects_structured]
            formatter.print_or_save({'projects': project_list}, output_file, dual_output)
    else:
        # Use existing Rich formatting
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = ProjectTablePanel(projects)
        layout.update(panel)
        console.print(layout)

# external imports
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole
from adare.types.output_models import TestFunctionInfo

import logging
log = logging.getLogger(__name__)


class TestfunctionListPanel:
    testfunctions: pd.DataFrame
    testfunction_file: str
    show_project_column: bool

    def __init__(self, testfunctions: pd.DataFrame, testfunction_file: str, show_project_column: bool = False):
        self.testfunctions = testfunctions
        self.testfunction_file = testfunction_file
        self.show_project_column = show_project_column

    def __rich__(self) -> Panel:
        if not self.testfunction_file:
            title = '[b gold3]testfunctions[/b gold3]'
        else:
            title = f'[b gold3]testfunctions[/b gold3] from [b gold3]{self.testfunction_file}[/b gold3]'
        table = Table(expand=True)

        # Add project column if showing project info and not filtering by specific file
        if self.show_project_column and not self.testfunction_file:
            table.add_column("project", justify="left", style="cyan", no_wrap=True)

        # Add file column if not filtering by specific file
        if not self.testfunction_file:
            table.add_column("file", justify="left", style="cyan", no_wrap=True)

        table.add_column("testfunction", justify="left", style="cyan", no_wrap=True)
        table.add_column("description", justify="left", style="cyan", no_wrap=True)
        table.add_column("#parameters", justify="left", style="cyan", no_wrap=True)

        for _, row in self.testfunctions.iterrows():
            # For name, use smart display name when available, otherwise fall back to existing logic
            if self.testfunction_file:
                display_name = row['name']
            else:
                # Use the new smart display_name field if available, otherwise fall back to dotnotation logic
                if 'display_name' in row:
                    display_name = row['display_name']
                    if '.' in display_name:
                        display_name = display_name.split('.', 1)[1]  # Keep everything after the first dot
                else:
                    display_name = row['dotnotation']
                    if '.' in display_name:
                        display_name = display_name.split('.', 1)[1]  # Keep everything after the first dot

            row_data = []

            # Add project column data if showing project info and not filtering by specific file
            if self.show_project_column and not self.testfunction_file:
                project_name = row.get('project', '') if 'project' in row else ''
                row_data.append(project_name)

            # Add file column data if not filtering by specific file
            if not self.testfunction_file:
                # Extract file name from dotnotation or file_name column if available
                if 'file_name' in row:
                    file_name = row['file_name'].replace('.py', '') if row['file_name'].endswith('.py') else row['file_name']
                elif 'dotnotation' in row and '.' in row['dotnotation']:
                    file_name = row['dotnotation'].split('.', 1)[0]
                else:
                    file_name = 'unknown'
                row_data.append(file_name)

            row_data.extend([
                display_name,
                row['description'],
                str(row['num_parameters']),
            ])

            table.add_row(*row_data)

        return Panel(table, border_style="blue", title_align='left', style='', title=title)


def print_testfunction_list(testfunction_file: str = None, formatter=None, output_file=None, dual_output=False):
    """Print testfunction list in the configured output format."""

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    # Determine if we should show project column by checking if we're outside a project context
    show_project_column = False
    try:
        from adare.backend.basics import determine_projectdirectory
        project_directory = determine_projectdirectory(None, silent=True)
        show_project_column = project_directory is None
    except:
        show_project_column = True  # Default to showing project column if we can't determine

    if dual_output or formatter.format_type.value != 'rich':
        # Use StructuredDataApi for JSON/YAML output
        from adare.database.api.structured_data import StructuredDataApi
        with StructuredDataApi() as api:
            testfunctions = api.get_testfunctions_structured(
                include_parameters=True,
                testfunction_file=testfunction_file
            )
            testfunction_list = [tf.to_dict() for tf in testfunctions]
            formatter.print_or_save({'testfunctions': testfunction_list}, output_file, dual_output)
    else:
        # Use existing Rich formatting with DataRetrievalApi
        with DataRetrievalApi() as api:
            testfunctions = api.get_testfunction_list()

            # Apply filtering if testfunction_file is specified
            if testfunction_file:
                # Filter based on file name (extracted from dotnotation or file_name column)
                if 'file_name' in testfunctions.columns:
                    file_column = 'file_name'
                elif 'dotnotation' in testfunctions.columns:
                    # Extract file name from dotnotation
                    testfunctions = testfunctions.copy()
                    testfunctions['file_name'] = testfunctions['dotnotation'].apply(
                        lambda x: x.split('.', 1)[0] if '.' in str(x) else str(x)
                    )
                    file_column = 'file_name'
                else:
                    # No suitable column found, use original data
                    file_column = None

                if file_column:
                    testfunctions = testfunctions[testfunctions[file_column] == testfunction_file]

            console = DefaultConsole()
            layout = Layout(name="root")
            panel = TestfunctionListPanel(testfunctions, testfunction_file, show_project_column)
            layout.update(panel)
            console.print(layout)

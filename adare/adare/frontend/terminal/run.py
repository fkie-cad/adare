# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole, TwoTitleRule, pad_string_to_length, timedelta_to_str
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class ExperimentRunHeader:
    experiment_name: str
    experiment_ulid: str
    environment_name: str
    experiment_ulid: str
    project_name: str
    duration: str
    start_time: str
    end_time: str
    osinfo: str
    box: str
    published: bool
    fake: bool

    def __init__(self, experiment_name: str, experiment_ulid: str, environment_ulid: str, environment_name: str,
                 project_name: str, duration: pd.Timedelta, start_time: str, end_time: str, vm: str, osinfo: str, published: bool, fake: bool = False):
        self.experiment_name = experiment_name
        self.experiment_ulid = experiment_ulid
        self.environment_ulid = environment_ulid
        self.environment_name = environment_name
        self.project_name = project_name
        self.duration = f'{timedelta_to_str(duration)}' if duration else '...'
        self.start_time = start_time or '...'
        self.end_time = end_time or '...'
        self.vm = vm
        self.osinfo = osinfo
        self.published = published
        self.fake = fake

    def __rich__(self) -> Panel:
        title = '[b medium_turquoise]info[/b medium_turquoise]'
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            f"{pad_string_to_length('experiment', 11)}: [b]{self.experiment_name}[/b] ([i]{self.experiment_ulid}[/i])",
            f"start: {self.start_time}",
        )
        grid.add_row(
            f"{pad_string_to_length('environment', 11)}: [b]{self.environment_name}[/b] ([i]{self.environment_ulid}[/i])",
            f"end: {self.end_time}",
        )
        grid.add_row(
            f"{pad_string_to_length('project', 11)}: [b]{self.project_name}[/b]",
            f"duration: {self.duration}",
        )
        grid.add_row(
            f"{pad_string_to_length('osinfo', 11)}: [b]{self.osinfo}[/b]",
            f"vm: {self.vm}",
        )
        published_str = "published" if self.published else "not published"
        run_type_str = "[red bold]TEST/FAKE RUN[/red bold]" if self.fake else published_str
        grid.add_row("", run_type_str)
        return Panel(grid, title=title, border_style="blue", title_align='left', style='')


class ExperimentRunTestsPanel:
    tests_data: dict
    test_overall_result: int

    def __init__(self, test_overall_result: int, tests_data: dict):
        self.tests_data = tests_data
        self.test_overall_result = test_overall_result

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)

        for test_data in self.tests_data.values():
            color = StatusEnum.get_color(test_data['result_status'])
            grid.add_row(
                TwoTitleRule(
                    title=f'[b {color}]{test_data["name"]} ([i]{test_data["testfunction_name"]}[/i])[/b {color}]',
                    style=color,
                    align='around',
                    title_right=f'[b {color}]{test_data["result_status_name"]}[/b {color}]',
                ),
            )
            # Add parameters section
            grid.add_row(':gear: [b]parameters[/b]:')
            for parameter in test_data['parameters']:
                grid.add_row(
                    f'  {parameter["name"]} ([i]{parameter["dtype"]}[/i]): [b]{parameter["value"]}[/b]'
                )

            # Add details section with better separation if details exist
            if test_data['result_details']:
                grid.add_row('')  # Empty line for separation
                grid.add_row(':information_source: [b]details[/b]:')
                grid.add_row(f'  {test_data["result_details"]}')

            # Add spacing between tests for better readability
            grid.add_row('')

        title = '[b light_steel_blue]tests[/b light_steel_blue]'
        title = f'{title} {StatusEnum.get_icon(self.test_overall_result, color=True)}'
        return Panel(grid, title=title, border_style="blue",
                     title_align='left', style='')


class ExperimentRunFlowPanel:
    stages: pd.DataFrame
    status: int

    def __init__(self, status: int, stages: pd.DataFrame):
        self.stages = stages
        self.status = status

    @staticmethod
    def __generate_line(row: pd.Series) -> str:
        # Defensive handling for status field
        try:
            status = row.get('status', StatusEnum.PENDING)
            if pd.isna(status):
                status = StatusEnum.PENDING
            icon = StatusEnum.get_icon(status, color=True)
        except (KeyError, TypeError, ValueError):
            # Fallback to pending status if there's any issue
            icon = StatusEnum.get_icon(StatusEnum.PENDING, color=True)

        message = row.get('msg', 'Unknown stage')
        sub_msg = row.get('sub_msg')
        if sub_msg and not pd.isna(sub_msg):
            message = f'{message}: {sub_msg}'

        level = row.get('level', 0)
        level_offset = 2 * ' ' * level
        line = f'{level_offset}{icon} {message}'

        # Handle result_status if present
        result_status = row.get('result_status')
        if result_status and str(result_status) != 'nan' and not pd.isna(result_status):
            try:
                result_icon = StatusEnum.get_icon(result_status, color=True)
                line = f'{line} {result_icon}'
            except (TypeError, ValueError):
                # Skip result status icon if there's an issue
                pass

        return line

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        # iterate over the rows of the stages dataframe
        for index, row in self.stages.iterrows():
            grid.add_row(
                self.__generate_line(row)
            )
        grid.add_row('')
        title = '[b honeydew2]flow[/b honeydew2]'
        title = f'{title} {StatusEnum.get_icon(self.status, color=True)}'
        return Panel(grid, title=title, border_style="blue", title_align='left', style='')


class ExperimentRunActionsPanel:
    actions: pd.DataFrame
    status: int

    def __init__(self, status: int, actions: pd.DataFrame):
        self.actions = actions
        self.status = status

    def __generate_action_line(self, row: pd.Series) -> str:
        """Generate a formatted line for an action, using success data from database."""
        from adare.frontend.terminal.action_display import format_action_message, get_action_display_info
        from adare.types.event_types import ActionType, event_type_resolver

        # Extract information from the row
        event_type = row.get('event_type', 'unknown')
        action_type_str = row.get('action_type')
        action_data = row.get('data', {})

        # Use the success and result_status from database instead of recomputing
        db_success = row.get('success')  # Boolean from database
        db_result_status = row.get('result_status')  # StatusEnum int for tests
        error_message = row.get('error')  # Error from database

        try:
            # Convert action_type string to ActionType enum
            if action_type_str:
                action_type = ActionType(action_type_str)
            else:
                # Fallback: try to determine from event_type
                resolved_event_type = event_type_resolver.resolve_event_type_from_name(event_type)
                action_type = event_type_resolver.get_action_type(resolved_event_type)

            # Use the exact same display logic as the live console
            display_info = get_action_display_info(action_type, action_data or {})
            # Prefer error from database, fallback to action_data
            if not error_message:
                error_message = (action_data.get('error_message') or action_data.get('error')) if action_data else None
            message = format_action_message(action_type, display_info, error_message)

            # Use database success and result_status values directly
            if db_success is None:
                # No success info available, show as pending
                status = StatusEnum.PENDING
                result_status = StatusEnum.PENDING
            elif db_success:
                # Execution succeeded
                status = StatusEnum.FINISHED
                # For tests, use the actual test result status
                if action_type == ActionType.TEST and db_result_status is not None:
                    result_status = db_result_status
                else:
                    result_status = StatusEnum.SUCCESS
            else:
                # Execution failed
                status = StatusEnum.FAILED
                result_status = StatusEnum.FAILED

            # Use the same logic as flow console: main status for primary icon
            icon = StatusEnum.get_icon(status, color=True)

        except (ValueError, Exception):
            # Fallback to generic message if anything goes wrong
            message = f"{event_type} action"
            icon = StatusEnum.get_icon(StatusEnum.PENDING, color=True)
            result_status = None

        # Format with proper indentation using display_level from database
        display_level = row.get('display_level', 0)  # Default to level 0 if not available
        level_offset = '  ' * display_level
        line = f'{level_offset}{icon} {message}'

        # Add result_status icon if available (for test events)
        # Show the test result icon for tests regardless of execution status
        if 'result_status' in locals() and result_status is not None and action_type == ActionType.TEST:
            result_icon = StatusEnum.get_icon(result_status, color=True)
            line = f'{line} {result_icon}'

        return line

    def _group_actions_by_id(self):
        """Group actions by action_id and organize hierarchically by parent relationships."""

        # Sort by timestamp to ensure proper ordering
        if 'timestamp' in self.actions.columns:
            sorted_actions = self.actions.sort_values('timestamp')
        else:
            sorted_actions = self.actions

        grouped = {}

        # First pass: group by event_group_id and prefer complete events
        for _, row in sorted_actions.iterrows():
            # Use event_group_id for universal grouping, fall back to action_id for backward compatibility
            event_group_id = row.get('event_group_id') or row.get('action_id')
            action_event_type = row.get('event_type_specific', '') or ''

            if not event_group_id:
                # If no grouping ID, treat as individual action
                event_group_id = row.get('id', len(grouped))

            if event_group_id not in grouped:
                grouped[event_group_id] = row
            else:
                existing_event_type = grouped[event_group_id].get('event_type_specific', '') or ''

                # Prefer complete events over start events for final display
                is_complete_event = ('complete' in action_event_type.lower() or
                                   row.get('status', 0) != 0)
                is_existing_complete = ('complete' in existing_event_type.lower() or
                                      grouped[event_group_id].get('status', 0) != 0)

                # Only replace if current event is complete and existing is not, or if both are complete but this is newer
                if is_complete_event and not is_existing_complete:
                    # Use the complete event but preserve the start event's timestamp for ordering
                    existing_timestamp = grouped[event_group_id].get('timestamp')
                    complete_row = row.copy()
                    if existing_timestamp and existing_timestamp < row.get('timestamp', 0):
                        complete_row['timestamp'] = existing_timestamp  # Use earlier timestamp for proper ordering
                    grouped[event_group_id] = complete_row
                elif is_complete_event and is_existing_complete:
                    # Both are complete events, keep the later one (more recent)
                    if row.get('timestamp', 0) > grouped[event_group_id].get('timestamp', 0):
                        grouped[event_group_id] = row

        # Second pass: organize hierarchically by parent relationships
        actions_by_id = {event_group_id: action for event_group_id, action in grouped.items()}
        parent_to_children = {}
        root_actions = []

        # Group actions by parent_event_id
        for event_group_id, action in actions_by_id.items():
            parent_event_id = action.get('parent_event_id')

            if parent_event_id:
                # Find the parent action by searching for action with matching event_group_id, action_id or id
                parent_action = None
                for _, paction in actions_by_id.items():
                    if (paction.get('event_group_id') == parent_event_id or
                        paction.get('action_id') == parent_event_id or
                        paction.get('id') == parent_event_id):
                        parent_action = paction
                        break

                if parent_action is not None:
                    parent_key = (parent_action.get('event_group_id') or
                                  parent_action.get('action_id') or
                                  parent_action.get('id'))
                    if parent_key not in parent_to_children:
                        parent_to_children[parent_key] = []
                    parent_to_children[parent_key].append(action)
                else:
                    # Parent not found, treat as root action
                    root_actions.append(action)
            else:
                # No parent, treat as root action
                root_actions.append(action)

        # Third pass: build hierarchical result with proper ordering
        def add_action_and_children(action, result, level=0):
            # Add the action itself
            result.append(action)

            # Add its children, sorted by timestamp
            action_key = (action.get('event_group_id') or
                         action.get('action_id') or
                         action.get('id'))
            if action_key in parent_to_children:
                children = parent_to_children[action_key]
                children.sort(key=lambda x: x.get('timestamp', 0))
                for child in children:
                    add_action_and_children(child, result, level + 1)

        # Build final result starting with root actions, sorted by timestamp
        result = []
        root_actions.sort(key=lambda x: x.get('timestamp', 0))
        for root_action in root_actions:
            add_action_and_children(root_action, result)

        return result

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)

        if self.actions.empty:
            grid.add_row('[dim]No actions executed[/dim]')
        else:
            # Group actions by action_id to consolidate start/complete pairs
            grouped_actions = self._group_actions_by_id()

            for action_data in grouped_actions:
                grid.add_row(self.__generate_action_line(action_data))

        grid.add_row('')
        title = '[b medium_turquoise]actions[/b medium_turquoise]'
        title = f'{title} {StatusEnum.get_icon(self.status, color=True)}'
        return Panel(grid, title=title, border_style="blue", title_align='left', style='')


def print_run(run_ulid: str, formatter=None, output_file=None, dual_output=False):
    from adare.exceptions import RunNotFoundError

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    console = DefaultConsole()

    with DataRetrievalApi() as api:
        data: pd.DataFrame = api.get_run(run_ulid)

        # Check if run exists
        if data.empty:
            raise RunNotFoundError(log, run_ulid)

        stages: pd.DataFrame = api.get_run_stages(run_ulid)
        actions_data: pd.DataFrame = api.get_run_actions(run_ulid)
        tests_data: dict = api.get_tests(run_ulid)

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            structured_data = {
                'id': run_ulid,
                'project_name': data['project_name'].values[0],
                'environment_name': data['environment_name'].values[0],
                'environment_id': data['environment_id'].values[0],
                'experiment_name': data['experiment_name'].values[0],
                'duration': str(data['duration'][0]) if not pd.isna(data['duration'][0]) else None,
                'timestamp_start': data['timestamp_start'].values[0],
                'timestamp_end': data['timestamp_end'].values[0],
                'vm': data['vm'].values[0].name if hasattr(data['vm'].values[0], 'name') else str(data['vm'].values[0]),
                'osinfo': data['osinfo'].values[0],
                'published': bool(data['published'].values[0]),
                'fake': bool(data['fake'].values[0]) if 'fake' in data.columns else False,
                'status': int(data['status'].values[0]),
                'result_status': int(data['result_status'].values[0]),
                'stages': stages.to_dict('records') if not stages.empty else [],
                'actions': actions_data.to_dict('records') if not actions_data.empty else [],
                'tests': tests_data
            }
            formatter.print_or_save(structured_data, output_file, dual_output)

            if not dual_output:
                return

        height_header = 7
        height_actions = len(actions_data) // 2 + 2
        height_stages = len(stages) + 2
        height_body = height_actions + height_stages
        height_total = height_header + height_body + 2

        layout = Layout(name='root')
        header = Layout(name='header', size=height_header)
        body = Layout(name='body')

        # Create three sections: flow, actions, tests - back to fixed ratios
        left_side = Layout(name='left_side', ratio=2)
        flow = Layout(name='flow')
        actions = Layout(name='actions')
        tests = Layout(name='tests', ratio=3)

        layout.split(
            header,
            body,
        )

        # Split the body into left side and tests
        layout['body'].split_row(
            left_side,
            tests,
        )


        left_side.split_column(
            Layout(flow, size=height_stages),
            Layout(actions, size=height_actions),
        )

        project_name = data['project_name'].values[0]
        environment_name = data['environment_name'].values[0]
        experiment_name = data['experiment_name'].values[0]
        experiment_ulid = run_ulid
        header.update(ExperimentRunHeader(
            experiment_name=experiment_name,
            experiment_ulid=run_ulid,
            environment_name=environment_name,
            environment_ulid=data['environment_id'].values[0],
            project_name=project_name,
            duration=data['duration'][0],
            start_time=data['timestamp_start'].values[0],
            end_time=data['timestamp_end'].values[0],
            vm=data['vm'].values[0].name,
            osinfo=data['osinfo'].values[0],
            published=data['published'].values[0],
            fake=bool(data['fake'].values[0]) if 'fake' in data.columns else False,
        ))

        title = f'[b gold3]{project_name}.{environment_name}.{experiment_name} - [i]{experiment_ulid}[/i][/b gold3]'
        panel = Panel(layout, title=title, border_style='blue', title_align='left', height=height_total)

        # Update each panel with their respective data
        tests.update(ExperimentRunTestsPanel(data['result_status'].values[0], tests_data))
        flow.update(ExperimentRunFlowPanel(data['status'].values[0], stages))
        actions.update(ExperimentRunActionsPanel(data['status'].values[0], actions_data))

        console.print(panel)


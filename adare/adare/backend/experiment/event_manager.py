"""
Event Manager for Playbook Controller

This module handles creation and management of action events for the flow console
display system. It provides clean separation of event handling from action execution.
"""

import logging
from typing import Any

from adare.types.actions import (
    ActionCompleteEvent,
    ActionStartEvent,
    BlockActionCompleteEvent,
    BlockActionStartEvent,
    ClickActionCompleteEvent,
    ClickActionStartEvent,
    CommandActionCompleteEvent,
    CommandActionStartEvent,
    ContinueActionCompleteEvent,
    ContinueActionStartEvent,
    DragActionCompleteEvent,
    DragActionStartEvent,
    ExecuteActionCompleteEvent,
    ExecuteActionStartEvent,
    FindActionCompleteEvent,
    FindActionStartEvent,
    GotoActionCompleteEvent,
    GotoActionStartEvent,
    IdleActionCompleteEvent,
    IdleActionStartEvent,
    KeyboardActionCompleteEvent,
    KeyboardActionStartEvent,
    LoopActionCompleteEvent,
    LoopActionStartEvent,
    PauseActionCompleteEvent,
    PauseActionStartEvent,
    PullActionCompleteEvent,
    PullActionStartEvent,
    PullChangedFilesActionCompleteEvent,
    PullChangedFilesActionStartEvent,
    SaveTimestampActionCompleteEvent,
    SaveTimestampActionStartEvent,
    ScreenshotActionCompleteEvent,
    ScreenshotActionStartEvent,
    ScrollActionCompleteEvent,
    ScrollActionStartEvent,
    SnapshotFilesystemActionCompleteEvent,
    SnapshotFilesystemActionStartEvent,
    StopActionCompleteEvent,
    StopActionStartEvent,
    TestActionCompleteEvent,
    TestActionStartEvent,
    WaitUntilActionCompleteEvent,
    WaitUntilActionStartEvent,
)
from adare.types.playbook import (
    ActionTestAction,
    ActionType,
    BlockAction,
    ClickAction,
    CommandAction,
    ContinueAction,
    DragAction,
    GotoAction,
    IdleAction,
    KeyboardAction,
    LoopAction,
    PauseAction,
    PullAction,
    PullChangedFilesAction,
    SaveTimestampAction,
    ScreenshotAction,
    ScrollAction,
    SnapshotFilesystemAction,
    StopAction,
    WaitUntilAction,
)

# Action event imports for flow console display
from adare.types.step_actions import ExecuteAction, FindAction

log = logging.getLogger(__name__)


class EventManager:
    """
    Manages creation and emission of action events for flow console display.

    This class handles all event creation logic that was previously in
    PlaybookController, providing clean separation of event handling concerns.
    """

    def __init__(self, experiment_run_id: str | None = None, playbook_items_map: dict[int, str] = None):
        """
        Initialize the event manager.

        Args:
            experiment_run_id: Experiment run ID for event tracking
            playbook_items_map: Maps action index to playbook_item_id for database integration
        """
        self.experiment_run_id = experiment_run_id
        self.playbook_items_map = playbook_items_map or {}

    def create_action_start_event(self, action: ActionType, action_index: int, action_id: str, parent_event_id: str = None):
        """Create appropriate start event for the given action type."""
        description = getattr(action, 'description', '')

        # Generate better description for CommandActions (always override for clean display)
        if isinstance(action, CommandAction):
            description = self._generate_command_description(action)

        # Always strip newlines from descriptions to prevent multiline display issues
        if description:
            description = ' '.join(description.split())

        # Common event data
        event_data = {
            'action_id': action_id,
            'action_description': description,
            'sequence_order': action_index,
            'playbook_item_id': self.playbook_items_map.get(action_index),
            'experiment_run_id': self.experiment_run_id,
            'parent_event_id': parent_event_id
        }

        # Dispatch to type-specific factory
        for action_cls, factory in self._start_event_factories():
            if isinstance(action, action_cls):
                return factory(action, event_data)

        # Generic start event for unknown action types
        return ActionStartEvent(**event_data)

    def _start_event_factories(self):
        """Yield (action_class, factory_callable) pairs for start events."""
        yield ClickAction, lambda a, d: ClickActionStartEvent(
            target_info=self._get_target_info(getattr(a, 'target', None)), **d)
        yield KeyboardAction, lambda a, d: KeyboardActionStartEvent(
            key=a.key if hasattr(a, 'key') else None,
            text=a.text if hasattr(a, 'text') else None,
            combination=a.combination if hasattr(a, 'combination') else None,
            keys=getattr(a, 'keys', None),
            **d)
        yield CommandAction, lambda a, d: CommandActionStartEvent(
            command=getattr(a, 'command', None), **d)
        yield ActionTestAction, lambda a, d: TestActionStartEvent(
            test_name=getattr(a, 'name', ''), **d)
        yield ScreenshotAction, lambda a, d: ScreenshotActionStartEvent(**d)
        yield ScrollAction, lambda a, d: ScrollActionStartEvent(
            direction=getattr(a, 'direction', None),
            amount=getattr(a, 'amount', None), **d)
        yield IdleAction, lambda a, d: IdleActionStartEvent(
            duration=getattr(a, 'duration', None), **d)
        yield DragAction, lambda a, d: DragActionStartEvent(
            source_target=self._get_target_info(getattr(a, 'src', None)),
            dest_target=self._get_target_info(getattr(a, 'dst', None)), **d)
        yield GotoAction, lambda a, d: GotoActionStartEvent(
            url=getattr(a, 'url', None), **d)
        yield BlockAction, lambda a, d: BlockActionStartEvent(
            action_count=len(getattr(a, 'actions', [])),
            conditions=self._get_condition_info(getattr(a, 'when', None)), **d)
        yield SaveTimestampAction, lambda a, d: SaveTimestampActionStartEvent(
            variable=getattr(a, 'variable', None), **d)
        yield PullAction, lambda a, d: PullActionStartEvent(
            source=getattr(a, 'src', None),
            destination=getattr(a, 'dst', None), **d)
        yield WaitUntilAction, self._create_wait_until_start_event
        yield LoopAction, self._create_loop_start_event
        yield PauseAction, lambda a, d: PauseActionStartEvent(
            message=getattr(a, 'message', None), **d)
        yield StopAction, lambda a, d: StopActionStartEvent(
            condition_info=self._extract_condition_info(a), **d)
        yield ContinueAction, lambda a, d: ContinueActionStartEvent(
            condition_info=self._extract_condition_info(a), **d)
        yield FindAction, lambda a, d: FindActionStartEvent(
            target_info=getattr(a, 'target_info', None), **d)
        yield ExecuteAction, lambda a, d: ExecuteActionStartEvent(
            coordinates=getattr(a, 'coordinates', None), **d)
        yield SnapshotFilesystemAction, lambda a, d: SnapshotFilesystemActionStartEvent(
            snapshot_type=getattr(a, 'snapshot_type', None), **d)
        yield PullChangedFilesAction, lambda a, d: PullChangedFilesActionStartEvent(
            destination=getattr(a, 'destination', None), **d)

    def create_action_complete_event(self, action: ActionType, action_index: int, action_id: str, result, parent_event_id: str = None):
        """Create appropriate complete event for the given action type and result."""
        description = getattr(action, 'description', '')

        # Generate better description for CommandActions (always override for clean display)
        if isinstance(action, CommandAction):
            description = self._generate_command_description(action)

        # Always strip newlines from descriptions to prevent multiline display issues
        if description:
            description = ' '.join(description.split())

        # Common event data
        event_data = {
            'action_id': action_id,
            'action_description': description,
            'sequence_order': action_index,
            'playbook_item_id': self.playbook_items_map.get(action_index),
            'experiment_run_id': self.experiment_run_id,
            'success': result.success,
            'execution_time': result.execution_time,
            'parent_event_id': parent_event_id
        }

        # Create type-specific complete event
        if isinstance(action, ClickAction):
            event = ClickActionCompleteEvent(coordinates=result.coordinates, target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, KeyboardAction):
            event = KeyboardActionCompleteEvent(
                key=result.data.get('key') if result.data else None,
                text=result.data.get('text') if result.data else None,
                combination=result.data.get('combination') if result.data else None,
                keys_sent=getattr(action, 'keys', None),  # Keep legacy field
                **event_data
            )
        elif isinstance(action, CommandAction):
            event = CommandActionCompleteEvent(
                command_executed=getattr(action, 'command', None),
                output=result.data.get('output') if result.data else None,
                return_code=result.data.get('return_code') if result.data else None,
                **event_data
            )
        elif isinstance(action, ActionTestAction):
            event = TestActionCompleteEvent(
                test_name=getattr(action, 'name', ''),
                test_output=result.data.get('result', {}).get('details') if result.data else None,
                result_category=result.data.get('result_category') if result.data else None,
                expect_to_fail=result.data.get('expect_to_fail', False) if result.data else False,
                **event_data
            )
        elif isinstance(action, ScreenshotAction):
            event = ScreenshotActionCompleteEvent(
                screenshot_path=result.data.get('screenshot_path') if result.data else None,
                **event_data
            )
        elif isinstance(action, ScrollAction):
            event = ScrollActionCompleteEvent(**event_data)
        elif isinstance(action, IdleAction):
            event = IdleActionCompleteEvent(actual_duration=result.execution_time, **event_data)
        elif isinstance(action, DragAction):
            event = DragActionCompleteEvent(
                source_coordinates=result.data.get('source_coordinates') if result.data else None,
                dest_coordinates=result.coordinates,
                **event_data
            )
        elif isinstance(action, GotoAction):
            event = GotoActionCompleteEvent(
                final_url=result.data.get('final_url') if result.data else None,
                **event_data
            )
        elif isinstance(action, BlockAction):
            event = BlockActionCompleteEvent(
                actions_executed=result.data.get('actions_executed', 0) if result.data else 0,
                **event_data
            )
        elif isinstance(action, SaveTimestampAction):
            event = SaveTimestampActionCompleteEvent(
                variable=getattr(action, 'variable', None),
                timestamp_value=result.data.get(getattr(action, 'variable', 'timestamp')) if result.data else None,
                **event_data
            )
        elif isinstance(action, PullAction):
            event = PullActionCompleteEvent(
                source=getattr(action, 'src', None),
                destination=getattr(action, 'dst', None),
                files_copied=result.data.get('files_copied') if result.data else None,
                total_size=result.data.get('total_size') if result.data else None,
                **event_data
            )
        elif isinstance(action, WaitUntilAction):
            # Extract target from condition (exists or not_exists)
            target = None
            if action.condition.exists:
                target = action.condition.exists
            elif action.condition.not_exists:
                target = action.condition.not_exists
            event = WaitUntilActionCompleteEvent(
                target_info=self._get_target_info(target),
                coordinates=result.coordinates,
                found=result.success,
                **event_data
            )
        elif isinstance(action, LoopAction):
            event = LoopActionCompleteEvent(
                iterations_completed=result.data.get('iterations') if result.data else None,
                actions_executed=result.data.get('actions_executed') if result.data else None,
                **event_data
            )
        elif isinstance(action, PauseAction):
            event = PauseActionCompleteEvent(
                user_input=result.data.get('user_input') if result.data else None,
                **event_data
            )
        elif isinstance(action, StopAction):
            event = StopActionCompleteEvent(
                condition_met=result.data.get('condition_met') if result.data else None,
                stopped_execution=result.data.get('should_stop', False) if result.data else False,
                **event_data
            )
        elif isinstance(action, ContinueAction):
            event = ContinueActionCompleteEvent(
                condition_met=result.data.get('condition_met') if result.data else None,
                skipped_remaining=result.data.get('should_continue', False) if result.data else False,
                **event_data
            )
        elif isinstance(action, FindAction):
            event = FindActionCompleteEvent(
                target_info=getattr(action, 'target_info', None),
                coordinates=result.coordinates,
                matched_text=result.data.get('matched_text') if result.data else None,
                **event_data
            )
        elif isinstance(action, ExecuteAction):
            event = ExecuteActionCompleteEvent(
                coordinates=result.coordinates,
                **event_data
            )
        elif isinstance(action, SnapshotFilesystemAction):
            event = SnapshotFilesystemActionCompleteEvent(
                snapshot_type=getattr(action, 'snapshot_type', None),
                files_count=result.data.get('files_count') if result.data else None,
                **event_data
            )
        elif isinstance(action, PullChangedFilesAction):
            event = PullChangedFilesActionCompleteEvent(
                destination=getattr(action, 'destination', None),
                files_pulled=result.data.get('files_pulled') if result.data else None,
                total_size=result.data.get('total_size') if result.data else None,
                **event_data
            )
        else:
            # Generic complete event for unknown action types
            event = ActionCompleteEvent(**event_data)

        return event

    def _get_target_info(self, target) -> dict[str, Any] | None:
        """Extract target information for event logging."""
        if not target:
            return None

        info = {}
        if hasattr(target, 'image') and target.image:
            info['image'] = target.image
        if hasattr(target, 'text') and target.text:
            info['text'] = target.text
        if hasattr(target, 'position') and target.position:
            info['position'] = target.position
        if hasattr(target, 'strategy') and target.strategy:
            strategy_name = target.strategy.__class__.__name__
            info['strategy'] = strategy_name
            # Add strategy parameters if available
            if hasattr(target.strategy, '__dict__'):
                import attrs
                if attrs.has(target.strategy):
                    strategy_params = attrs.asdict(target.strategy)
                    if strategy_params:
                        info['strategy_params'] = strategy_params

        return info if info else None

    def _generate_command_description(self, action: CommandAction) -> str:
        """Generate a clean, single-line description for command actions."""
        command = action.command.strip()

        # Always force single-line display by replacing any actual newlines with spaces
        command = ' '.join(command.split())

        # Special handling for heredoc commands (<<)
        if '<<' in command:
            # Extract the base command before heredoc
            base_cmd = command.split('<<')[0].strip()
            # Try to get the filename if it's a file creation command
            if 'cat >' in base_cmd or 'tee' in base_cmd:
                # Extract filename for better readability
                import re
                file_match = re.search(r'[>]\s*([^\s]+)', base_cmd)
                if file_match:
                    filename = file_match.group(1)
                    # Keep filename shorter to prevent flow console truncation
                    import os
                    basename = os.path.basename(filename)
                    return f"command: create file {basename}"

            # Truncate heredoc command
            if len(base_cmd) > 40:
                base_cmd = base_cmd[:37] + "..."
            return f"command: execute '{base_cmd}'"

        # Regular command truncation - always single line
        if len(command) > 40:
            return f"command: execute '{command[:37]}...'"
        return f"command: execute '{command}'"

    def _get_condition_info(self, conditions) -> dict[str, Any] | None:
        """Extract condition information for event logging."""
        if not conditions:
            return None

        # If conditions is a list, extract basic info from each
        if isinstance(conditions, list):
            return {
                'count': len(conditions),
                'types': [type(cond).__name__ for cond in conditions]
            }
        return {'type': type(conditions).__name__}

    def update_playbook_items_map(self, playbook_items_map: dict[int, str]):
        """Update the playbook items mapping."""
        self.playbook_items_map = playbook_items_map

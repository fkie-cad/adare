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

        # Dispatch to type-specific factory
        for action_cls, factory in self._complete_event_factories():
            if isinstance(action, action_cls):
                return factory(action, result, event_data)

        # Generic complete event for unknown action types
        return ActionCompleteEvent(**event_data)

    def _complete_event_factories(self):
        """Yield (action_class, factory_callable) pairs for complete events."""
        yield ClickAction, lambda a, r, d: ClickActionCompleteEvent(
            coordinates=r.coordinates,
            target_info=self._get_target_info(getattr(a, 'target', None)), **d)
        yield KeyboardAction, lambda a, r, d: KeyboardActionCompleteEvent(
            key=r.data.get('key') if r.data else None,
            text=r.data.get('text') if r.data else None,
            combination=r.data.get('combination') if r.data else None,
            keys_sent=getattr(a, 'keys', None),
            **d)
        yield CommandAction, lambda a, r, d: CommandActionCompleteEvent(
            command_executed=getattr(a, 'command', None),
            output=r.data.get('output') if r.data else None,
            return_code=r.data.get('return_code') if r.data else None,
            **d)
        yield ActionTestAction, lambda a, r, d: TestActionCompleteEvent(
            test_name=getattr(a, 'name', ''),
            test_output=r.data.get('result', {}).get('details') if r.data else None,
            result_category=r.data.get('result_category') if r.data else None,
            expect_to_fail=r.data.get('expect_to_fail', False) if r.data else False,
            **d)
        yield ScreenshotAction, lambda a, r, d: ScreenshotActionCompleteEvent(
            screenshot_path=r.data.get('screenshot_path') if r.data else None,
            **d)
        yield ScrollAction, lambda a, r, d: ScrollActionCompleteEvent(**d)
        yield IdleAction, lambda a, r, d: IdleActionCompleteEvent(
            actual_duration=r.execution_time, **d)
        yield DragAction, lambda a, r, d: DragActionCompleteEvent(
            source_coordinates=r.data.get('source_coordinates') if r.data else None,
            dest_coordinates=r.coordinates, **d)
        yield GotoAction, lambda a, r, d: GotoActionCompleteEvent(
            final_url=r.data.get('final_url') if r.data else None, **d)
        yield BlockAction, lambda a, r, d: BlockActionCompleteEvent(
            actions_executed=r.data.get('actions_executed', 0) if r.data else 0, **d)
        yield SaveTimestampAction, lambda a, r, d: SaveTimestampActionCompleteEvent(
            variable=getattr(a, 'variable', None),
            timestamp_value=r.data.get(getattr(a, 'variable', 'timestamp')) if r.data else None,
            **d)
        yield PullAction, lambda a, r, d: PullActionCompleteEvent(
            source=getattr(a, 'src', None),
            destination=getattr(a, 'dst', None),
            files_copied=r.data.get('files_copied') if r.data else None,
            total_size=r.data.get('total_size') if r.data else None,
            **d)
        yield WaitUntilAction, self._create_wait_until_complete_event
        yield LoopAction, lambda a, r, d: LoopActionCompleteEvent(
            iterations_completed=r.data.get('iterations') if r.data else None,
            actions_executed=r.data.get('actions_executed') if r.data else None,
            **d)
        yield PauseAction, lambda a, r, d: PauseActionCompleteEvent(
            user_input=r.data.get('user_input') if r.data else None, **d)
        yield StopAction, lambda a, r, d: StopActionCompleteEvent(
            condition_met=r.data.get('condition_met') if r.data else None,
            stopped_execution=r.data.get('should_stop', False) if r.data else False,
            **d)
        yield ContinueAction, lambda a, r, d: ContinueActionCompleteEvent(
            condition_met=r.data.get('condition_met') if r.data else None,
            skipped_remaining=r.data.get('should_continue', False) if r.data else False,
            **d)
        yield FindAction, lambda a, r, d: FindActionCompleteEvent(
            target_info=getattr(a, 'target_info', None),
            coordinates=r.coordinates,
            matched_text=r.data.get('matched_text') if r.data else None,
            **d)
        yield ExecuteAction, lambda a, r, d: ExecuteActionCompleteEvent(
            coordinates=r.coordinates, **d)
        yield SnapshotFilesystemAction, lambda a, r, d: SnapshotFilesystemActionCompleteEvent(
            snapshot_type=getattr(a, 'snapshot_type', None),
            files_count=r.data.get('files_count') if r.data else None,
            **d)
        yield PullChangedFilesAction, lambda a, r, d: PullChangedFilesActionCompleteEvent(
            destination=getattr(a, 'destination', None),
            files_pulled=r.data.get('files_pulled') if r.data else None,
            total_size=r.data.get('total_size') if r.data else None,
            **d)

    def _create_wait_until_start_event(self, action, event_data):
        """Create start event for WaitUntilAction."""
        target = self._extract_wait_until_target(action)
        return WaitUntilActionStartEvent(
            target_info=self._get_target_info(target),
            timeout=getattr(action, 'timeout', None),
            check_interval=getattr(action, 'check_interval', None),
            initial_delay=getattr(action, 'initial_delay', None),
            **event_data
        )

    def _create_wait_until_complete_event(self, action, result, event_data):
        """Create complete event for WaitUntilAction."""
        target = self._extract_wait_until_target(action)
        return WaitUntilActionCompleteEvent(
            target_info=self._get_target_info(target),
            coordinates=result.coordinates,
            found=result.success,
            **event_data
        )

    def _create_loop_start_event(self, action, event_data):
        """Create start event for LoopAction."""
        iteration_count = action.times if action.times is not None else (len(action.items) if action.items else None)
        return LoopActionStartEvent(
            iteration_count=iteration_count,
            items=action.items if hasattr(action, 'items') else None,
            **event_data
        )

    @staticmethod
    def _extract_condition_info(action) -> dict | None:
        """Extract condition info dict from StopAction or ContinueAction."""
        if hasattr(action, 'condition') and action.condition:
            return {'variable': action.condition.variable, 'has_condition': True}
        return None

    @staticmethod
    def _extract_wait_until_target(action):
        """Extract target from WaitUntilAction condition."""
        if action.condition.exists:
            return action.condition.exists
        if action.condition.not_exists:
            return action.condition.not_exists
        return None

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

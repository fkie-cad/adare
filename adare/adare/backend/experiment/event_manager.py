"""
Event Manager for Playbook Controller

This module handles creation and management of action events for the flow console
display system. It provides clean separation of event handling from action execution.
"""

import logging
from typing import Dict, List, Optional, Any
import time

from adare.types.playbook import (
    ActionType, ClickAction, DragAction,
    KeyboardAction, IdleAction, ScrollAction, GotoAction, 
    CommandAction, ScreenshotAction, BlockAction, ActionTestAction,
    SaveTimestampAction, PullAction
)

# Action event imports for flow console display
from adare.types.step_actions import FindAction, ExecuteAction
from adare.types.actions import (
    ClickActionStartEvent, ClickActionCompleteEvent,
    KeyboardActionStartEvent, KeyboardActionCompleteEvent,
    CommandActionStartEvent, CommandActionCompleteEvent,
    TestActionStartEvent, TestActionCompleteEvent,
    ScreenshotActionStartEvent, ScreenshotActionCompleteEvent,
    ScrollActionStartEvent, ScrollActionCompleteEvent,
    IdleActionStartEvent, IdleActionCompleteEvent,
    DragActionStartEvent, DragActionCompleteEvent,
    GotoActionStartEvent, GotoActionCompleteEvent,
    BlockActionStartEvent, BlockActionCompleteEvent,
    SaveTimestampActionStartEvent, SaveTimestampActionCompleteEvent,
    PullActionStartEvent, PullActionCompleteEvent,
    FindActionStartEvent, FindActionCompleteEvent,
    ExecuteActionStartEvent, ExecuteActionCompleteEvent
)

log = logging.getLogger(__name__)


class EventManager:
    """
    Manages creation and emission of action events for flow console display.
    
    This class handles all event creation logic that was previously in 
    PlaybookController, providing clean separation of event handling concerns.
    """
    
    def __init__(self, experiment_run_id: Optional[str] = None, playbook_items_map: Dict[int, str] = None):
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
        action_type = type(action).__name__
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
        
        # Create type-specific start event
        if isinstance(action, ClickAction):
            return ClickActionStartEvent(target_info=self._get_target_info(getattr(action, 'target', None)), **event_data)
        elif isinstance(action, KeyboardAction):
            return KeyboardActionStartEvent(keys=getattr(action, 'keys', None), **event_data)
        elif isinstance(action, CommandAction):
            return CommandActionStartEvent(command=getattr(action, 'command', None), **event_data)
        elif isinstance(action, ActionTestAction):
            return TestActionStartEvent(test_name=getattr(action, 'name', ''), **event_data)
        elif isinstance(action, ScreenshotAction):
            return ScreenshotActionStartEvent(**event_data)
        elif isinstance(action, ScrollAction):
            return ScrollActionStartEvent(
                direction=getattr(action, 'direction', None),
                amount=getattr(action, 'amount', None),
                **event_data
            )
        elif isinstance(action, IdleAction):
            return IdleActionStartEvent(duration=getattr(action, 'duration', None), **event_data)
        elif isinstance(action, DragAction):
            return DragActionStartEvent(
                source_target=self._get_target_info(getattr(action, 'src', None)),
                dest_target=self._get_target_info(getattr(action, 'dst', None)),
                **event_data
            )
        elif isinstance(action, GotoAction):
            return GotoActionStartEvent(url=getattr(action, 'url', None), **event_data)
        elif isinstance(action, BlockAction):
            return BlockActionStartEvent(
                action_count=len(getattr(action, 'actions', [])),
                conditions=self._get_condition_info(getattr(action, 'when', None)),
                **event_data
            )
        elif isinstance(action, SaveTimestampAction):
            return SaveTimestampActionStartEvent(variable=getattr(action, 'variable', None), **event_data)
        elif isinstance(action, PullAction):
            return PullActionStartEvent(
                source=getattr(action, 'src', None),
                destination=getattr(action, 'dst', None),
                **event_data
            )
        elif isinstance(action, FindAction):
            return FindActionStartEvent(target_info=getattr(action, 'target_info', None), **event_data)
        elif isinstance(action, ExecuteAction):
            return ExecuteActionStartEvent(coordinates=getattr(action, 'coordinates', None), **event_data)
        else:
            # Generic start event for unknown action types
            from adare.types.actions import ActionEvent
            return ActionEvent(**event_data)
    
    def create_action_complete_event(self, action: ActionType, action_index: int, action_id: str, result, parent_event_id: str = None):
        """Create appropriate complete event for the given action type and result."""
        action_type = type(action).__name__
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
            event = KeyboardActionCompleteEvent(keys_sent=getattr(action, 'keys', None), **event_data)
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
        elif isinstance(action, FindAction):
            event = FindActionCompleteEvent(
                target_info=getattr(action, 'target_info', None),
                coordinates=result.coordinates,
                **event_data
            )
        elif isinstance(action, ExecuteAction):
            event = ExecuteActionCompleteEvent(
                coordinates=result.coordinates,
                **event_data
            )
        else:
            # Generic complete event for unknown action types
            from adare.types.actions import ActionEvent
            event = ActionEvent(**event_data)
        
        return event
    
    def _get_target_info(self, target) -> Optional[Dict[str, Any]]:
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

        # Handle multiline commands (like heredoc)
        if '\n' in command:
            # For heredoc commands, extract the main command (first line)
            first_line = command.split('\n')[0].strip()

            # Check if it's a heredoc command
            if '<<' in first_line:
                # Extract the base command before heredoc
                base_cmd = first_line.split('<<')[0].strip()
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

                # Truncate base command aggressively to prevent flow console truncation
                if len(base_cmd) > 40:
                    base_cmd = base_cmd[:37] + "..."
                result = f"command: execute '{base_cmd}'"
                import logging
                log = logging.getLogger(__name__)
                log.error(f"CLAUDE: DEBUG - Returning command description: {repr(result)}")
                return result
            else:
                # Multi-line command without heredoc - be very aggressive with truncation
                if len(first_line) > 40:
                    first_line = first_line[:37] + "..."
                result = f"command: execute '{first_line}'"
                print(f"CLAUDE: DEBUG - Returning first_line description: {repr(result)}")
                return result
        else:
            # Single line command - be more aggressive with truncation
            if len(command) > 40:
                return f"command: execute '{command[:37]}...'"
            else:
                return f"command: execute '{command}'"
    
    def _get_condition_info(self, conditions) -> Optional[Dict[str, Any]]:
        """Extract condition information for event logging."""
        if not conditions:
            return None
        
        # If conditions is a list, extract basic info from each
        if isinstance(conditions, list):
            return {
                'count': len(conditions),
                'types': [type(cond).__name__ for cond in conditions]
            }
        else:
            return {'type': type(conditions).__name__}
    
    def update_playbook_items_map(self, playbook_items_map: Dict[int, str]):
        """Update the playbook items mapping."""
        self.playbook_items_map = playbook_items_map
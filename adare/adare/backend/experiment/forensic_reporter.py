"""
Forensic Report Generator for ADARE Experiments

This module generates forensic logs from completed experiment runs by querying
the database for all ActionEvent and TestEvent records. The forensic logs
provide a complete audit trail of GUI automation steps in YAML format.
"""

import logging
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import json

from sqlalchemy.orm import Session
from adare.database.models.experiment import ExperimentRun, ActionEvent, TestEvent, Event
from adare.database.api.experiment import ExperimentApi
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class ForensicReporter:
    """
    Generates forensic audit logs from experiment run database records.
    """

    def generate_forensic_report(self, experiment_run_id: str, output_path: Path) -> bool:
        """
        Generate forensic log for an experiment run and save to file.

        Args:
            experiment_run_id: ULID of the experiment run
            output_path: Path to save the forensic log YAML file

        Returns:
            True if report generated successfully, False otherwise
        """
        try:
            # Use ExperimentApi for database access
            with ExperimentApi() as api:
                # Query experiment run with relationships
                experiment_run = api._session.query(ExperimentRun).filter(
                    ExperimentRun.id == experiment_run_id
                ).first()

                if not experiment_run:
                    log.error(f"Experiment run {experiment_run_id} not found")
                    return False

                # Generate forensic data
                forensic_data = self._build_forensic_data(api._session, experiment_run)

            # Create output directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write YAML file
            with open(output_path, 'w') as f:
                yaml.dump(forensic_data, f, default_flow_style=False, sort_keys=False)

            log.info(f"Forensic report generated: {output_path}")
            return True

        except Exception as e:
            log.error(f"Failed to generate forensic report for run {experiment_run_id}: {e}")
            return False

    def _build_forensic_data(self, session: Session, experiment_run: ExperimentRun) -> Dict[str, Any]:
        """Build the forensic data structure from database records."""

        # Query all events for this run, ordered by timestamp
        events = session.query(Event).filter(
            Event.experiment_run_id == experiment_run.id
        ).order_by(Event.timestamp).all()

        # Build experiment metadata
        experiment_info = {
            'experiment_id': experiment_run.experiment.id if experiment_run.experiment else None,
            'experiment_run_id': experiment_run.id,
            'experiment_name': experiment_run.experiment.name if experiment_run.experiment else 'unknown',
            'environment_name': experiment_run.environment.name if experiment_run.environment else 'unknown',
            'start_time': experiment_run.timestamp_start.isoformat() + 'Z' if experiment_run.timestamp_start else None,
            'end_time': experiment_run.timestamp_end.isoformat() + 'Z' if experiment_run.timestamp_end else None
        }

        # Process events into forensic actions
        actions = []
        sequence = 1

        for event in events:
            action_entry = self._process_event_to_action(event, sequence)
            if action_entry:
                actions.append(action_entry)
                sequence += 1

        return {
            'forensic_log_version': '1.0',
            'experiment_info': experiment_info,
            'actions': actions
        }

    def _process_event_to_action(self, event: Event, sequence: int) -> Optional[Dict[str, Any]]:
        """Convert a database event record to forensic action entry."""

        try:
            # Extract basic event information
            action_entry = {
                'sequence': sequence,
                'timestamp': event.timestamp.isoformat() + 'Z' if event.timestamp else None,
                'action_type': self._determine_action_type(event),
                'action_description': getattr(event, 'event_type_specific', '') or 'action',
                'result': 'success' if event.success else 'failed' if event.success is not None else 'unknown'
            }

            # Add result details
            result_details = self._extract_result_details(event)
            if result_details:
                action_entry['result_details'] = result_details

            # Add target information for applicable action types
            target_info = self._extract_target_info(event)
            if target_info:
                action_entry['target'] = target_info

            # Add screenshot reference if available in database
            screenshot_path = self._extract_screenshot_path_from_database(event)
            if screenshot_path:
                if 'result_details' not in action_entry:
                    action_entry['result_details'] = {}
                action_entry['result_details']['screenshot'] = screenshot_path

            return action_entry

        except Exception as e:
            log.warning(f"Failed to process event {event.id}: {e}")
            return None

    def _determine_action_type(self, event: Event) -> str:
        """Determine the action type from event data."""
        if isinstance(event, TestEvent):
            return 'test'
        elif isinstance(event, ActionEvent):
            return event.action_type or 'action'
        else:
            return event.event_type or 'event'

    def _extract_result_details(self, event: Event) -> Dict[str, Any]:
        """Extract result details from event."""
        result_details = {}

        # Add execution time if available
        if hasattr(event, 'execution_time') and event.execution_time is not None:
            result_details['execution_time_ms'] = event.execution_time

        # Add error message if present
        if hasattr(event, 'error') and event.error:
            result_details['error'] = event.error

        # Process ActionEvent specific data
        if isinstance(event, ActionEvent) and hasattr(event, 'action_data') and event.action_data:
            try:
                action_data = json.loads(event.action_data) if isinstance(event.action_data, str) else event.action_data

                # Extract coordinates
                if 'coordinates' in action_data:
                    result_details['coordinates'] = action_data['coordinates']

                # Extract command output
                if 'output' in action_data:
                    result_details['output'] = action_data['output']

                # Extract return code for commands
                if 'return_code' in action_data:
                    result_details['return_code'] = action_data['return_code']

                # Extract text for keyboard actions
                if 'text_entered' in action_data:
                    result_details['text_entered'] = action_data['text_entered']
                elif 'keys_sent' in action_data:
                    result_details['keys_sent'] = action_data['keys_sent']

            except (json.JSONDecodeError, TypeError) as e:
                log.debug(f"Could not parse action_data for event {event.id}: {e}")

        # Process TestEvent specific data
        if isinstance(event, TestEvent):
            if hasattr(event, 'result') and event.result:
                result_details['status'] = self._get_status_name(event.result.status_id) if hasattr(event.result, 'status_id') else 'unknown'
                if hasattr(event.result, 'details') and event.result.details:
                    result_details['details'] = event.result.details

            if hasattr(event, 'abstract_test') and event.abstract_test:
                result_details['test_name'] = event.abstract_test.name

                # Extract testfunction information
                if hasattr(event.abstract_test, 'testfunction') and event.abstract_test.testfunction:
                    result_details['testfunction'] = event.abstract_test.testfunction.dotnotation

                # Extract test parameters
                if hasattr(event.abstract_test, 'parameters') and event.abstract_test.parameters:
                    parameters = {}
                    for param_entry in event.abstract_test.parameters:
                        if hasattr(param_entry, 'parameter') and hasattr(param_entry, 'value'):
                            parameters[param_entry.parameter.name] = param_entry.value
                    if parameters:
                        result_details['parameters'] = parameters

        # Add generic message
        if not result_details.get('error'):
            if event.success:
                result_details['message'] = f"{self._determine_action_type(event).title()} executed successfully"
            elif event.success is False:
                result_details['message'] = f"{self._determine_action_type(event).title()} execution failed"
            else:
                result_details['message'] = f"{self._determine_action_type(event).title()} execution completed"

        return result_details

    def _extract_target_info(self, event: Event) -> Optional[Dict[str, Any]]:
        """Extract target information from event as YAML structure."""
        if isinstance(event, ActionEvent) and hasattr(event, 'action_data') and event.action_data:
            try:
                action_data = json.loads(event.action_data) if isinstance(event.action_data, str) else event.action_data

                # Extract target information
                if 'target_info' in action_data:
                    target_info = action_data['target_info']
                    if isinstance(target_info, dict):
                        target = {}
                        if 'image' in target_info:
                            target['image'] = target_info['image']
                        elif 'text' in target_info:
                            target['text'] = target_info['text']
                        elif 'position' in target_info:
                            target['position'] = target_info['position']
                        return target

                # Extract command for command actions - return as command target
                if 'command' in action_data:
                    return {'command': action_data['command']}

            except (json.JSONDecodeError, TypeError):
                pass

        # For test events, use test name
        if isinstance(event, TestEvent) and hasattr(event, 'abstract_test') and event.abstract_test:
            return {'test_name': event.abstract_test.name}

        return None

    def _extract_screenshot_path_from_database(self, event: Event) -> Optional[str]:
        """Extract screenshot file path from database action data."""
        if isinstance(event, ActionEvent) and hasattr(event, 'action_data') and event.action_data:
            try:
                action_data = json.loads(event.action_data) if isinstance(event.action_data, str) else event.action_data

                # Extract screenshot path from action data
                if 'screenshot_path' in action_data:
                    return action_data['screenshot_path']

            except (json.JSONDecodeError, TypeError):
                pass

        return None

    def _get_status_name(self, status_id: str) -> str:
        """Convert status ID to readable status name."""
        try:
            status_enum = StatusEnum(int(status_id))
            if status_enum == StatusEnum.SUCCESS:
                return 'PASSED'
            elif status_enum == StatusEnum.FAILED:
                return 'FAILED'
            elif status_enum == StatusEnum.ERROR:
                return 'ERROR'
            elif status_enum == StatusEnum.WARNING:
                return 'WARNING'
            else:
                return 'UNKNOWN'
        except (ValueError, TypeError):
            return 'UNKNOWN'


def generate_forensic_report_for_run(experiment_run_id: str, forensic_log_path: Path) -> bool:
    """
    Convenience function to generate forensic report for an experiment run.

    Args:
        experiment_run_id: ULID of the experiment run
        forensic_log_path: Path to save the forensic log file

    Returns:
        True if report generated successfully, False otherwise
    """
    reporter = ForensicReporter()
    return reporter.generate_forensic_report(experiment_run_id, forensic_log_path)
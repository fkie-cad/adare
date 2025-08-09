# external imports
from pathlib import Path
from threading import Lock
import ulid

# internal imports
from adare.database.models.experiment import EventFactory, Event as ModelEvent, ExperimentRun, Result as ModelResult
from adare.database.api.experiment import ExperimentApi
from adare.config import database as config_database
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)

lock = Lock()


def replace_list_recursive_in_dict(d: dict):
    for key, value in d.items():
        if isinstance(value, dict):
            replace_list_recursive_in_dict(value)
        elif isinstance(value, list):
            d[key] = ' '.join(value)


class EventDbApi(ExperimentApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def get_or_create_test_result(self, test_result_data: dict):
        test_result = self._session.query(ModelResult).filter_by(**test_result_data).first()
        if not test_result:
            test_result = ModelResult(**test_result_data)
            self._session.add(test_result)
            self._session.commit()
        return test_result


    def add_action_event(self, action_data: dict, action_id: str, experiment_run_ulid: str, parent_event_id: str = None):
        """
        Add an action event to the database.
        
        Args:
            action_data: Dictionary containing action event data
            action_id: Unique identifier for this action
            experiment_run_ulid: Experiment run ULID
            parent_event_id: Optional parent event ID for nested actions
        """
        import json
        from datetime import datetime, timezone
        from adare.types.event_types import event_type_resolver
        
        with lock:
            try:
                # Check if experiment run exists
                experiment_run = self._session.query(ExperimentRun).filter_by(ulid=experiment_run_ulid).first()
                if not experiment_run:
                    log.error(f'No experiment run found for ULID {experiment_run_ulid}')
                    return
                
                # Use event type resolver to determine action type and event type
                event_type = event_type_resolver.resolve_event_type(action_data)
                action_type = event_type_resolver.get_action_type(event_type)
                
                # Create ActionEvent
                model_event = EventFactory.create_event('action',
                    id=str(ulid.ULID()),
                    event_type='action_event',
                    experiment_run_id=experiment_run_ulid,
                    timestamp=datetime.now(timezone.utc),
                    parent_event_id=parent_event_id,
                    action_type=action_type.value,
                    event_type_specific=event_type.value,  # Store specific event type in base Event field
                    action_id=action_id,  # Keep for backward compatibility
                    event_group_id=action_id,  # Use action_id as the universal grouping field
                    success=action_data.get('success'),
                    error=action_data.get('error_message'),  # Use Event.error field
                    execution_time=action_data.get('execution_time'),
                    action_data=json.dumps(action_data)  # Serialize action data as JSON
                )
                
                self._session.add(model_event)
                self._session.commit()
                log.info(f'Added action event {model_event.ulid} ({action_type.value}) to experiment run {experiment_run_ulid}')
                
            except Exception as e:
                log.error(f'Failed to add action event: {e}', exc_info=True)
                self._session.rollback()

    def add_test_event(self, action_data: dict, action_id: str, experiment_run_ulid: str, parent_event_id: str = None):
        """
        Add a test event to the database as a TestEvent (now stores both start and complete events).
        
        Args:
            action_data: Dictionary containing test event data
            action_id: Unique identifier for this action
            experiment_run_ulid: Experiment run ULID
            parent_event_id: Optional parent event ID for nested test actions
        """
        import json
        from datetime import datetime, timezone
        from adare.types.event_types import event_type_resolver
        
        with lock:
            try:
                # Check if experiment run exists
                experiment_run = self._session.query(ExperimentRun).filter_by(ulid=experiment_run_ulid).first()
                if not experiment_run:
                    log.error(f'No experiment run found for ULID {experiment_run_ulid}')
                    return
                
                # Use event type resolver to determine event type
                event_type = event_type_resolver.resolve_event_type(action_data)
                is_complete = event_type_resolver.is_complete_event(event_type)
                
                # Extract test name from action data
                test_name = action_data.get('test_name')
                if not test_name:
                    log.warning(f'No test_name found in action_data for test event {action_id}')
                    return
                
                # Try to find existing AbstractTest for this test name in the experiment
                experiment = experiment_run.experiment
                abstract_test = None
                if experiment and experiment.abstract_tests:
                    for test in experiment.abstract_tests:
                        if test.name == test_name:
                            abstract_test = test
                            break
                
                if not abstract_test:
                    log.warning(f'No AbstractTest found with name "{test_name}" in experiment {experiment.id if experiment else "None"}')
                
                # Create or update result based on test success (only for complete events)
                test_result = None
                success = action_data.get('success')
                if is_complete and success is not None:
                    # Create a Result object for the test
                    test_result = self.get_or_create_test_result({
                        'status': StatusEnum.SUCCESS if success else StatusEnum.FAILED,
                        'details': action_data.get('error_message') or action_data.get('test_output'),
                    })
                
                # Create TestEvent with specific event type information (like ActionEvent)
                model_event = EventFactory.create_event('test',
                    id=str(ulid.ULID()),
                    event_type='test_event',
                    experiment_run_id=experiment_run_ulid,
                    timestamp=datetime.now(timezone.utc),
                    parent_event_id=parent_event_id,
                    event_type_specific=event_type.value,  # Store specific event type like TEST_START/TEST_COMPLETE
                    event_group_id=action_id,  # Use action_id as the universal grouping field
                    success=success,
                    execution_time=action_data.get('execution_time'),
                    abstract_test=abstract_test,
                    result=test_result
                )
                
                self._session.add(model_event)
                self._session.commit()
                
                event_description = "start" if not is_complete else f"complete (success: {success})"
                log.info(f'Added test event {model_event.ulid} ({event_description}) for test: {test_name} to experiment run {experiment_run_ulid}')
                
            except Exception as e:
                log.error(f'Failed to add test event: {e}', exc_info=True)
                self._session.rollback()

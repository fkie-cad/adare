# external imports
import attrs
from datetime import datetime

# internal imports
from adare.database.models.experiment import EventFactory, Event as ModelEvent, ExperimentRun, Result as ModelResult
from adare.database.api.experiment import ExperimentApi
from adarelib.types import EventSystemData
from adarelib.config import TIMESTAMP_FORMAT

# configure logging
import logging

log = logging.getLogger(__name__)


def replace_list_recursive_in_dict(d: dict):
    for key, value in d.items():
        if isinstance(value, dict):
            replace_list_recursive_in_dict(value)
        elif isinstance(value, list):
            d[key] = ' '.join(value)


class EventDbApi(ExperimentApi):

    def get_or_create_test_result(self, test_result_data: dict):
        test_result = self._session.query(ModelResult).filter_by(**test_result_data).first()
        if not test_result:
            test_result = ModelResult(**test_result_data)
            self._session.add(test_result)
            self._session.commit()
        return test_result

    def update_events(self, experiment_run_uuid: str, eventsystem: EventSystemData):
        experiment_run = self._session.query(ExperimentRun).filter_by(uuid=experiment_run_uuid).first()
        if not experiment_run:
            log.error(f'no experiment run found for uuid {experiment_run_uuid}')
            return
        num_events_eventsystem = len(eventsystem.events)
        event_uuids_db = [event.uuid for event in experiment_run.events]
        if num_events_eventsystem == len(event_uuids_db):
            log.info(f'events for experiment run {experiment_run_uuid} are already up to date')
            return
        elif num_events_eventsystem < len(event_uuids_db):
            log.error(f'eventsystem has less events than experiment run {experiment_run_uuid}')
            return
        else:
            log.info(f'updating events for experiment run {experiment_run_uuid}')
            for event in eventsystem.events:
                if self._session.query(ModelEvent).filter_by(uuid=event.uuid).first():
                    continue
                event_data = attrs.asdict(event)
                # rename category to event_type
                event_type = event_data.pop('category')
                replace_list_recursive_in_dict(event_data)
                # convert string to datetime object
                event_data['timestamp'] = datetime.strptime(event_data['timestamp'], TIMESTAMP_FORMAT)
                event_data['experiment_run_id'] = experiment_run_uuid
                if event_data.get('result'):
                    result = self.get_or_create_test_result(event_data.pop('result'))
                    if result:
                        event_data['result_id'] = result.id
                    else:
                        log.fatal(f'could not create test result for event {event.uuid}')
                model_event: ModelEvent = EventFactory.create_event(event_type, **event_data)
                self._session.add(model_event)
                log.info(f'added event {model_event.uuid} to experiment run {experiment_run_uuid}')
            self._session.commit()
            log.info(f'updated events for experiment run {experiment_run_uuid}')

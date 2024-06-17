# external imports
import attrs
from datetime import datetime
import sqlalchemy.orm
import queue
from pathlib import Path
from threading import Lock

# internal imports
from adare.database.models.experiment import EventFactory, Event as ModelEvent, ExperimentRun, Result as ModelResult, Stage, StageInRun
from adare.database.api.experiment import ExperimentApi
from adarelib.types.event import EventSystemData
from adare.config import database as config_database
from adarelib.config import TIMESTAMP_FORMAT, StatusEnum

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

    def __update_stage(self, event: ModelEvent, experiment_run: ExperimentRun):
        if not (stage_db := self._session.query(Stage).filter(Stage.name == f'box.experiment.{event.category}').first()):
            log.warning(f"Stage '{event.event_type}' not found in database")
            return
        # find stage in run in running events
        group_event = self._session.query(ModelEvent) \
            .filter(ModelEvent.group_id == event.group_id,
                    ModelEvent.experiment_run_id == experiment_run.ulid,
                    ModelEvent.ulid != event.ulid) \
            .first()
        if not group_event:
            kwargs = {
                'stage_id': stage_db.id,
                'run_id': experiment_run.ulid,
                'start_time': event.timestamp,
                'sub_msg': event.stage_submessage,
            }
            if event.status != StatusEnum.RUNNING:
                kwargs['end_time'] = event.timestamp
                kwargs['status'] = event.status
                kwargs['result_status'] = event.stage_result
            # create new stage in run
            stage_in_run = StageInRun(**kwargs)
            self._session.add(stage_in_run)
            event.stage_in_run = stage_in_run
            log.info(f"added stage '{event.event_type}' to run {experiment_run.ulid}")
        else:
            if group_event.stage_in_run:
                # update stage in run
                if event.status != StatusEnum.RUNNING:
                    group_event.stage_in_run.end_time = event.timestamp
                    group_event.stage_in_run.status = event.status
                    group_event.stage_in_run.result_status = event.stage_result
                    log.info(f"stage '{event.event_type}' finished with result {event.stage_result}")
                group_event.stage_in_run.sub_msg = event.stage_submessage
                log.info(f"updated stage '{event.event_type}' in run {experiment_run.ulid}")
        self._session.commit()

    def update_events(self, experiment_run_ulid: str, eventsystem: EventSystemData):
        with lock:
            experiment_run = self._session.query(ExperimentRun).filter_by(ulid=experiment_run_ulid).first()
            if not experiment_run:
                log.error(f'no experiment run found for ulid {experiment_run_ulid}')
                return
            num_events_eventsystem = len(eventsystem.events)
            event_ulids_db = [event.ulid for event in experiment_run.events]
            if num_events_eventsystem == len(event_ulids_db):
                log.info(f'events for experiment run {experiment_run_ulid} are already up to date')
                return
            elif num_events_eventsystem < len(event_ulids_db):
                log.error(f'eventsystem has less events than experiment run {experiment_run_ulid}')
                return
            else:
                log.info(f'updating events for experiment run {experiment_run_ulid}')
                for event in eventsystem.events:
                    if self._session.query(ModelEvent).filter_by(ulid=event.ulid).first():
                        continue
                    event_data = attrs.asdict(event)
                    # rename category to event_type
                    category = event_data.pop('category')
                    replace_list_recursive_in_dict(event_data)
                    # convert string to datetime object
                    event_data['timestamp'] = datetime.strptime(event_data['timestamp'], TIMESTAMP_FORMAT)
                    event_data['experiment_run_id'] = experiment_run_ulid
                    if event_data.get('result'):
                        result = self.get_or_create_test_result(event_data.pop('result'))
                        if result:
                            event_data['result'] = result
                        else:
                            log.fatal(f'could not create test result for event {event.ulid}')
                    model_event: ModelEvent = EventFactory.create_event(category, **event_data)
                    self._session.add(model_event)
                    log.info(f'added event {model_event.ulid} to experiment run {experiment_run_ulid}')
                    if model_event.stage:
                        stage_in_run = self.__update_stage(model_event, experiment_run)
                self._session.commit()
                log.info(f'updated events for experiment run {experiment_run_ulid}')

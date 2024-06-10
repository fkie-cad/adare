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
    stage_in_run_id: int

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        self.stage_in_run_id = -1

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
        if self.stage_in_run_id < 0:
            kwargs = {
                'stage_id': stage_db.id,
                'run_id': experiment_run.uuid,
                'start_time': event.timestamp,
                'sub_msg': event.stage_submessage,
            }
            if event.status == StatusEnum.FINISHED:
                kwargs['end_time'] = event.timestamp
                kwargs['status'] = StatusEnum.SUCCESS
                kwargs['result_status'] = event.stage_result

            # create new stage in run
            stage_in_run = StageInRun(**kwargs)
            self._session.add(stage_in_run)
            self._session.commit()
            if event.status != StatusEnum.FINISHED:
                self.stage_in_run_id = stage_in_run.id
            log.info(f"added stage '{event.event_type}' to run {experiment_run.uuid}")
        else:
            stage_in_run = self._session.query(StageInRun).filter_by(id=self.stage_in_run_id).first()
            if not stage_in_run:
                log.error(f"stage in run with id {self.stage_in_run_id} not found")
                return
            # update stage in run
            if event.status == StatusEnum.FINISHED:
                stage_in_run.end_time = event.timestamp
                stage_in_run.status = StatusEnum.SUCCESS
                stage_in_run.result_status = event.stage_result
                log.info(f"stage '{event.event_type}' finished with result {event.stage_result}")
                self.stage_in_run_id = -1
            stage_in_run.sub_msg = event.stage_submessage
            log.info(f"updated stage '{event.event_type}' in run {experiment_run.uuid}")
            self._session.commit()

    def update_events(self, experiment_run_uuid: str, eventsystem: EventSystemData):
        with lock:
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
                    category = event_data.pop('category')
                    replace_list_recursive_in_dict(event_data)
                    # convert string to datetime object
                    event_data['timestamp'] = datetime.strptime(event_data['timestamp'], TIMESTAMP_FORMAT)
                    event_data['experiment_run_id'] = experiment_run_uuid
                    if event_data.get('result'):
                        result = self.get_or_create_test_result(event_data.pop('result'))
                        if result:
                            event_data['result'] = result
                        else:
                            log.fatal(f'could not create test result for event {event.uuid}')
                    model_event: ModelEvent = EventFactory.create_event(category, **event_data)
                    self._session.add(model_event)
                    log.info(f'added event {model_event.uuid} to experiment run {experiment_run_uuid}')
                    if model_event.stage:
                        self.__update_stage(model_event, experiment_run)
                self._session.commit()
                log.info(f'updated events for experiment run {experiment_run_uuid}')

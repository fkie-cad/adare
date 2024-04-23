# external imports
import attrs

# internal imports
from adare.database.models.experiment import Event as ModelEvent, ExperimentRun
from adare.database.api.experiment import ExperimentApi
from adarelib.types import EventSystemData

# configure logging
import logging

log = logging.getLogger(__name__)


class EventDbApi(ExperimentApi):

    def update_events(self, experiment_run_uuid: str, eventsystem: EventSystemData):
        experiment_run = self._session.query(ExperimentRun).filter_by(uuid=experiment_run_uuid).first()
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
                event_data = attrs.asdict(event)
                # rename category to event_type
                event_data['event_type'] = event_data.pop('category')
                for key, value in event_data.items():
                    if isinstance(value, list):
                        event_data[key] = ' '.join(value)
                model_event = ModelEvent(
                    experiment_run_id=experiment_run.uuid,
                    # add event data as keyword arguments
                    **event_data
                )
                self._session.add(model_event)
                log.info(f'added event {model_event.uuid} to experiment run {experiment_run_uuid}')
            self._session.commit()
            log.info(f'updated events for experiment run {experiment_run_uuid}')

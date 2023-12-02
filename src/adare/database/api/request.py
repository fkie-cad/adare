# external imports
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.experiments import Scenario, PublishStatus, Experiment, Request
from adare.database.api.database import DatabaseApi
from adare.database.models.experiments import Base as BaseExperiments

# configure logging
import logging
log = logging.getLogger(__name__)



class RequestSessionApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        BaseExperiments.metadata.create_all(self.engine)


    def __enter__(self):
        super().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def add_request(self, req_type: str, title: str = '', description: str = '', experiment_uuid: str = None, scenario_uuid: str = None):
        if req_type not in ['experiment', 'scenario']:
            log.error(f'invalid request type {req_type}')
            return None, 'invalid request type'
        # add request to database (with status 'open')
        status_obj = self._session.query(PublishStatus).filter_by(name='not published').first()
        if not status_obj:
            log.error(f'publish status "not published" not found in database')
            return None, 'publish status "not published" not found in database'
        # get experiment and scenario objects
        experiment_obj = None
        scenario_obj = None
        if experiment_uuid:
            experiment_obj = self._session.query(Experiment).filter_by(uuid=experiment_uuid).first()
        if scenario_uuid:
            scenario_obj = self._session.query(Scenario).filter_by(uuid=scenario_uuid).first()
        if not experiment_obj and not scenario_obj:
            log.error(f'could not find experiment or scenario with uuid {experiment_uuid if experiment_uuid else scenario_uuid}')
            return None, f'could not find experiment or scenario with uuid {experiment_uuid if experiment_uuid else scenario_uuid}'
        req = Request(title=title, description=description, type=req_type, experiment=experiment_obj, scenario=scenario_obj, status=status_obj)
        self._session.add(req)
        self._session.commit()
        log.debug(f'added request to database (uuid: {req.uuid}, type: {req_type})')
        return req.uuid, ''

    def get_request_by_uuid(self, uuid: str):
        return self._session.query(Request).filter_by(uuid=uuid).first()

    def get_all_requests(self):
        all_requests = self._session.query(Request).all()
        log.debug(f'got all requests from database (count: {len(all_requests)})')
        return all_requests
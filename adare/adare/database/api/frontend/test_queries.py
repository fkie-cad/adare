"""Mixin for test and testfunction related queries."""

import logging

from adare.database.models.project_models import Event, Experiment, Status

log = logging.getLogger(__name__)


class TestQueryMixin:
    """Mixin providing test and testfunction query methods."""

    def get_tests(self, run_ulid: str) -> dict:
        tests_data = {}
        test_events = self._project_api._session.query(Event).filter_by(experiment_run_id=run_ulid).filter(Event.category == 'test').all()
        for event in test_events:
            if event.abstract_test.name not in tests_data:
                pinned_fv = getattr(event.abstract_test, 'testfunction_file_version', None)
                executed_fv = getattr(event, 'testfunction_file_version', None)
                drift = None
                if pinned_fv is not None and executed_fv is not None:
                    drift = (
                        pinned_fv != executed_fv
                        or event.abstract_test.testfunction_file_sha256 != event.testfunction_file_sha256
                        or event.abstract_test.testfunction_version != event.testfunction_version
                    )
                tests_data[event.abstract_test.name] = {
                    'name': event.abstract_test.name,
                    'description': event.abstract_test.description,
                    'testfunction_name': event.abstract_test.testfunction.dotnotation,
                    'testfunction_description': event.abstract_test.testfunction.description,
                    'testfunction_file': getattr(event, 'testfunction_file_name', None),
                    'testfunction_file_version': executed_fv,
                    'testfunction_drift': drift,
                    'result_status': int(event.stage_result) if event.result else None,
                    'result_details': event.result.details if event.result else None,
                    'result_status_name': self._project_api._session.query(Status).filter_by(id=event.result.status).one().name if event.result else None,
                }
                parameter_data = [
                    {
                        'name': parameter.parameter.name,
                        'dtype': parameter.parameter.dtype,
                        'value': parameter.value,
                    }
                    for parameter in event.abstract_test.parameters
                ]
                tests_data[event.abstract_test.name]['parameters'] = parameter_data
            else:
                # update results
                tests_data[event.abstract_test.name]['result_status'] = int(event.stage_result)
                tests_data[event.abstract_test.name]['result_details'] = event.result.details
                tests_data[event.abstract_test.name]['result_status_name'] = self._project_api._session.query(Status).filter_by(id=event.result.status).one().name
        return tests_data

    def get_abstract_tests(self, experiment_ulid: str) -> dict:
        experiment = self._project_api._session.query(Experiment).filter_by(id=experiment_ulid).one()
        tests = experiment.abstract_tests
        tests_data = {}
        for test in tests:
            tests_data[test.name] = {
                'name': test.name,
                'description': test.description,
                'testfunction_name': test.testfunction.dotnotation,
                'testfunction_description': test.testfunction.description,
                'parameters': [
                    {
                        'name': parameter.parameter.name if parameter.parameter else parameter.parameter_id,
                        'dtype': parameter.parameter.dtype if parameter.parameter else 'unknown',
                        'value': parameter.value,
                    }
                    for parameter in test.parameters
                    if parameter is not None
                ],
            }
        return tests_data

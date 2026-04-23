"""Mixin for test and testfunction related queries."""

import logging

import pandas as pd
import sqlalchemy

from adare.database.models.global_models import (
    Project,
    TestFunction,
    TestFunctionFile,
    TestParameter,
)
from adare.database.models.project_models import Event, Experiment, Status
from adare.exceptions import TestFunctionNotFoundError

log = logging.getLogger(__name__)


class TestQueryMixin:
    """Mixin providing test and testfunction query methods."""

    def get_tests(self, run_ulid: str) -> dict:
        tests_data = {}
        test_events = self._project_api._session.query(Event).filter_by(experiment_run_id=run_ulid).filter(Event.category == 'test').all()
        for event in test_events:
            if event.abstract_test.name not in tests_data:
                tests_data[event.abstract_test.name] = {
                    'name': event.abstract_test.name,
                    'description': event.abstract_test.description,
                    'testfunction_name': event.abstract_test.testfunction.dotnotation,
                    'testfunction_description': event.abstract_test.testfunction.description,
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

    def _enrich_testfunction_data(self, data: pd.DataFrame) -> pd.DataFrame:
        data['object'] = [self._global_api._session.query(TestFunction).filter_by(id=id).one() for id in data['id']]
        data['testfunction_file'] = [self._global_api._session.query(TestFunctionFile).filter_by(id=file_id).one() for file_id in data['file_id']]
        data['dotnotation'] = [obj.dotnotation for obj in data['object']]
        # Add smart display name based on current project context
        data['display_name'] = [self._get_smart_display_name(obj, 'testfunction') for obj in data['object']]
        data['num_parameters'] = [obj.num_parameters for obj in data['object']]
        data['file_path'] = [obj.path for obj in data['testfunction_file']]
        data['file_name'] = [obj.name for obj in data['testfunction_file']]
        data['file_sha256'] = [obj.sha256hash for obj in data['testfunction_file']]
        data['file_description'] = [obj.description for obj in data['testfunction_file']]
        # remove object and testfunction_file columns
        return data.drop(columns=['object', 'testfunction_file'])

    def get_testfunction_list(self) -> pd.DataFrame:
        data = pd.read_sql(self._global_api._session.query(TestFunction).statement, self._global_api._session.bind).map(str)
        return self._enrich_testfunction_data(data)

    def get_testfunction(self, testfunction_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        try:
            testfunction_data = pd.read_sql(self._global_api._session.query(TestFunction).filter_by(id=testfunction_id).statement, self._global_api._session.bind).map(str)
        except sqlalchemy.orm.exc.NoResultFound:
            raise TestFunctionNotFoundError(log, f'Testfunction with id "{testfunction_id}" not found') from None
        testfunction_data = self._enrich_testfunction_data(testfunction_data)
        # get all parameters for the testfunction in a pandas dataframe (test parameters can be in multiple functions)
        testfunction = self._global_api._session.query(TestFunction).filter_by(id=testfunction_id).one()
        parameter_ids = [parameter.id for parameter in testfunction.parameters]
        parameter_data = pd.read_sql(self._global_api._session.query(TestParameter).filter(TestParameter.id.in_(parameter_ids)).statement, self._global_api._session.bind).map(str)
        return testfunction_data, parameter_data

    def testfunction_dotnotation_to_id(self, dotnotation: str) -> int:
        from adare.database.api.dotnotation_parser import DotNotationParser

        parser = DotNotationParser()
        parsed = parser.parse_testfunction_dotnotation(dotnotation)

        file_name = parsed['file_name']
        function_name = parsed['function_name']
        project_name = parsed['project_name']

        file_name_with_extension = file_name + '.py'

        try:
            if project_name:
                # 3-part notation: project.file.function
                # Filter by project to ensure we get the right testfunction
                testfunction_file = self._global_api._session.query(TestFunctionFile).filter(
                    TestFunctionFile.name == file_name_with_extension).filter(
                    TestFunctionFile.projects.any(Project.name == project_name)).one()
            else:
                # 2-part notation: file.function (current project context)
                # Get from current project or first match if no project specified
                testfunction_file = self._global_api._session.query(TestFunctionFile).filter_by(name=file_name_with_extension).one()

            testfunction = self._global_api._session.query(TestFunction).filter_by(file_id=testfunction_file.id, name=function_name).one()
        except sqlalchemy.orm.exc.NoResultFound:
            if project_name:
                raise TestFunctionNotFoundError(log, f'Testfunction with dotnotation "{dotnotation}" not found in project "{project_name}"') from None
            raise TestFunctionNotFoundError(log, f'Testfunction with dotnotation "{dotnotation}" not found') from None
        return testfunction.id

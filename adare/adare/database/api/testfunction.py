# external imports
import sqlalchemy
from pathlib import Path
import ast

# internal imports
import adare.config.database as config_database
from adare.database.models.experiment import TestFunction, TestFunctionFile, TestParameter, \
    Base as ExperimentBase, AbstractTest, TestEvent
from adare.database.api.experiment import ExperimentApi
from adare.database.exceptions import DatabaseTestfunctionCreationError, DatabaseTestfunctionRemovalError, \
    DatabaseTestfunctionUpdateError, DatabaseTestValidationError
from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer
from adare.helperfunctions.hash import hash_file_sha256, hash_string_sha256, combine_hashes
from adare.exceptions import TestfunctionParameterClassMissingError

# configure logging
import logging

log = logging.getLogger(__name__)


class TestfunctionDbApi(ExperimentApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentBase.metadata.create_all(self.engine)

    # def check_test_validity(self, testfunction_file: Path, testfunction: str):
    #     testfunction_obj = self._session.query(TestFunction).filter(
    #         TestFunction.file.path == testfunction_file.as_posix(), TestFunction.name == testfunction).first()
    #     if not testfunction_obj:
    #         raise DatabaseTestValidationError(
    #             log,
    #             message=f'testfunction {testfunction_file.name}.{testfunction} does not exist in database',
    #         )
    #     # get test method from testfunction_file
    #     module_analyzer = PyModuleAnalyzer(testfunction_file)
    #     test_class = module_analyzer.get_class(testfunction)
    #     if not test_class:
    #         raise DatabaseTestValidationError(
    #             log,
    #             message=f'test {testfunction} does not exist in testfunction file {testfunction_file}',
    #         )
    #     # check hash of test method
    #     sha256_test = hash_string_sha256(test_class.get_attribute('test').get_value())
    #     if testfunction_obj.sha256hash != sha256_test and self._session.query(Test).filter(
    #             Test.abstracttest.has(TestFunction.id == testfunction_obj.id)).first():
    #         raise DatabaseTestValidationError(
    #             log,
    #             message=f'test {testfunction} has been changed. It therefore cannot be used in a test because it would result in an inconsistent results',
    #             possible_solutions=[
    #                 'if the test is not used in a test, try to load the testfunction first',
    #                 'otherwise, recover the old testfunction'
    #             ]
    #         )

    def create_testfunction(self, testfunction_file, t_func_class, db_parameter_objects, sha256_testfunction: str):
        test_name = t_func_class.get_attribute('testname').get_value()
        test_description = t_func_class.get_attribute('testdescription').get_value()
        testfunction_obj, created = self.get_or_create(
            TestFunction, defaults={'file': testfunction_file}, name=test_name, sha256hash=sha256_testfunction,
            description=test_description,
        )
        if not created:
            raise DatabaseTestfunctionCreationError(
                log,
                message=f'Testfunction {test_name} already exists in database',
            )

        testfunction_obj.type = t_func_class.name
        testfunction_obj.description = test_description
        testfunction_obj.parameters.extend(db_parameter_objects.values())
        return testfunction_obj

    def remove_testfunction(self, testfunction_file: Path, name: str, safe=False):
        testfunction_file_obj = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.path == testfunction_file.as_posix()).first()
        if not testfunction_file_obj:
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction file {testfunction_file} does not exist in database',
            )
        testfunction_obj = self._session.query(TestFunction).filter(
            TestFunction.file == testfunction_file_obj, TestFunction.name == name).first()
        if not testfunction_obj:
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction {name} does not exist in database',
            )
        if safe:
            # check if testfunction is used in a test
            if self._session.query(sqlalchemy.exists().where(
                    AbstractTest.testfunction_id == testfunction_obj.id,
                    AbstractTest.ulid == TestEvent.abstract_test_id
            )).scalar():
                raise DatabaseTestfunctionRemovalError(
                    log,
                    message=f'Testfunction {name} is used in a test. A removal would result in an inconsistent state',
                    possible_solutions=[
                        'Remove the test that uses the testfunction and then remove the testfunction',
                        'Recover the old testfunction and create a new testfunction'
                    ]
                )

        # delete all related tests as well as abstract tests
        for abstract_test in testfunction_obj.abstracttests:
            for test in abstract_test.tests:
                self._session.delete(test)
                log.info(f'Removed test {test.name} from database')
            self._session.delete(abstract_test)
            log.info(f'Removed abstract test {abstract_test.name} from database')

        self._session.delete(testfunction_obj)
        log.info(f'Removed testfunction {name} from database')
        self._session.commit()


    def remove_testfunction_file_obj(self, path: Path):
        testfunction_file_obj = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.path == path.as_posix()).first()
        if not testfunction_file_obj:
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction file {path} does not exist in database',
            )
        for testfunction_obj in testfunction_file_obj.test_functions:
            # check if testfunction is used in a test
            if self._session.query(sqlalchemy.exists().where(
                    AbstractTest.testfunction_id == testfunction_obj.id,
                    AbstractTest.ulid == TestEvent.abstract_test_id
            )).scalar():
                raise DatabaseTestfunctionRemovalError(
                    log,
                    message=f'Testfunction {testfunction_obj.name} is used in a test. A removal would result in an inconsistent state',
                    possible_solutions=[
                        'Remove the test that uses the testfunction and then remove the testfunction',
                        'Recover the old testfunction and create a new testfunction'
                    ]
                )
            self.remove_testfunction(path, testfunction_obj.name)
        self._session.delete(testfunction_file_obj)
        log.info(f'Removed testfunction file {path} from database')
        self._session.commit()

    def parse_and_create_testfunction(self, testfunction_class, module_analyzer: PyModuleAnalyzer,
                                      testfunction_file: TestFunctionFile):
        parameter_attr_type = testfunction_class.get_attribute('params').get_type()
        if matching_parameter_class := module_analyzer.get_class(parameter_attr_type):
            attribute_dict = matching_parameter_class.get_attributes_as_dict()
            db_parameter_objects = {}
            
            # Create or get parameters sequentially to avoid race conditions
            for attr in attribute_dict.values():
                param_obj, created = self.get_or_create(TestParameter, defaults={'dtype': attr['type']}, name=attr['name'])
                if created:
                    # Flush immediately to make the parameter visible to subsequent get_or_create calls
                    self._session.flush()
                db_parameter_objects[attr['name']] = param_obj
            
            sha256_testfunction = self.__get_testfunction_hash(testfunction_class)
            testfunction_obj = self.create_testfunction(testfunction_file, testfunction_class, db_parameter_objects,
                                                        sha256_testfunction)
            self._session.add(testfunction_obj)
        else:
            raise TestfunctionParameterClassMissingError(
                log,
                message=f'parameter class for testfunction class {testfunction_class.name} is missing',
            )

    def create_testfunction_file_obj(self, project_path: Path, path: Path, requirements: Path):
        if self.testfunction_file_obj_exists(path):
            raise DatabaseTestfunctionCreationError(
                log,
                message=f'Testfunction file {path} already exists in database',
            )
        project = self.get_project(project_path.name)
        if not project:
            raise DatabaseTestfunctionCreationError(
                log,
                message=f'Project {project_path.name} does not exist in database',
            )
        module_analyzer = PyModuleAnalyzer(path)
        sha256hash = combine_hashes([hash_file_sha256(path),hash_file_sha256(requirements)])
        testfunction_file = TestFunctionFile(
            name=path.name,
            path=path.as_posix(),
            requirements_path=requirements.as_posix(),
            sha256hash=sha256hash,
        )
        testfunction_file.projects.append(project)
        self._session.add(testfunction_file)

        for t_func_class in module_analyzer.get_classes(parent='BasicTest'):
            if t_func_class.has_attribute('params'):
                self.parse_and_create_testfunction(t_func_class, module_analyzer, testfunction_file)
            else:
                raise TestfunctionParameterClassMissingError(
                    log,
                    message=f'parameter class for testfunction class {t_func_class.name} is missing',
                )

        self._session.commit()
        return testfunction_file

    def testfunction_file_obj_exists(self, path: Path) -> bool:
        return self._session.query(TestFunctionFile).filter(
            TestFunctionFile.path == path.as_posix()).first() is not None

    def __get_testfunction_hash(self, test_class):
        testfunction_bytes = ast.unparse(test_class.get_method('test'))
        return hash_string_sha256(testfunction_bytes)

    def __update_testfunction(self, testfunction_obj, t_func_class, sha256_testfunction, module_analyzer,
                              testfunction_file):
        if testdescription_attr := t_func_class.get_attribute(
                'testdescription'
        ):
            test_description = testdescription_attr.get_value()
            if testfunction_obj.description != test_description:
                testfunction_obj.description = test_description
                log.info(f'Updated testfunction description for {testfunction_obj.name}')
        if testfunction_obj.sha256hash != sha256_testfunction:
            if (
                    self._session.query(sqlalchemy.exists().where(
                        AbstractTest.testfunction_id == testfunction_obj.id,
                        AbstractTest.ulid == TestEvent.abstract_test_id
                    )).scalar()

            ):
                raise DatabaseTestfunctionUpdateError(
                    log,
                    message=f'Cannot update testfunction {testfunction_obj.name} because it is used in a test. A change would result in an inconsistent state',
                    possible_solutions=[
                        'Remove the test that uses the testfunction and then update the testfunction',
                        'Recover the old testfunction and create a new testfunction'
                    ]
                )
            self.remove_testfunction(Path(testfunction_file.path), testfunction_obj.name)

            self.parse_and_create_testfunction(
                t_func_class, module_analyzer, testfunction_file
            )

            log.info(f'Updated testfunction {testfunction_obj.name}')

    def update_testfunction_file_obj(self, path: Path, requirements_path: Path):
        if not self.testfunction_file_obj_exists(path):
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction file {path} does not exist in database',
            )
        module_analyzer = PyModuleAnalyzer(path)
        testfunction_file = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.path == path.as_posix()).first()

        for t_func_class in module_analyzer.get_classes(parent='BasicTest'):
            sha256_testfunction = self.__get_testfunction_hash(t_func_class)
            if (
                    testfunction_obj := self._session.query(TestFunction).filter(
                        TestFunction.file == testfunction_file,
                        TestFunction.type == t_func_class.name,
                    ).first()
            ):
                self.__update_testfunction(testfunction_obj, t_func_class, sha256_testfunction, module_analyzer,
                                           testfunction_file)
            else:
                self.parse_and_create_testfunction(t_func_class, module_analyzer, testfunction_file)

        class_names = [t_func_class.name for t_func_class in module_analyzer.get_classes(parent='BasicTest')]
        for testfunction_obj in testfunction_file.test_functions:
            if testfunction_obj.type not in class_names:
                self.remove_testfunction(path, testfunction_obj.name, safe=True)
        testfunction_file.sha256hash = combine_hashes([hash_file_sha256(path), hash_file_sha256(requirements_path)])
        self._session.commit()
        return testfunction_file

    def __serialize_testfunction(self, testfunction: TestFunction):
        return {
            'name': testfunction.name,
            'description': testfunction.description,
            'parameters': ",".join([param.name for param in testfunction.parameters])
        }

    def get_testfunctions_by_file(self):
        return {
            testfunction_file.name: [
                self.__serialize_testfunction(testfunction)
                for testfunction in testfunction_file.test_functions
            ]
            for testfunction_file in self._session.query(TestFunctionFile).all()
        }

    def testfunction_exists(self, name: str):
        return self._session.query(sqlalchemy.exists().where(TestFunction.name == name)).scalar()

    def get_testfunction_file(self, testfunction_id: int):
        return self._session.query(TestFunctionFile).filter(TestFunctionFile.id == testfunction_id).first()

    def get_testfunction_file_hash(self, testfunction_id: int):
        testfunction_file = self.get_testfunction_file(testfunction_id)
        sha256 = testfunction_file.sha256hash
        return sha256

    def sync_testfunction_file(self, testfunction_id: int, remote_id: int, remote_url: str, is_published: bool):
        testfunction_obj = self.get_testfunction_file(testfunction_id)
        testfunction_obj.remote_id = remote_id
        testfunction_obj.remote_url = remote_url
        testfunction_obj.published = is_published
        self._session.commit()
        return testfunction_obj

    def get_testfunction_files(self, project_path: Path = None):
        if project_path:
            project = self.get_project(project_path.name)
            return self._session.query(TestFunctionFile).filter(TestFunctionFile.projects.contains(project)).all()
        return self._session.query(TestFunctionFile).all()

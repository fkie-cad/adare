# external imports
import ast

# configure logging
import logging
from pathlib import Path

import sqlalchemy

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.exceptions import (
    DatabaseTestfunctionCreationError,
    DatabaseTestfunctionRemovalError,
)
from adare.database.models.global_models import Project, TestFunction, TestFunctionFile, TestParameter
from adare.exceptions import TestfunctionParameterClassMissingError
from adare.helperfunctions.hash import combine_hashes, hash_file_sha256, hash_string_sha256
from adare.helperfunctions.pyfileanalyze import PyModuleAnalyzer

log = logging.getLogger(__name__)


class TestfunctionDbApi(GlobalDatabaseApi):

    def __init__(self):
        super().__init__()
        self._start_session()

    def get_project(self, name: str) -> Project | None:
        """Get project by name from global database."""
        project = self._session.query(Project).filter(Project.name == name).first()
        if not project:
            log.error(f"Project '{name}' not found in database")
            return None
        return project

    def create_testfunction(self, testfunction_file, t_func_class, db_parameter_objects, sha256_testfunction: str):
        test_name = t_func_class.get_attribute('testname').get_value()
        test_description = t_func_class.get_attribute('testdescription').get_value()

        testfunction_obj, created = self.get_or_create(
            TestFunction,
            defaults={
                'description': test_description,
                'type': t_func_class.name,
                'sha256hash': sha256_testfunction
            },
            name=test_name,
            file_id=testfunction_file.id
        )
        if not created:
            raise DatabaseTestfunctionCreationError(
                log,
                message=f'Testfunction {test_name} already exists in database',
            )

        testfunction_obj.parameters.extend(db_parameter_objects.values())
        return testfunction_obj

    def remove_testfunction(self, testfunction_file: Path, name: str):
        """Remove a single testfunction. Does NOT commit - caller must commit."""
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
        # Note: Usage checks should be done at command level using get_testfunction_usage()
        # because abstract_tests and test_events are in project databases, not global database

        self._session.delete(testfunction_obj)
        log.info(f'Marked testfunction {name} for removal from database')


    def remove_testfunction_file_obj(self, path: Path):
        """Remove a testfunction file and all its testfunctions (cascade delete)."""
        testfunction_file_obj = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.path == path.as_posix()).first()
        if not testfunction_file_obj:
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction file {path} does not exist in database',
            )
        # Note: Usage checks should be done at command level using get_testfunction_usage()

        # Count testfunctions for logging
        testfunction_count = len(testfunction_file_obj.test_functions)

        # Delete the file object - cascade will automatically delete all testfunctions
        self._session.delete(testfunction_file_obj)

        # Single commit at the end
        self._session.commit()
        log.info(f'Successfully removed testfunction file {path} and {testfunction_count} testfunction(s)')

    def remove_testfunction_file_obj_by_name(self, name: str):
        """Remove a testfunction file by name (e.g., 'xml', 'json', 'csv')."""
        testfunction_file_obj = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == name).first()
        if not testfunction_file_obj:
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction file "{name}" does not exist in database',
            )
        # Note: Usage checks should be done at command level using get_testfunction_usage()

        # Count testfunctions for logging
        testfunction_count = len(testfunction_file_obj.test_functions)

        # Delete the file object - cascade will automatically delete all testfunctions
        self._session.delete(testfunction_file_obj)

        # Single commit at the end
        self._session.commit()
        log.info(f'Successfully removed testfunction file "{name}" and {testfunction_count} testfunction(s)')

    def parse_and_create_testfunction(self, testfunction_class, module_analyzer: PyModuleAnalyzer,
                                      testfunction_file: TestFunctionFile):
        parameter_attr_type = testfunction_class.get_attribute('parameter').get_type()
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
        # Check if testfunction file already exists by name (testfunctions are global)
        existing_file = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == path.stem).first()
        if existing_file:
            log.debug(f'Testfunction file {path.name} already exists in global database - using existing')
            return existing_file
        # Testfunctions are now global resources - no project relationship needed
        module_analyzer = PyModuleAnalyzer(path)
        sha256hash = combine_hashes([hash_file_sha256(path),hash_file_sha256(requirements)])

        # Use the actual paths provided (which should be the global paths from TestfunctionManager)
        testfunction_file = TestFunctionFile(
            name=path.stem,
            path=path.as_posix(),
            requirements_path=requirements.as_posix(),
            sha256hash=sha256hash,
        )
        self._session.add(testfunction_file)
        self._session.flush()  # Flush to get ID for the testfunction_file

        for t_func_class in module_analyzer.get_classes(parent='BasicTest'):
            if t_func_class.has_attribute('parameter'):
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
            TestFunctionFile.name == path.stem).first() is not None

    def testfunction_file_obj_exists_by_name(self, name: str) -> bool:
        """Check if a testfunction file exists by name."""
        return self._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == name).first() is not None

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
            # Note: Usage checks should be done at command level using can_safely_update_testfunction()
            # because abstract_tests and test_events are in project databases, not global database
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
                self.remove_testfunction(path, testfunction_obj.name)
        testfunction_file.sha256hash = combine_hashes([hash_file_sha256(path), hash_file_sha256(requirements_path)])
        self._session.commit()
        return testfunction_file

    def __serialize_testfunction(self, testfunction: TestFunction):
        return {
            'name': testfunction.dotnotation,
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
        return testfunction_file.sha256hash

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

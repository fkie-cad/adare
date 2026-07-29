# external imports
import ast

# configure logging
import logging
import shutil
from pathlib import Path

import sqlalchemy

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.exceptions import (
    DatabaseTestfunctionCreationError,
    DatabaseTestfunctionRemovalError,
)
from adare.database.models.global_models import (
    Project,
    SyncMetadata,
    TestFunction,
    TestFunctionFile,
    TestFunctionFileVersion,
    TestFunctionVersion,
    TestParameter,
)
from adare.database.models.sync_identity import apply_remote_identity
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
                'sha256hash': sha256_testfunction,
                # Set explicitly (not only via column default) so the values are
                # readable before flush — _append_testfunction_version reads them.
                'version': 1,
                'is_current': True,
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
        # Record the initial per-method version (v1) introduced by the file's
        # current version. Uses the relationship so the FK resolves at flush even
        # before the ULID default is materialised.
        self._append_testfunction_version(testfunction_obj, testfunction_file.version)
        return testfunction_obj

    def _append_testfunction_version(self, testfunction_obj: TestFunction, file_version: int | None):
        """Append a per-method version history row mirroring the method's current state."""
        self._session.add(TestFunctionVersion(
            test_function=testfunction_obj,
            version=testfunction_obj.version,
            sha256hash=testfunction_obj.sha256hash,
            file_version=file_version,
        ))

    def _write_file_snapshot(self, testfunction_file: TestFunctionFile, version: int) -> Path:
        """Retain the on-disk copy of a file version under versions/v<N>/ (best effort)."""
        py_path = Path(testfunction_file.path)
        snapshot_dir = py_path.parent / 'versions' / f'v{version}'
        try:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            if py_path.exists():
                shutil.copy2(py_path, snapshot_dir / py_path.name)
            if testfunction_file.requirements_path:
                req_path = Path(testfunction_file.requirements_path)
                if req_path.exists():
                    shutil.copy2(req_path, snapshot_dir / 'requirements.txt')
        except OSError as e:
            log.warning(f'Could not write snapshot for {testfunction_file.name} v{version}: {e}')
        return snapshot_dir

    def _append_file_version(self, testfunction_file: TestFunctionFile, version: int, sha256hash: str):
        """Retain a snapshot and append a file version history row."""
        snapshot_dir = self._write_file_snapshot(testfunction_file, version)
        self._session.add(TestFunctionFileVersion(
            file=testfunction_file,
            version=version,
            sha256hash=sha256hash,
            snapshot_dir=snapshot_dir.as_posix(),
        ))

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

    def _resolve_parameters(self, testfunction_class, module_analyzer: PyModuleAnalyzer) -> dict:
        """Resolve (creating as needed) the TestParameter rows for a testfunction class."""
        parameter_attr_type = testfunction_class.get_attribute('parameter').get_type()
        matching_parameter_class = module_analyzer.get_class(parameter_attr_type)
        if not matching_parameter_class:
            raise TestfunctionParameterClassMissingError(
                log,
                message=f'parameter class for testfunction class {testfunction_class.name} is missing',
            )
        attribute_dict = matching_parameter_class.get_attributes_as_dict()
        db_parameter_objects = {}
        # Create or get parameters sequentially to avoid race conditions
        for attr in attribute_dict.values():
            param_obj, created = self.get_or_create(TestParameter, defaults={'dtype': attr['type']}, name=attr['name'])
            if created:
                # Flush immediately to make the parameter visible to subsequent get_or_create calls
                self._session.flush()
            db_parameter_objects[attr['name']] = param_obj
        return db_parameter_objects

    def parse_and_create_testfunction(self, testfunction_class, module_analyzer: PyModuleAnalyzer,
                                      testfunction_file: TestFunctionFile):
        db_parameter_objects = self._resolve_parameters(testfunction_class, module_analyzer)
        sha256_testfunction = self.__get_testfunction_hash(testfunction_class)
        testfunction_obj = self.create_testfunction(testfunction_file, testfunction_class, db_parameter_objects,
                                                    sha256_testfunction)
        self._session.add(testfunction_obj)

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

        # Record the initial file version (v1) and retain its snapshot.
        self._append_file_version(testfunction_file, testfunction_file.version, sha256hash)
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
                              testfunction_file, file_version: int):
        """Non-destructive per-method update.

        Keeps the same TestFunction row (stable ULID referenced by experiments).
        On a method content change (or reactivation of a previously-removed
        method) the version is bumped in place and a TestFunctionVersion row is
        appended — the row is never deleted and recreated.
        """
        if testdescription_attr := t_func_class.get_attribute('testdescription'):
            test_description = testdescription_attr.get_value()
            if testfunction_obj.description != test_description:
                testfunction_obj.description = test_description
                log.info(f'Updated testfunction description for {testfunction_obj.name}')

        # Keep the class type accurate (a class may be renamed while its testname stays).
        if testfunction_obj.type != t_func_class.name:
            testfunction_obj.type = t_func_class.name

        # A method that had vanished (is_current=False) reappeared under the same
        # name: reactivate the existing identity instead of creating a duplicate.
        reactivated = False
        if not testfunction_obj.is_current:
            testfunction_obj.is_current = True
            reactivated = True
            log.info(f'Reactivated testfunction {testfunction_obj.name} (reappeared in source)')

        if testfunction_obj.sha256hash != sha256_testfunction or reactivated:
            # Note: Usage checks should be done at command level using can_safely_update_testfunction()
            # because abstract_tests and test_events are in project databases, not global database
            testfunction_obj.sha256hash = sha256_testfunction
            # Refresh parameters in place (the signature may have changed).
            db_parameter_objects = self._resolve_parameters(t_func_class, module_analyzer)
            testfunction_obj.parameters = list(db_parameter_objects.values())
            testfunction_obj.version += 1
            self._append_testfunction_version(testfunction_obj, file_version)
            log.info(f'Updated testfunction {testfunction_obj.name} to version {testfunction_obj.version}')

    def upsert_testfunction_file_obj(self, path: Path, requirements: Path) -> tuple[str, TestFunctionFile]:
        """Upsert by hash. Returns ('created' | 'updated' | 'unchanged', file_obj)."""
        existing = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == path.stem).first()
        if not existing:
            return 'created', self.create_testfunction_file_obj(path.parent, path, requirements)

        current_hash = combine_hashes([hash_file_sha256(path), hash_file_sha256(requirements)])
        if existing.sha256hash == current_hash:
            return 'unchanged', existing

        return 'updated', self.update_testfunction_file_obj(path, requirements)

    def __get_testname(self, t_func_class) -> str:
        return t_func_class.get_attribute('testname').get_value()

    def update_testfunction_file_obj(self, path: Path, requirements_path: Path):
        if not self.testfunction_file_obj_exists(path):
            raise DatabaseTestfunctionRemovalError(
                log,
                message=f'Testfunction file {path} does not exist in database',
            )
        module_analyzer = PyModuleAnalyzer(path)
        testfunction_file = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.path == path.as_posix()).first()

        # Bump the file version first so brand-new / updated methods record the
        # file version that introduced them.
        new_file_version = testfunction_file.version + 1
        testfunction_file.version = new_file_version

        # Identity is the dotnotation (collection.testname); match existing rows by
        # `name`, not class type, so a class rename with an unchanged testname
        # updates the same identity instead of colliding on a create.
        source_test_names: set[str] = set()
        for t_func_class in module_analyzer.get_classes(parent='BasicTest'):
            test_name = self.__get_testname(t_func_class)
            source_test_names.add(test_name)
            sha256_testfunction = self.__get_testfunction_hash(t_func_class)
            if (
                    testfunction_obj := self._session.query(TestFunction).filter(
                        TestFunction.file == testfunction_file,
                        TestFunction.name == test_name,
                    ).first()
            ):
                self.__update_testfunction(testfunction_obj, t_func_class, sha256_testfunction, module_analyzer,
                                           testfunction_file, new_file_version)
            else:
                self.parse_and_create_testfunction(t_func_class, module_analyzer, testfunction_file)

        # Vanished methods: never delete (would dangle experiment references) —
        # mark not current and keep the row + its version history.
        for testfunction_obj in list(testfunction_file.test_functions):
            if testfunction_obj.name not in source_test_names and testfunction_obj.is_current:
                testfunction_obj.is_current = False
                log.info(f'Marked testfunction {testfunction_obj.name} as not current (removed from source)')

        new_hash = combine_hashes([hash_file_sha256(path), hash_file_sha256(requirements_path)])
        testfunction_file.sha256hash = new_hash
        self._append_file_version(testfunction_file, new_file_version, new_hash)
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
        """Record where this testfunction file lives on the server.

        Same fix as sync_experiment / sync_environment: ``remote_id``,
        ``remote_url`` and ``published`` are not mapped columns on
        TestFunctionFile, so assigning them wrote nothing. The file already has a
        ``sync_metadata`` relationship — that is the row that persists.
        """
        testfunction_obj = self.get_testfunction_file(testfunction_id)
        apply_remote_identity(
            self._session, testfunction_obj, SyncMetadata,
            remote_ulid=str(remote_id) if remote_id is not None else None,
            remote_url=remote_url, is_published=is_published,
        )
        self._session.commit()
        return testfunction_obj

    def get_version_history(self, file_name: str, func_name: str | None = None) -> dict | None:
        """Return the version history for a testfunction file (and optionally a
        single method), as plain detached data. Returns None if the file is unknown.
        """
        testfunction_file = self._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == file_name).first()
        if not testfunction_file:
            return None

        file_versions = sorted(testfunction_file.versions, key=lambda v: v.version)
        result = {
            'file_name': testfunction_file.name,
            'current_version': testfunction_file.version,
            'versions': [
                {
                    'version': v.version,
                    'sha256': v.sha256hash,
                    'created_at': v.created_at.isoformat() if v.created_at else None,
                    'is_current': v.version == testfunction_file.version,
                    'snapshot_dir': v.snapshot_dir,
                }
                for v in file_versions
            ],
            'method': None,
        }

        if func_name:
            testfunction = self._session.query(TestFunction).filter(
                TestFunction.file_id == testfunction_file.id,
                TestFunction.name == func_name,
            ).first()
            if testfunction:
                method_versions = sorted(testfunction.versions, key=lambda v: v.version)
                result['method'] = {
                    'name': testfunction.name,
                    'current_version': testfunction.version,
                    'is_current': testfunction.is_current,
                    'versions': [
                        {
                            'version': v.version,
                            'sha256': v.sha256hash,
                            'file_version': v.file_version,
                            'created_at': v.created_at.isoformat() if v.created_at else None,
                            'is_current': v.version == testfunction.version,
                        }
                        for v in method_versions
                    ],
                }
        return result

    def get_testfunction_files(self, project_path: Path = None):
        if project_path:
            project = self.get_project(project_path.name)
            return self._session.query(TestFunctionFile).filter(TestFunctionFile.projects.contains(project)).all()
        return self._session.query(TestFunctionFile).all()

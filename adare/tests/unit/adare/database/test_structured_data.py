"""Tests for StructuredDataApi — the structured data retrieval layer."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, PropertyMock

import ulid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adare.database.models.global_models import (
    GlobalBase, Project, Environment, Vm, OsInfo, SyncMetadata,
    TestFunction, TestFunctionFile, TestParameter,
    mapping_testfunction_testparameter,
)
from adare.database.models.project_models import (
    ProjectBase, Experiment, ExperimentRun, Tag,
    mapping_experiment_tag,
)
from adare.database.api.structured_data import StructuredDataApi
from adare.database.utils.error_handling import DataRetrievalError
from adare.types.output_models import (
    ProjectInfo, EnvironmentInfo, ExperimentInfo, TestFunctionInfo, RunInfo,
)


# ---------------------------------------------------------------------------
# Helpers — generate model instances with sensible defaults
# ---------------------------------------------------------------------------

def _ulid() -> str:
    return str(ulid.ULID())


def make_project(name="proj1", description="A project", path="/tmp/proj1"):
    return Project(id=_ulid(), name=name, description=description, path=path)


def make_osinfo(
    platform="Windows", os="Windows", distribution="10",
    version="21H2", language="en-US",
):
    return OsInfo(
        id=_ulid(), platform=platform, os=os,
        distribution=distribution, version=version, language=language,
    )


def make_vm(name="win10-vm", file="win10.box", hash_val="abc123", osinfo=None):
    return Vm(
        id=_ulid(), name=name, file=file, hash=hash_val,
        osinfo_id=osinfo.id if osinfo else None,
    )


def make_sync_metadata(sync_status="synced"):
    return SyncMetadata(id=_ulid(), sync_status=sync_status)


def make_environment(
    name="env1", description="An env", vm=None,
    file="env.yaml", sync_metadata=None,
):
    return Environment(
        id=_ulid(), name=name, description=description,
        vm_id=vm.id if vm else None,
        file=file,
        sync_metadata_id=sync_metadata.id if sync_metadata else None,
    )


def make_experiment(name="exp1", description="An experiment", environment_ids=None, tags=None):
    exp = Experiment(
        id=_ulid(), name=name, description=description,
        sha256="deadbeef", environment_ids=environment_ids,
    )
    if tags:
        exp.tags = tags
    return exp


def make_tag(name="tag1"):
    return Tag(id=_ulid(), name=name)


def make_testfunction_file(
    name="standard.py", path="/funcs/standard.py",
    sha256hash="ffff", description="Standard tests",
):
    return TestFunctionFile(
        id=_ulid(), name=name, path=path,
        sha256hash=sha256hash, description=description,
    )


def make_testfunction(name="file_exists", tf_file=None, description="Check file"):
    return TestFunction(
        id=_ulid(), type="standard", name=name,
        description=description, sha256hash="aaaa",
        file_id=tf_file.id if tf_file else _ulid(),
    )


def make_testparameter(name="dst", dtype="str", description="Destination path", optional=False):
    return TestParameter(
        id=_ulid(), name=name, dtype=dtype,
        description=description, optional=optional,
    )


def make_run(experiment=None, start_time=None, end_time=None, status="PENDING", fake=False, published=False):
    return ExperimentRun(
        id=_ulid(),
        experiment_id=experiment.id if experiment else None,
        start_time=start_time, end_time=end_time,
        status=status, fake=fake, published=published,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    """Return a temporary SQLite database path."""
    return tmp_path / "test.db"


@pytest.fixture()
def structured_api(db_path):
    """Create tables for both GlobalBase and ProjectBase, return API as context manager."""
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    GlobalBase.metadata.create_all(engine)
    ProjectBase.metadata.create_all(engine)

    api = StructuredDataApi.__new__(StructuredDataApi)
    api.engine = engine
    api.conn = engine.connect()
    api.metadata = GlobalBase.metadata
    api.session_starter = sessionmaker(autoflush=False, expire_on_commit=False)
    api.session_starter.configure(bind=engine)

    api._session = api.session_starter()
    api._session.begin()
    yield api
    api._session.rollback()
    api._session.close()


def _add_all(session, *objs):
    """Flush a batch of ORM objects into the session."""
    for obj in objs:
        session.add(obj)
    session.flush()


# ---------------------------------------------------------------------------
# TestGetProjectsStructured
# ---------------------------------------------------------------------------

class TestGetProjectsStructured:

    def test_empty_db(self, structured_api):
        assert structured_api.get_projects_structured() == []

    def test_single_project(self, structured_api):
        p = make_project(name="alpha", description="Alpha project", path="/alpha")
        _add_all(structured_api._session, p)

        result = structured_api.get_projects_structured()
        assert len(result) == 1
        assert isinstance(result[0], ProjectInfo)
        assert result[0].name == "alpha"
        assert result[0].description == "Alpha project"
        assert result[0].path == "/alpha"

    def test_multiple_projects(self, structured_api):
        _add_all(
            structured_api._session,
            make_project(name="a", path="/a"),
            make_project(name="b", path="/b"),
            make_project(name="c", path="/c"),
        )

        result = structured_api.get_projects_structured()
        assert len(result) == 3
        names = {r.name for r in result}
        assert names == {"a", "b", "c"}

    def test_null_description_and_path(self, structured_api):
        p = Project(id=_ulid(), name="bare", description=None, path=None)
        _add_all(structured_api._session, p)

        result = structured_api.get_projects_structured()
        assert result[0].description == ""
        assert result[0].path == ""


# ---------------------------------------------------------------------------
# TestGetEnvironmentsStructured
# ---------------------------------------------------------------------------

class TestGetEnvironmentsStructured:

    def test_empty_db(self, structured_api):
        assert structured_api.get_environments_structured() == []

    def test_environment_with_vm_and_osinfo(self, structured_api):
        osinfo = make_osinfo(
            platform="Windows", os="Windows",
            distribution="10", version="21H2", language="en-US",
        )
        vm = make_vm(name="win10-box", file="win10.box", osinfo=osinfo)
        env = make_environment(name="win10-env", description="Win10 test env", vm=vm, file="win10.yaml")
        _add_all(structured_api._session, osinfo, vm, env)

        result = structured_api.get_environments_structured()
        assert len(result) == 1
        info = result[0]
        assert isinstance(info, EnvironmentInfo)
        assert info.name == "win10-env"
        assert info.description == "Win10 test env"
        assert info.vm_box == "win10-box"
        assert info.vm_id == vm.id
        assert info.osinfo_os == "Windows"
        assert info.osinfo_distribution == "10"
        assert info.osinfo_version == "21H2"
        assert info.osinfo_language == "en-US"
        assert info.file == "win10.yaml"
        assert info.project == "Global"

    def test_environment_without_vm(self, structured_api):
        env = make_environment(name="no-vm-env", vm=None, file="")
        _add_all(structured_api._session, env)

        result = structured_api.get_environments_structured()
        assert len(result) == 1
        info = result[0]
        assert info.vm_box == "No VM"
        assert info.vm_id == ""
        assert info.osinfo_os == ""

    def test_environment_with_sync_metadata(self, structured_api):
        sync = make_sync_metadata(sync_status="synced")
        env = make_environment(name="synced-env", sync_metadata=sync)
        _add_all(structured_api._session, sync, env)

        result = structured_api.get_environments_structured()
        info = result[0]
        assert info.published is True
        assert info.in_request is False


# ---------------------------------------------------------------------------
# TestGetExperimentsStructured
# ---------------------------------------------------------------------------

class TestGetExperimentsStructured:

    def test_empty_db(self, structured_api):
        assert structured_api.get_experiments_structured() == []

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="testproj")
    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="exp1")
    def test_single_experiment(self, mock_display, mock_proj, structured_api):
        exp = make_experiment(name="exp1", description="First experiment", environment_ids=None)
        _add_all(structured_api._session, exp)

        result = structured_api.get_experiments_structured()
        assert len(result) == 1
        info = result[0]
        assert isinstance(info, ExperimentInfo)
        assert info.name == "exp1"
        assert info.description == "First experiment"
        assert info.dotnotation == "testproj.exp1"
        assert info.project == "testproj"
        assert info.created_at is not None

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="proj")
    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="exp1")
    def test_experiment_with_tags(self, mock_display, mock_proj, structured_api):
        t1 = make_tag(name="forensics")
        t2 = make_tag(name="windows")
        exp = make_experiment(name="exp1", tags=[t1, t2])
        _add_all(structured_api._session, t1, t2, exp)

        result = structured_api.get_experiments_structured()
        assert set(result[0].tags) == {"forensics", "windows"}

    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="exp1")
    def test_experiment_project_name_from_arg(self, mock_display, structured_api):
        """Passing project_name= explicitly should override CWD detection."""
        exp = make_experiment(name="exp1", environment_ids=None)
        _add_all(structured_api._session, exp)

        result = structured_api.get_experiments_structured(project_name="myproj")
        assert result[0].dotnotation == "myproj.exp1"
        assert result[0].project == "myproj"

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="proj")
    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="exp1")
    def test_experiment_no_environments(self, mock_display, mock_proj, structured_api):
        """environment_ids=None -> environments property returns [], primary env is ''."""
        exp = make_experiment(name="exp1", environment_ids=None)
        _add_all(structured_api._session, exp)

        result = structured_api.get_experiments_structured()
        assert result[0].environment == ""
        assert result[0].environments == []


# ---------------------------------------------------------------------------
# TestGetTestfunctionsStructured
# ---------------------------------------------------------------------------

class TestGetTestfunctionsStructured:

    def test_empty_db(self, structured_api):
        assert structured_api.get_testfunctions_structured() == []

    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="standard.file_exists")
    def test_testfunction_with_file_and_params(self, mock_display, structured_api):
        tf_file = make_testfunction_file(
            name="standard.py", path="/funcs/standard.py",
            sha256hash="abcd1234", description="Standard test functions",
        )
        tf = make_testfunction(name="file_exists", tf_file=tf_file, description="Check if file exists")
        param = make_testparameter(name="dst", dtype="str", description="Destination", optional=False)
        _add_all(structured_api._session, tf_file, tf, param)

        # Link parameter to testfunction via mapping table
        structured_api._session.execute(
            mapping_testfunction_testparameter.insert().values(
                test_function_id=tf.id, test_parameter_id=param.id,
            )
        )
        structured_api._session.flush()

        result = structured_api.get_testfunctions_structured(include_parameters=True)
        assert len(result) == 1
        info = result[0]
        assert isinstance(info, TestFunctionInfo)
        assert info.name == "file_exists"
        assert info.description == "Check if file exists"
        assert info.file_name == "standard.py"
        assert info.file_path == "standard"
        assert info.full_file_path == "/funcs/standard.py"
        assert info.file_sha256 == "abcd1234"
        assert info.file_description == "Standard test functions"
        assert info.parameter_count == 1
        assert len(info.parameters) == 1
        assert info.parameters[0]["name"] == "dst"
        assert info.parameters[0]["data_type"] == "str"
        assert info.parameters[0]["required"] is True

    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="standard.file_exists")
    def test_testfunction_without_parameters(self, mock_display, structured_api):
        tf_file = make_testfunction_file(name="check.py", path="/funcs/check.py")
        tf = make_testfunction(name="file_exists", tf_file=tf_file)
        _add_all(structured_api._session, tf_file, tf)

        result = structured_api.get_testfunctions_structured(include_parameters=False)
        assert len(result) == 1
        assert result[0].parameters == []

    @patch("adare.database.api.structured_data.get_smart_display_name", return_value="standard.file_exists")
    def test_testfunction_filter_by_file(self, mock_display, structured_api):
        f1 = make_testfunction_file(name="standard.py", path="/funcs/standard.py")
        f2 = make_testfunction_file(name="excel.py", path="/funcs/excel.py")
        tf1 = make_testfunction(name="file_exists", tf_file=f1)
        tf2 = make_testfunction(name="validate_columns", tf_file=f2)
        _add_all(structured_api._session, f1, f2, tf1, tf2)

        result = structured_api.get_testfunctions_structured(testfunction_file="standard.py")
        assert len(result) == 1
        assert result[0].name == "file_exists"

    def test_testfunction_filter_nonexistent_file(self, structured_api):
        f1 = make_testfunction_file(name="standard.py", path="/funcs/standard.py")
        tf1 = make_testfunction(name="file_exists", tf_file=f1)
        _add_all(structured_api._session, f1, tf1)

        result = structured_api.get_testfunctions_structured(testfunction_file="nonexistent.py")
        assert result == []

    def test_testfunction_invalid_file_param(self, structured_api):
        with pytest.raises(DataRetrievalError, match="testfunction_file must be a string"):
            structured_api.get_testfunctions_structured(testfunction_file=123)


# ---------------------------------------------------------------------------
# TestGetRunsStructured
# ---------------------------------------------------------------------------

class TestGetRunsStructured:

    def test_empty_db(self, structured_api):
        assert structured_api.get_runs_structured() == []

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="myproj")
    def test_run_with_experiment(self, mock_proj, structured_api):
        exp = make_experiment(name="exp1", environment_ids=None)
        now = datetime(2026, 1, 15, 10, 0, 0)
        run = make_run(experiment=exp, start_time=now, end_time=now + timedelta(seconds=120))
        _add_all(structured_api._session, exp, run)

        result = structured_api.get_runs_structured()
        assert len(result) == 1
        info = result[0]
        assert isinstance(info, RunInfo)
        assert info.experiment_name == "myproj.exp1"
        assert info.experiment_ulid == exp.id
        assert info.ulid == run.id
        assert info.project_name == "myproj"

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="proj")
    def test_run_duration_calculation(self, mock_proj, structured_api):
        exp = make_experiment(name="exp1", environment_ids=None)
        start = datetime(2026, 3, 1, 12, 0, 0)
        end = datetime(2026, 3, 1, 12, 5, 30)
        run = make_run(experiment=exp, start_time=start, end_time=end)
        _add_all(structured_api._session, exp, run)

        result = structured_api.get_runs_structured()
        assert result[0].duration_seconds == 330.0

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="proj")
    def test_run_no_times(self, mock_proj, structured_api):
        exp = make_experiment(name="exp1", environment_ids=None)
        run = make_run(experiment=exp, start_time=None, end_time=None)
        _add_all(structured_api._session, exp, run)

        result = structured_api.get_runs_structured()
        assert result[0].duration_seconds == 0.0

    @patch("adare.database.api.structured_data.get_current_project_name", return_value="proj")
    def test_run_filter_by_experiment_name(self, mock_proj, structured_api):
        exp1 = make_experiment(name="target", environment_ids=None)
        exp2 = make_experiment(name="other", environment_ids=None)
        run1 = make_run(experiment=exp1)
        run2 = make_run(experiment=exp2)
        _add_all(structured_api._session, exp1, exp2, run1, run2)

        result = structured_api.get_runs_structured(experiment_name="target")
        assert len(result) == 1
        assert result[0].experiment_name == "proj.target"

    def test_run_invalid_param_type(self, structured_api):
        with pytest.raises(DataRetrievalError, match="experiment_name must be a string"):
            structured_api.get_runs_structured(experiment_name=42)

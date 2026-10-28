"""The current project is named by its registration, not by its directory.

A project can be registered under a name other than its directory's (``T2F`` at
``.../adare``). Runs, experiments and dotnotations are keyed by the registered name, so
resolving the current project by directory name found nothing for such projects.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from adare.backend.basics import registered_project_name
from adare.database.api.dotnotation_parser import DotNotationParser
from adare.database.utils import display_helpers

pytestmark = pytest.mark.unit

REGISTERED_NAME = 'T2F'


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """A project directory named ``adare``, registered as ``T2F``; the cwd is inside it."""
    directory = tmp_path / 'adare'
    directory.mkdir()
    record = SimpleNamespace(name=REGISTERED_NAME, path=directory.as_posix())

    class _Db:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_project(self, name, silent=False):
            return record if name == REGISTERED_NAME else None

        def get_project_by_path(self, path, silent=False):
            return record if path.as_posix() == record.path else None

    import adare.database.api.project as project_module

    monkeypatch.setattr(project_module, 'ProjectDbApi', _Db)
    monkeypatch.chdir(directory)
    display_helpers.get_current_project_name.cache_clear()
    yield directory
    display_helpers.get_current_project_name.cache_clear()


class TestRegisteredProjectName:
    def test_returns_the_registered_name(self, project_dir):
        assert project_dir.name != REGISTERED_NAME
        assert registered_project_name(project_dir) == REGISTERED_NAME

    def test_falls_back_to_the_directory_name(self, project_dir, tmp_path):
        assert registered_project_name(tmp_path / 'elsewhere') == 'elsewhere'

    def test_with_a_real_registry(self, tmp_path):
        """Against the actual global database (in the test ADARE_HOME), not a stub."""
        from adare.database.api.project import ProjectDbApi
        from adare.database.models.global_models import Project

        directory = tmp_path / 'checkout'
        directory.mkdir()
        with ProjectDbApi() as api:
            api._session.add(Project(name='RegisteredElsewhere', path=directory.as_posix()))
        try:
            assert registered_project_name(directory) == 'RegisteredElsewhere'
            assert registered_project_name(tmp_path / 'unknown') == 'unknown'
        finally:
            with ProjectDbApi() as api:
                api._session.query(Project).filter(Project.path == directory.as_posix()).delete()


class TestCurrentProjectName:
    def test_get_current_project_name_uses_the_registered_name(self, project_dir):
        assert display_helpers.get_current_project_name() == REGISTERED_NAME

    def test_get_current_project_name_outside_a_project(self, project_dir, tmp_path, monkeypatch):
        outside = tmp_path / 'outside'
        outside.mkdir()
        monkeypatch.chdir(outside)
        assert display_helpers.get_current_project_name() is None

    def test_get_current_project_name_survives_a_database_error(self, project_dir, monkeypatch):
        import sqlite3

        from adare.backend import basics

        def broken(_path):
            raise sqlite3.DatabaseError('file is not a database')

        monkeypatch.setattr(basics, 'registered_project_name', broken)
        assert display_helpers.get_current_project_name() is None

    def test_dotnotation_parser_uses_the_registered_name(self, project_dir):
        assert DotNotationParser()._get_current_project_name() == REGISTERED_NAME

    def test_show_filter_uses_the_registered_name(self, project_dir):
        from adare.cli.show import _parse_filter

        assert _parse_filter(SimpleNamespace(filter='env1.exp1', project=None)) == (REGISTERED_NAME, 'env1', 'exp1')
        assert _parse_filter(SimpleNamespace(filter=None, project=None))[0] == REGISTERED_NAME
        assert Path.cwd() == project_dir

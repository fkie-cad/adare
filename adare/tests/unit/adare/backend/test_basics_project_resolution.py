"""``-p/--project`` must accept a project name **or** a path.

Its help text says "Project name/path", and the not-found error's own suggestion is
*"Use full path: 'adare -p /path/to/project <command>'"* — but only the name lookup
was implemented, so passing a path (even the exact one ``adare project list``
prints) failed with "does not exist in database". `get_project_by_path` existed two
functions away and was never consulted.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from adare.backend import basics
from adare.backend.basics import _looks_like_path, determine_projectdirectory

PROJECT_NAME = 'Tproj1'


@pytest.fixture
def registered(tmp_path, monkeypatch):
    """Stub ProjectDbApi with one registered project at *tmp_path*."""
    project_dir = tmp_path / PROJECT_NAME
    project_dir.mkdir()
    record = SimpleNamespace(name=PROJECT_NAME, path=project_dir.as_posix())
    calls: list[tuple[str, str]] = []

    class _Db:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_project(self, name, silent=False):
            calls.append(('name', name))
            return record if name == PROJECT_NAME else None

        def get_project_by_path(self, path, silent=False):
            calls.append(('path', path.as_posix()))
            return record if path.as_posix() == record.path else None

    import adare.database.api.project as project_module
    monkeypatch.setattr(project_module, 'ProjectDbApi', _Db)
    return SimpleNamespace(dir=project_dir, record=record, calls=calls)


class TestLooksLikePath:

    @pytest.mark.parametrize('value', ['/abs/path', 'rel/path', '~/under-home', '~'])
    def test_path_shaped_values(self, value):
        assert _looks_like_path(value) is True

    @pytest.mark.parametrize('value', ['Tproj1', 'my-project', 'proj_2', ''])
    def test_bare_names_are_not_paths(self, value):
        assert _looks_like_path(value) is False


class TestDetermineProjectDirectory:

    def test_resolves_by_name(self, registered):
        assert determine_projectdirectory(PROJECT_NAME) == registered.dir

    def test_resolves_by_absolute_path(self, registered):
        assert determine_projectdirectory(str(registered.dir)) == registered.dir

    def test_resolves_by_home_relative_path(self, registered, monkeypatch):
        monkeypatch.setenv('HOME', str(registered.dir.parent))
        assert determine_projectdirectory(f'~/{PROJECT_NAME}') == registered.dir

    def test_unknown_name_returns_none(self, registered):
        assert determine_projectdirectory('NoSuchProject') is None

    def test_unknown_path_returns_none(self, registered):
        assert determine_projectdirectory('/nope/nothing') is None

    def test_a_bare_name_never_triggers_a_path_lookup(self, registered):
        """Otherwise every mistyped name would also probe the path column."""
        determine_projectdirectory('NoSuchProject')
        assert [kind for kind, _ in registered.calls] == ['name']

    def test_a_path_tries_the_name_first_then_the_path(self, registered):
        """Name first keeps a project literally named like a path working."""
        determine_projectdirectory(str(registered.dir))
        assert [kind for kind, _ in registered.calls] == ['name', 'path']

    def test_name_miss_is_silent_when_a_path_attempt_follows(self, registered, monkeypatch):
        """A successful path resolution must not log an error on the way."""
        seen = {}

        original = registered.record

        class _Db:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_project(self, name, silent=False):
                seen['silent'] = silent
                return None

            def get_project_by_path(self, path, silent=False):
                return original

        import adare.database.api.project as project_module
        monkeypatch.setattr(project_module, 'ProjectDbApi', _Db)

        determine_projectdirectory('/some/path')
        assert seen['silent'] is True

    def test_name_miss_is_loud_for_a_bare_name(self, registered):
        """With no fallback to come, the miss is the final answer — report it."""
        loud = {}

        class _Db:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_project(self, name, silent=False):
                loud['silent'] = silent
                return None

            def get_project_by_path(self, path, silent=False):  # pragma: no cover
                raise AssertionError('a bare name must not reach the path lookup')

        import adare.database.api.project as project_module
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(project_module, 'ProjectDbApi', _Db)
            assert determine_projectdirectory('NoSuchProject') is None
        assert loud['silent'] is False

    def test_registered_but_missing_directory_falls_through(self, tmp_path, monkeypatch):
        """Unchanged pre-existing behaviour: a registered project whose directory is
        gone falls through to the cwd lookup rather than erroring here."""
        record = SimpleNamespace(name=PROJECT_NAME, path=(tmp_path / 'vanished').as_posix())
        probed: list[str] = []

        class _Db:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_project(self, name, silent=False):
                return record

            def get_project_by_path(self, path, silent=False):
                probed.append(path.as_posix())
                return None

        import adare.database.api.project as project_module
        monkeypatch.setattr(project_module, 'ProjectDbApi', _Db)

        assert determine_projectdirectory(PROJECT_NAME) is None
        assert probed == [Path.cwd().as_posix()]


def test_no_project_given_uses_the_cwd(monkeypatch):
    class _Db:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_project(self, name, silent=False):  # pragma: no cover
            raise AssertionError('no name was given')

        def get_project_by_path(self, path, silent=False):
            return SimpleNamespace(name='cwd-project', path=path.as_posix())

    import adare.database.api.project as project_module
    monkeypatch.setattr(project_module, 'ProjectDbApi', _Db)
    assert determine_projectdirectory(None) == Path.cwd()
    assert basics.determine_projectdirectory('') == Path.cwd()

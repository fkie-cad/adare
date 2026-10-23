"""`adare test validate` warns about documentation gaps without failing validation."""

from argparse import Namespace
from pathlib import Path

import pytest

from adare.backend.testfunction.catalog import docstring_warnings

pytestmark = pytest.mark.unit

COLLECTION = '''\
from adarelib.testset.api import testfunction


@testfunction(name='undocumented', description='no docstring at all')
def undocumented(ctx, dst: str):
    return None


@testfunction(name='partly', description='one parameter lacks an Args entry')
def partly(ctx, dst: str, mode: str = 'any'):
    """Pass when it passes.

    Args:
        dst: Guest path.
    """
    return None


@testfunction(name='complete', description='fully documented')
def complete(ctx, dst: str):
    """Pass when it passes.

    Args:
        dst: Guest path.
    """
    return None
'''


@pytest.fixture
def collection_dir(tmp_path: Path) -> Path:
    directory = tmp_path / 'doccheck'
    directory.mkdir()
    (directory / 'doccheck.py').write_text(COLLECTION, encoding='utf-8')
    return directory


def test_docstring_warnings_flags_missing_docstring_and_args(collection_dir):
    warnings = docstring_warnings(collection_dir / 'doccheck.py')

    assert len(warnings) == 2
    assert any('doccheck.undocumented' in w and 'no docstring' in w for w in warnings)
    assert any('doccheck.partly' in w and 'mode' in w and 'dst' not in w.split('parameter(s)')[-1] for w in warnings)
    assert not any('doccheck.complete' in w for w in warnings)


def test_docstring_warnings_ignore_broken_file(tmp_path):
    broken = tmp_path / 'broken' / 'broken.py'
    broken.parent.mkdir()
    broken.write_text('def (:\n', encoding='utf-8')
    assert docstring_warnings(broken) == []


def test_validate_prints_warnings_but_passes(collection_dir, monkeypatch):
    from adare.cli import testfunction as cli
    from adare.console import console

    printed: list[str] = []
    monkeypatch.setattr(console, 'print', lambda *args, **kwargs: printed.append(' '.join(map(str, args))))

    # A failing validation calls exit(1) -> SystemExit; passing must return normally.
    cli.exec_validate_testfunction(Namespace(path=str(collection_dir)))

    output = '\n'.join(printed)
    assert 'doccheck is valid' in output
    assert 'documentation warning' in output
    assert 'doccheck.undocumented' in output
    assert 'doccheck.partly' in output

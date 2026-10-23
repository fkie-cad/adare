"""'adare vm test' keeps its own debug log in the working directory unless told not to."""

import logging
from types import SimpleNamespace

import pytest

from adare.cli import vm as cli_vm
from adare.logger.logger import FileHandlerFormatter

pytestmark = pytest.mark.unit


@pytest.fixture
def root_logger():
    """Restore the root logger's handlers and level after each test."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    root.setLevel(logging.WARNING)
    root.handlers = [h for h in handlers if not isinstance(h, logging.FileHandler)]
    yield root
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers, root.level = handlers, level


def _args(**overrides):
    return SimpleNamespace(**{'target': 'ubuntu2404-20261023', 'log_file': None, 'no_log': False, **overrides})


def test_default_log_goes_to_cwd_named_after_target(root_logger, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    path = cli_vm._attach_vm_test_log(_args())

    assert path is not None
    assert path.parent == tmp_path
    assert path.name.startswith('adare-vm-test-ubuntu2404-20261023-')
    assert path.suffix == '.log'
    logging.getLogger('adare.backend.experiment.vm_test').debug('CLAUDE: debug reaches the file')
    assert 'CLAUDE: debug reaches the file' in path.read_text()


def test_file_level_does_not_make_the_console_chattier(root_logger, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    root_logger.addHandler(console)

    cli_vm._attach_vm_test_log(_args())

    assert root_logger.level == logging.DEBUG
    assert console.level == logging.WARNING


def test_ova_target_uses_file_stem(tmp_path):
    path = cli_vm._vm_test_logfile_path('/images/my win 11.ova')

    assert path.name.startswith('adare-vm-test-my_win_11-')


def test_explicit_log_file(root_logger, tmp_path):
    target = tmp_path / 'custom.log'

    assert cli_vm._attach_vm_test_log(_args(log_file=str(target))) == target
    assert target.exists()


def test_no_log_writes_nothing(root_logger, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert cli_vm._attach_vm_test_log(_args(no_log=True)) is None
    assert list(tmp_path.iterdir()) == []


def test_reuses_global_logfile(root_logger, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    global_log = tmp_path / 'global.log'
    handler = logging.FileHandler(global_log)
    handler.setFormatter(FileHandlerFormatter())
    root_logger.addHandler(handler)

    assert cli_vm._attach_vm_test_log(_args()) == global_log
    assert [p.name for p in tmp_path.iterdir()] == ['global.log']


def test_unwritable_location_warns_and_continues(root_logger, tmp_path, capsys):
    path = cli_vm._attach_vm_test_log(_args(log_file=str(tmp_path / 'missing' / 'x.log')))

    assert path is None
    assert 'cannot write vm test log' in capsys.readouterr().err

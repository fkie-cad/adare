"""Host settings: environment > ~/.adare/settings.json > (legacy config profile) > default."""

import json

import pytest

from adare.config import settings

pytestmark = pytest.mark.unit

NAMES = list(settings.SETTINGS)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr('adare.config.userconfig.get', lambda name: None)
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / 'settings.json'


def test_defaults():
    assert settings.resolve('ADARE_MAX_VMS') == (20, 'default')
    assert settings.resolve('ADARE_DEV_SESSION_MAX_AGE_DAYS') == (None, 'default')


def test_saved_value_beats_default_and_environment_beats_saved(monkeypatch, isolated):
    assert settings.set_value('ADARE_MAX_VMS', '4') == 4
    assert json.loads(isolated.read_text()) == {'ADARE_MAX_VMS': 4}
    assert settings.resolve('ADARE_MAX_VMS') == (4, 'settings')

    monkeypatch.setenv('ADARE_MAX_VMS', '2')
    assert settings.resolve('ADARE_MAX_VMS') == (2, 'environment')


def test_legacy_config_profile_still_counts_below_the_settings_file(monkeypatch):
    monkeypatch.setattr('adare.config.userconfig.get', lambda name: '7' if name == 'ADARE_MAX_VMS' else None)
    assert settings.resolve('ADARE_MAX_VMS') == (7, 'config profile')
    settings.set_value('ADARE_MAX_VMS', 3)
    assert settings.resolve('ADARE_MAX_VMS') == (3, 'settings')


def test_unset_returns_to_the_default():
    settings.set_value('ADARE_DEV_SESSION_MAX_AGE_DAYS', '30')
    assert settings.get('ADARE_DEV_SESSION_MAX_AGE_DAYS') == 30.0
    assert settings.unset('ADARE_DEV_SESSION_MAX_AGE_DAYS') is True
    assert settings.unset('ADARE_DEV_SESSION_MAX_AGE_DAYS') is False
    assert settings.get('ADARE_DEV_SESSION_MAX_AGE_DAYS') is None


@pytest.mark.parametrize(
    ('name', 'raw', 'message'),
    [
        ('ADARE_MAX_VMS', '0', '>= 1'),
        ('ADARE_MAX_VMS', '2.5', 'whole number'),
        ('ADARE_MIN_FREE_DISK_GB', '-1', '>= 0'),
        ('ADARE_DEV_SESSION_MAX_AGE_DAYS', '0', '> 0'),
        ('ADARE_VM_SLOT_TIMEOUT', 'soon', 'must be a number'),
    ],
)
def test_invalid_values_are_refused_when_saved(name, raw, message):
    with pytest.raises(ValueError, match=message):
        settings.set_value(name, raw)


def test_an_invalid_environment_value_falls_back_with_a_warning(monkeypatch, caplog):
    monkeypatch.setenv('ADARE_MAX_VMS', 'many')
    settings.set_value('ADARE_MAX_VMS', 5)
    assert settings.resolve('ADARE_MAX_VMS') == (5, 'settings')
    assert 'Ignoring environment value' in caplog.text


def test_a_corrupt_file_is_ignored(isolated):
    isolated.write_text('{not json')
    assert settings.resolve('ADARE_MAX_VMS') == (20, 'default')


def test_cli_set_get_unset(isolated):
    from click.testing import CliRunner

    from adare.run import cli

    runner = CliRunner()
    result = runner.invoke(cli, ['system', 'settings', 'set', 'dev_session_max_age_days', '30'])
    assert result.exit_code == 0, result.output
    assert json.loads(isolated.read_text()) == {'ADARE_DEV_SESSION_MAX_AGE_DAYS': 30.0}

    result = runner.invoke(cli, ['system', 'settings', 'get', 'ADARE_DEV_SESSION_MAX_AGE_DAYS'])
    assert 'ADARE_DEV_SESSION_MAX_AGE_DAYS=30  (settings)' in result.output

    result = runner.invoke(cli, ['system', 'settings', 'list', '--json'])
    rows = {row['name']: row for row in json.loads(result.output)['settings']}
    assert rows['ADARE_DEV_SESSION_MAX_AGE_DAYS']['value'] == 30.0

    result = runner.invoke(cli, ['system', 'settings', 'unset', 'ADARE_DEV_SESSION_MAX_AGE_DAYS'])
    assert result.exit_code == 0 and json.loads(isolated.read_text()) == {}


def test_cli_refuses_unknown_and_invalid_settings(isolated):
    from click.testing import CliRunner

    from adare.run import cli

    runner = CliRunner()
    assert runner.invoke(cli, ['system', 'settings', 'set', 'nope', '1']).exit_code != 0
    assert runner.invoke(cli, ['system', 'settings', 'set', 'ADARE_MAX_VMS', '0']).exit_code != 0
    assert not isolated.exists()

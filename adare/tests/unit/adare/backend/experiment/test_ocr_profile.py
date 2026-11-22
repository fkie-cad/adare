"""OCR profile selection and provenance on the client side.

The cv-server's OCR engine decides where clicks land, so which profile a run uses
must be explicit (argv, never inherited env), pinnable per experiment
(``ocr:`` in metadata.yml) and recorded per run (``ocr.yml``). No cv-server is
started here: Popen and the engine-info call are faked.
"""

import asyncio
import logging
import subprocess

import pytest
import yaml

from adare.backend.experiment import mcp_server_manager as msm
from adare.backend.experiment.directory import ExperimentDirectory, ocr_info_file
from adare.backend.experiment.mcp_server_manager import (
    MCPServerManager,
    record_ocr_provenance,
    resolve_ocr_settings,
)
from adare.config import server as server_config
from adare.exceptions import DataStructuringError
from adare.types.experiment import ExperimentMetadata, OcrSettings

pytestmark = pytest.mark.unit

INFO = {
    'profile': 'rapidocr-v5m-latin',
    'engine': 'rapidocr',
    'lang': 'latin',
    'models': {'det': {'name': 'ch_PP-OCRv5_det_mobile.onnx', 'sha256': 'abc'}},
    'glyph_tolerance': True,
}


def _spawn(manager, monkeypatch) -> tuple[list[str], dict]:
    calls = []

    class FakePopen:
        pid = 4242

        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))

        def poll(self):
            return None

    async def ready():
        return True

    monkeypatch.setattr(manager, '_is_port_in_use', lambda port: False)
    monkeypatch.setattr(manager, '_await_ready', ready)
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    assert asyncio.run(manager.start())
    return calls[0]


class TestServerArgv:
    def test_defaults_come_from_config_and_are_passed_explicitly(self, monkeypatch):
        monkeypatch.setattr(server_config, 'OCR_ENGINE', 'rapidocr')
        monkeypatch.setattr(server_config, 'OCR_LANG', 'latin')
        cmd, _ = _spawn(MCPServerManager(server_port=13109), monkeypatch)
        assert cmd[cmd.index('--ocr-engine') + 1] == 'rapidocr'
        assert cmd[cmd.index('--ocr-lang') + 1] == 'latin'

    def test_experiment_pin_overrides_default(self, monkeypatch):
        monkeypatch.setattr(server_config, 'OCR_ENGINE', 'rapidocr')
        cmd, _ = _spawn(MCPServerManager(server_port=13109, ocr_engine='paddle', ocr_lang='en'), monkeypatch)
        assert cmd[cmd.index('--ocr-engine') + 1] == 'paddle'
        assert cmd[cmd.index('--ocr-lang') + 1] == 'en'

    def test_child_env_skips_paddle_source_check_and_sets_threads(self, monkeypatch):
        monkeypatch.delenv('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', raising=False)
        monkeypatch.setattr(server_config, 'OCR_THREADS', '2')
        _, kwargs = _spawn(MCPServerManager(server_port=13109), monkeypatch)
        assert kwargs['env']['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] == 'True'
        assert kwargs['env']['ADARE_OCR_THREADS'] == '2'


@pytest.fixture
def experiment(tmp_path):
    exp = ExperimentDirectory(tmp_path, 'exp')
    exp.path.mkdir(parents=True)
    return exp


class TestExperimentPin:
    def test_no_pin_means_default(self, experiment):
        experiment.metadatafile.write_text('environments: [env1]\n')
        assert resolve_ocr_settings(experiment) == (None, None)

    def test_pin_is_read(self, experiment):
        experiment.metadatafile.write_text('environments: [env1]\nocr:\n  engine: paddle\n')
        assert resolve_ocr_settings(experiment) == ('paddle', None)

    def test_no_experiment_means_default(self):
        assert resolve_ocr_settings(None) == (None, None)

    def test_unknown_engine_is_a_metadata_error(self, experiment):
        experiment.metadatafile.write_text('environments: [env1]\nocr:\n  engine: tesseract\n')
        with pytest.raises(DataStructuringError):
            experiment.load_metadata()

    def test_save_metadata_keeps_the_pin(self, experiment):
        experiment.save_metadata(ExperimentMetadata(environments=['env1'], ocr=OcrSettings(engine='paddle')))
        saved = yaml.safe_load(experiment.metadatafile.read_text())
        assert saved['ocr'] == {'engine': 'paddle'}
        assert experiment.load_metadata().ocr == OcrSettings(engine='paddle')


class TestProvenance:
    def _record(self, tmp_path, monkeypatch, info, manager=None, machine_key=None):
        manager = manager or MCPServerManager(server_port=13109, ocr_engine='rapidocr', ocr_lang='latin')

        async def fetch(timeout=300.0):
            return info

        monkeypatch.setattr(manager, 'fetch_engine_info', fetch)
        return asyncio.run(record_ocr_provenance(manager, tmp_path, machine_key=machine_key))

    def test_writes_ocr_yml(self, tmp_path, monkeypatch):
        self._record(tmp_path, monkeypatch, INFO)
        record = yaml.safe_load((tmp_path / 'ocr.yml').read_text())
        assert record['profile'] == 'rapidocr-v5m-latin'
        assert record['requested'] == {'engine': 'rapidocr', 'lang': 'latin'}
        assert record['models']['det']['sha256'] == 'abc'

    def test_one_file_per_machine(self, tmp_path, monkeypatch):
        self._record(tmp_path, monkeypatch, INFO, machine_key='client')
        assert ocr_info_file(tmp_path, 'client') == tmp_path / 'ocr-client.yml'
        assert (tmp_path / 'ocr-client.yml').exists()

    def test_warns_when_the_server_runs_another_profile(self, tmp_path, monkeypatch, caplog):
        manager = MCPServerManager(server_port=13109, ocr_engine='paddle')
        with caplog.at_level(logging.WARNING, logger=msm.__name__):
            self._record(tmp_path, monkeypatch, INFO, manager=manager)
        assert 'paddle' in caplog.text and 'rapidocr-v5m-latin' in caplog.text

    def test_unreachable_server_writes_nothing(self, tmp_path, monkeypatch):
        assert self._record(tmp_path, monkeypatch, None) is None
        assert not (tmp_path / 'ocr.yml').exists()

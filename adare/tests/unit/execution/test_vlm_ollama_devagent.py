"""Tests for the Ollama-Cloud-facing pieces: gui-doctor coord detection and the
dev-agent service mixin's session handling."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from adare.cli.vm_gui_doctor import _calibration_png_b64, _classify_coords
from adare.core.dto.devmode import DevGuiAgentRequest
from adare.services.devmode.gui_agent import GuiAgentMixin

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# gui-doctor coordinate classifier
# ---------------------------------------------------------------------------

def test_classifier_detects_absolute():
    # Model returns the target's actual pixel coordinates.
    detected, err_abs, err_norm = _classify_coords(740, 250)
    assert detected == 'absolute'
    assert err_abs < err_norm


def test_classifier_detects_normalized():
    # Target (740, 250) on a 1000x800 image → normalized (740, 312.5).
    detected, err_abs, err_norm = _classify_coords(740, 312)
    assert detected == 'normalized_1000'
    assert err_norm < err_abs


def test_classifier_rejects_garbage():
    detected, _, _ = _classify_coords(5, 5)
    assert detected is None


def test_calibration_image_is_valid_png():
    raw = base64.b64decode(_calibration_png_b64())
    with Image.open(io.BytesIO(raw)) as img:
        assert img.size == (1000, 800)
        assert img.format == 'PNG'


# ---------------------------------------------------------------------------
# dev-agent service mixin: graceful failure when the session/VM is absent
# ---------------------------------------------------------------------------

class _FakeManager:
    def __init__(self, session):
        self._session = session

    async def get_or_restore_session(self, session_id, console_ulid=None):
        return self._session


class _Svc(GuiAgentMixin):
    def __init__(self, session):
        self._manager = _FakeManager(session)


def test_run_gui_agent_no_session_fails_cleanly():
    svc = _Svc(session=None)
    result = svc.run_gui_agent(DevGuiAgentRequest(session_id='missing', goal='x'))
    assert result.success is False
    assert result.error.code == 'SESSION_NOT_FOUND'


def test_run_gui_agent_session_without_vm_fails_cleanly():
    class _Ctx:
        vm = None
        experiment_run_directory = None

    class _Session:
        experiment_ctx = _Ctx()

    svc = _Svc(session=_Session())
    result = svc.run_gui_agent(DevGuiAgentRequest(session_id='s', goal='x'))
    assert result.success is False
    assert result.error.code == 'SESSION_NOT_FOUND'

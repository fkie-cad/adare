"""Tests for PlaybookControllerConfig dataclass."""

import pytest

pytestmark = pytest.mark.unit

from dataclasses import fields
from pathlib import Path

from adare.backend.experiment.playbook_controller import PlaybookControllerConfig


class TestDefaults:
    """Verify default field values."""

    def test_all_defaults(self):
        cfg = PlaybookControllerConfig()

        assert cfg.experiment_dir is None
        assert cfg.project_dir is None
        assert cfg.mcp_gui_url == "http://localhost:13109/mcp"
        assert cfg.debug_screenshots is False
        assert cfg.screenshots_dir is None
        assert cfg.experiment_id is None
        assert cfg.experiment_run_id is None
        assert cfg.experiment_run_directory is None
        assert cfg.vm_os is None
        assert cfg.vm_user is None
        assert cfg.test_mode is False
        assert cfg.config is None

    def test_field_count(self):
        """Ensure we don't accidentally drop or add fields without updating tests."""
        assert len(fields(PlaybookControllerConfig)) == 12


class TestConstruction:
    """Verify construction with explicit values."""

    def test_all_fields_set(self):
        sentinel = object()
        cfg = PlaybookControllerConfig(
            experiment_dir=Path("/exp"),
            project_dir=Path("/proj"),
            mcp_gui_url="http://custom:9999/mcp",
            debug_screenshots=True,
            screenshots_dir=Path("/screens"),
            experiment_id="exp-123",
            experiment_run_id="run-456",
            experiment_run_directory=Path("/runs/456"),
            vm_os="linux",
            vm_user="testuser",
            test_mode=True,
            config=sentinel,
        )

        assert cfg.experiment_dir == Path("/exp")
        assert cfg.project_dir == Path("/proj")
        assert cfg.mcp_gui_url == "http://custom:9999/mcp"
        assert cfg.debug_screenshots is True
        assert cfg.screenshots_dir == Path("/screens")
        assert cfg.experiment_id == "exp-123"
        assert cfg.experiment_run_id == "run-456"
        assert cfg.experiment_run_directory == Path("/runs/456")
        assert cfg.vm_os == "linux"
        assert cfg.vm_user == "testuser"
        assert cfg.test_mode is True
        assert cfg.config is sentinel

    def test_partial_fields(self):
        cfg = PlaybookControllerConfig(
            project_dir=Path("/proj"),
            test_mode=True,
        )

        assert cfg.project_dir == Path("/proj")
        assert cfg.test_mode is True
        # Everything else should be default
        assert cfg.experiment_dir is None
        assert cfg.debug_screenshots is False


class TestEquality:
    """Dataclass equality semantics."""

    def test_equal_instances(self):
        a = PlaybookControllerConfig(project_dir=Path("/proj"))
        b = PlaybookControllerConfig(project_dir=Path("/proj"))
        assert a == b

    def test_unequal_instances(self):
        a = PlaybookControllerConfig(project_dir=Path("/proj"))
        b = PlaybookControllerConfig(project_dir=Path("/other"))
        assert a != b
